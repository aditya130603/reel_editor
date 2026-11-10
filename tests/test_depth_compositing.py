"""Smoke-test true subject alpha compositing without downloading a model."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import app
from studio_pipeline import drawtext_filters


class DepthCompositingTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg unavailable")
    def test_mask_video_keeps_subject_above_title(self):
        if not app.verify_tools()["ready"]:
            self.skipTest("libass unavailable")
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            clip = directory / "clip.mp4"
            matte = directory / "alpha.mkv"
            src = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
            for command in [
                src + ["-f", "lavfi", "-i", "color=c=blue:s=180x320:r=30:d=2",
                       "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                       "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(clip)],
                src + ["-f", "lavfi", "-i", "color=c=white:s=180x320:r=30:d=2",
                       "-vf", "format=gray", "-c:v", "ffv1", "-pix_fmt", "gray",
                       str(matte)]
            ]:
                subprocess.run(command, check=True, timeout=30, capture_output=True)
            old_w, old_h = app.RENDER_WIDTH, app.RENDER_HEIGHT
            app.RENDER_WIDTH, app.RENDER_HEIGHT = 180, 320
            try:
                words = [{"start": .2, "end": .6, "text": "KIDNEY"},
                         {"start": 1.1, "end": 1.5, "text": "URGENT"}]
                ass = directory / "captions.ass"
                preset = app.presets()["medical_clean"]
                app.make_ass(words, preset, ass)
                filters, events = drawtext_filters(words, "poster", directory, 180, 320)
                self.assertGreater(len(events), 0)
                output = directory / "out.mp4"
                app.render(clip, ass, output, preset, [], 2, True, filters, matte)
                self.assertTrue(app.probe(output)["has_audio"])
                self.assertTrue(app.probe(output)["has_video"])
                self.assertGreater(output.stat().st_size, 3000)
            finally:
                app.RENDER_WIDTH, app.RENDER_HEIGHT = old_w, old_h


if __name__ == "__main__":
    unittest.main()
