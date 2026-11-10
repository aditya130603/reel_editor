"""Unit tests for new caption-animation and contextual B-roll modules."""
import json
import tempfile
import unittest
from pathlib import Path

import broll_matcher
import caption_motion


WORDS = [
    {"start": .1, "end": .4, "text": "Kidney"},
    {"start": .41, "end": .7, "text": "stones"},
    {"start": .71, "end": 1.05, "text": "are"},
    {"start": 1.06, "end": 1.5, "text": "painful."},
    {"start": 3.2, "end": 3.5, "text": "Surgery"},
    {"start": 3.51, "end": 3.8, "text": "is"},
    {"start": 3.81, "end": 4.2, "text": "sometimes"},
    {"start": 4.21, "end": 4.7, "text": "needed."},
]


class MotionTests(unittest.TestCase):
    def test_every_caption_style_generates_ass(self):
        for style in caption_motion.STYLES:
            with self.subTest(style=style), tempfile.TemporaryDirectory() as d:
                p = Path(d) / "motion.ass"
                timeline = caption_motion.render_ass(
                    WORDS, {"caption_style": style, "size": 66, "font": "DejaVu Sans",
                            "accent": "99DDCC", "primary": "FFFFFF",
                            "words_per_card": 4}, p
                )
                content = p.read_text()
                self.assertIn("[Events]", content)
                self.assertIn("Dialogue:", content)
                self.assertTrue(timeline)
                self.assertTrue(all(item["end"] > item["start"] for item in timeline))

    def test_emphasis_prefers_strong_words(self):
        group = [{"text": "the"}, {"text": "critical"}, {"text": "case"}]
        self.assertEqual(caption_motion.hero_index(group), 1)

    def test_safe_ass_escape(self):
        self.assertNotIn("{", caption_motion.escape("{\\r}"))
        self.assertNotIn("}", caption_motion.escape("{\\r}"))

    def test_broll_aliases_match(self):
        item = {"tags": ["renal", "care"], "description": ""}
        self.assertGreater(broll_matcher.lexical_score("Kidney care is important.", item), 0)

    def test_broll_gap_and_order(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            (directory / "kidney.mp4").touch()
            (directory / "surgery.mp4").touch()
            options = {"broll": True, "max_broll": 2, "broll_duration": 1.5,
                       "min_broll_gap": 2}
            selected = broll_matcher.choose(WORDS, options, 9, directory)
            self.assertGreaterEqual(len(selected), 1)
            self.assertLessEqual(len(selected), 2)
            self.assertEqual(selected, sorted(selected, key=lambda x: x["start"]))

    def test_asset_sidecar_tags(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            (directory / "take01.mp4").touch()
            (directory / "take01.mp4.json").write_text(
                json.dumps({"tags": ["kidney", "scan"], "description": "A doctor reviewing scans"})
            )
            indexed = broll_matcher.catalog(directory)
            self.assertIn("kidney", indexed[0]["tags"])

    def test_cosine(self):
        self.assertAlmostEqual(broll_matcher.similarity([1, 0], [0, 1]), 0)
        self.assertAlmostEqual(broll_matcher.similarity([1, 0], [1, 0]), 1)


if __name__ == "__main__":
    unittest.main()
