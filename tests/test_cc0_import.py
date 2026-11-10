"""Free local-media integration and source-backed graphics guardrails."""
import tempfile
import unittest
from pathlib import Path

import app
from studio_routes import MUSIC_DIR
from motion_component_pack import plan_components, paint_frame


class CC0AndDataTests(unittest.TestCase):
    def test_no_invented_rating(self):
        words = [
            {"start": 1.0, "end": 1.2, "text": "rating"},
            {"start": 1.3, "end": 1.5, "text": "matters"},
        ]
        candidates = plan_components(words, "neon_business", 9)
        self.assertFalse(any(x["kind"] == "rating_strip" for x in candidates))

    def test_rating_from_spoken_number(self):
        words = [
            {"start": 1.0, "end": 1.2, "text": "4"},
            {"start": 1.3, "end": 1.5, "text": "star"},
            {"start": 1.6, "end": 1.8, "text": "rating"},
        ]
        candidates = plan_components(words, "neon_business", 9)
        matched = [x for x in candidates if x["kind"] == "rating_strip"]
        self.assertTrue(matched)
        self.assertIn("4", matched[0]["word"])

    def test_library_route_registered(self):
        paths={getattr(r,"path","") for r in app.app.routes}
        self.assertIn("/api/studio/music",paths)

    def test_import_source_collection(self):
        from scripts.import_anve_cc0_audio import collect
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root / "music" / "library" / "beds"
            p.mkdir(parents=True)
            (p / "bed.wav").write_bytes(b"test")
            self.assertEqual(len(collect(root,"music/library/beds",2)),1)
            self.assertEqual(collect(root,"music/library/beds",0),[])


if __name__=="__main__":
    unittest.main()
