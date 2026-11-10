"""Regression tests for the latest caption-polish, cutaway and optional SFX paths."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import app
import broll_matcher
import caption_motion


class FinalRegression(unittest.TestCase):
    def test_special_caption_treatments_have_real_tags(self):
        words = [{"start": .1, "end": .4, "text": "Important"},
                 {"start": .43, "end": .8, "text": "information"}]
        cases = {
            "editorial": r"\move(",
            "outline": r"\1a&HFF&",
            "glow": r"\blur5",
            "karaoke": r"\fscx111",
            "typewriter": "Dialogue: 0",
            "soft_bounce": r"\fscx107",
        }
        for style, tag in cases.items():
            with self.subTest(style=style), tempfile.TemporaryDirectory() as d:
                p = Path(d) / "captions.ass"
                caption_motion.render_ass(words, {"caption_style": style}, p, 360, 640)
                self.assertIn(tag, p.read_text())

    def test_cutaway_follows_spoken_keyword(self):
        words = [{"start": 1, "end": 1.3, "text": "We"},
                 {"start": 3.2, "end": 3.5, "text": "kidney"},
                 {"start": 3.5, "end": 3.7, "text": "scans"}]
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "renal_scan.mp4").touch()
            preset = {"broll": True, "max_broll": 1,
                      "broll_duration": 1.5, "min_broll_gap": 3}
            selected = broll_matcher.choose(words, preset, 9, Path(d))
            self.assertEqual(len(selected), 1)
            self.assertAlmostEqual(selected[0]["start"], 3.12, delta=.08)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg unavailable")
    def test_still_broll_with_ken_burns_and_sfx(self):
        if not app.verify_tools()["ready"]:
            self.skipTest("libass unavailable")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "source.mp4"
            still = root / "kidney.png"
            sound = root / "soft_whoosh.wav"
            cmds = [
                ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "lavfi", "-i", "color=c=blue:s=180x320:r=24:d=2",
                 "-f", "lavfi", "-i", "sine=frequency=220:duration=2",
                 "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(source)],
                ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "lavfi", "-i", "color=c=red:s=180x320:d=.1",
                 "-frames:v", "1", str(still)],
                ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "lavfi", "-i", "sine=frequency=600:duration=.5",
                 "-ar", "48000", str(sound)],
            ]
            for command in cmds:
                subprocess.run(command, capture_output=True, check=True, timeout=30)
            preset = dict(app.presets()["viral_punch"])
            preset.update({"broll_motion": "slow_push", "sfx": True,
                           "sfx_file": sound.name, "sfx_volume": .05})
            original = app.RENDER_WIDTH, app.RENDER_HEIGHT, app.SFX_DIR
            app.RENDER_WIDTH, app.RENDER_HEIGHT, app.SFX_DIR = 180, 320, root
            try:
                ass = root / "captions.ass"
                app.make_ass([{"start": .2, "end": .7, "text": "Kidney"}], preset, ass)
                out = root / "output.mp4"
                app.render(source, ass, out, preset, [
                    {"start": .3, "duration": 1.1, "asset": still}
                ], 2, True)
                self.assertTrue(app.probe(out)["has_video"])
                self.assertTrue(app.probe(out)["has_audio"])
                self.assertGreater(out.stat().st_size, 1000)
            finally:
                app.RENDER_WIDTH, app.RENDER_HEIGHT, app.SFX_DIR = original


if __name__ == "__main__":
    unittest.main()
