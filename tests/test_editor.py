"""Smoke tests for rules and the FFmpeg render path. No Whisper model download."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import app


class EditorTests(unittest.TestCase):
    def test_presets_load(self):
        for key, preset in app.presets().items():
            self.assertTrue(key)
            self.assertGreater(preset["words_per_card"], 0)

    def test_emphasis_and_ass(self):
        words = [
            {"start": 0.1, "end": 0.4, "text": "Kidney"},
            {"start": 0.41, "end": 0.7, "text": "stones"},
            {"start": 0.71, "end": 0.95, "text": "hurt."},
        ]
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "captions.ass"
            cards = app.make_ass(words, app.presets()["medical_clean"], target)
            self.assertTrue(cards)
            self.assertIn("Dialogue:", target.read_text())
            self.assertIn("Kidney", target.read_text())

    def test_broll_keyword_matching(self):
        with tempfile.TemporaryDirectory() as d:
            original = app.ASSETS
            try:
                app.ASSETS = Path(d)
                (Path(d) / "kidney_scan.png").write_bytes(b"placeholder")
                words = [{"start": 1, "end": 1.3, "text": "kidney"}]
                choices = app.select_broll(words, app.presets()["medical_clean"], 12)
                self.assertEqual(len(choices), 1)
            finally:
                app.ASSETS = original

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg unavailable")
    def test_ffmpeg_render(self):
        if not app.verify_tools()["ready"]:
            self.skipTest("FFmpeg libass unavailable")
        words = [{"start": .2, "end": .6, "text": "Kidney"},
                 {"start": .65, "end": 1.1, "text": "care"}]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "test.mp4"
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                   "-f", "lavfi", "-i", "color=c=blue:s=360x640:r=30:d=3",
                   "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                   "-c:v", "libx264", "-c:a", "aac", "-shortest", str(source)]
            subprocess.run(cmd, check=True, timeout=50, capture_output=True)
            ass = root / "test.ass"
            preset = app.presets()["medical_clean"]
            app.make_ass(words, preset, ass)
            previous_width, previous_height = app.RENDER_WIDTH, app.RENDER_HEIGHT
            app.RENDER_WIDTH, app.RENDER_HEIGHT = 360, 640
            try:
                output = root / "out.mp4"
                app.render(source, ass, output, preset, [], 3, True)
                self.assertGreater(output.stat().st_size, 1000)
                self.assertTrue(app.probe(output)["has_audio"])
            finally:
                app.RENDER_WIDTH, app.RENDER_HEIGHT = previous_width, previous_height


    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg unavailable")
    def test_six_broll_transitions(self):
        if not app.verify_tools()["ready"]:
            self.skipTest("FFmpeg libass unavailable")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "source.mp4"
            insert = root / "kidney.mp4"
            for color, target in [("blue", source), ("red", insert)]:
                args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", f"color=c={color}:s=180x320:r=24:d=2",
                        "-c:v", "mpeg4", str(target)]
                subprocess.run(args, check=True, timeout=40, capture_output=True)
            words = [{"start": .1, "end": .35, "text": "Kidney"}]
            caption = root / "captions.ass"
            preset = dict(app.presets()["medical_clean"])
            old_size = app.RENDER_WIDTH, app.RENDER_HEIGHT
            app.RENDER_WIDTH, app.RENDER_HEIGHT = 180, 320
            try:
                app.make_ass(words, preset, caption)
                for transition in app.TRANSITIONS:
                    with self.subTest(transition=transition):
                        preset["transition_style"] = transition
                        preset["transition"] = .12
                        out = root / (transition + ".mp4")
                        app.render(source, caption, out, preset, [
                            {"start": .35, "duration": .9, "asset": insert}
                        ], 2, False)
                        self.assertGreater(out.stat().st_size, 1000)
                        self.assertTrue(app.probe(out)["has_video"])
            finally:
                app.RENDER_WIDTH, app.RENDER_HEIGHT = old_size



if __name__ == "__main__":
    unittest.main()
