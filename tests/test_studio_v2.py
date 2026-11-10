"""Studio V2 integration tests, using tiny generated media (no AI/model download)."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import app
from caption_motion import render_ass
from studio_pipeline import normalize_clips, join_clips, mix_music, drawtext_filters


def run(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                    *map(str, args)], check=True, capture_output=True, timeout=50)


class StudioV2(unittest.TestCase):
    def test_responsive_captions_stay_two_line(self):
        words = [
            {"start": .1 + i * .2, "end": .26 + i * .2, "text": w}
            for i, w in enumerate(["Endometriosis", "surgeries", "require", "specialized", "experience"])
        ]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "words.ass"
            timeline = render_ass(words, {"caption_style": "highlight",
                                        "size": 70, "words_per_card": 5}, p, 360, 640)
            self.assertGreaterEqual(len(timeline), 1)
            content = p.read_text()
            self.assertIn("Dialogue:", content)
            self.assertIn(r"\N", content)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "No FFmpeg")
    def test_multiclip_transitions_music_and_motion_titles(self):
        if not app.verify_tools()["ready"]:
            self.skipTest("No libass")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            files = []
            for idx, color in enumerate(("blue", "red")):
                file = root / f"sample{idx}.mp4"
                run("-f", "lavfi", "-i", f"color=c={color}:s=180x320:r=30:d=2",
                    "-f", "lavfi", "-i", f"sine=frequency={300+idx*100}:duration=2",
                    "-c:v", "mpeg4", "-c:a", "aac", "-shortest", file)
                files.append(file)
            music = root / "music.wav"
            run("-f", "lavfi", "-i", "sine=frequency=650:duration=4", music)
            clips, lengths = normalize_clips(files, root, 180, 320, 120,
                                             lambda p: app.probe(p)["has_audio"])
            joined = root / "joined.mp4"
            total = join_clips(clips, lengths, joined, "fade", .25, 120)
            self.assertGreater(total, 3.5)
            self.assertTrue(app.probe(joined)["has_audio"])
            words = [{"start": .4, "end": .65, "text": "Kidney"},
                     {"start": 1.2, "end": 1.5, "text": "important"},
                     {"start": 2.2, "end": 2.5, "text": "surgery"}]
            titles, events = drawtext_filters(words, "editorial", root, 180, 320)
            self.assertGreater(len(events), 0)
            preset = dict(app.presets()["medical_clean"])
            existing_width, existing_height = app.RENDER_WIDTH, app.RENDER_HEIGHT
            app.RENDER_WIDTH, app.RENDER_HEIGHT = 180, 320
            try:
                ass = root / "captions.ass"
                app.make_ass(words, preset, ass)
                graphics = root / "graphics.mp4"
                app.render(joined, ass, graphics, preset, [], total, True, titles)
                final = root / "with_music.mp4"
                mix_music(graphics, music, final, .12, 120)
                self.assertTrue(app.probe(final)["has_audio"])
                self.assertTrue(app.probe(final)["has_video"])
                self.assertGreater(final.stat().st_size, 8000)
            finally:
                app.RENDER_WIDTH, app.RENDER_HEIGHT = existing_width, existing_height

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "No FFmpeg")
    def test_hard_cut_multiclip(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            sources = []
            for i in range(2):
                p = root / f"cut{i}.mp4"
                run("-f", "lavfi", "-i", f"color=c=green:s=120x212:r=30:d=1.5",
                    "-f", "lavfi", "-i", "sine=frequency=500:duration=1.5",
                    "-c:v", "mpeg4", "-c:a", "aac", "-shortest", p)
                sources.append(p)
            norm, lengths = normalize_clips(sources, root, 120, 212, 120,
                                            lambda p: app.probe(p)["has_audio"])
            out = root / "hard.mp4"
            final_length = join_clips(norm, lengths, out, "cut", timeout=120)
            self.assertAlmostEqual(final_length, 3, delta=.25)


if __name__ == "__main__":
    unittest.main()
