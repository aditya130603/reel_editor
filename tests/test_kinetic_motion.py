"""Tests for locally generated alpha motion graphics, reference-inspired but original."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import app
from motion_component_pack import PACKS, COMPONENTS, plan_components, render_components, paint_frame


class KineticPackTest(unittest.TestCase):
    def test_empty_and_bounded_plans(self):
        words = [
            {"start": .7 + i * 2.6, "end": 1 + i * 2.6,
             "text": word}
            for i, word in enumerate(["editing", "50%", "marketing", "$2000", "important", "rating"])
        ]
        self.assertEqual(plan_components(words, "off", 25), [])
        for pack in ("editorial_clean", "neon_business", "documentary"):
            chosen = plan_components(words, pack, 25)
            self.assertTrue(chosen)
            self.assertLessEqual(len(chosen), 4)
            self.assertTrue(all(v["end"] <= 25 for v in chosen))
            self.assertEqual(sorted(chosen, key=lambda x:x["at"]),chosen)

    def test_all_component_illustrations_draw_safely(self):
        cue = {"pack":"neon_business", "word":"IMPORTANT", "at":.9}
        for name in COMPONENTS:
            with self.subTest(name=name):
                cue["kind"] = name
                for progress in (0.0, .2, .5, .8, 1.0):
                    im = paint_frame(cue, 360, 640, progress)
                    self.assertEqual(im.mode, "RGBA")
                    self.assertEqual(im.size,(360,640))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),"No FFmpeg")
    def test_generated_alpha_overlays_composite_to_video(self):
        if not app.verify_tools()["ready"]:
            self.skipTest("Missing libass")
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            source=folder/"test.mp4"
            command=["ffmpeg","-hide_banner","-nostdin","-loglevel","error","-y",
                     "-f","lavfi","-i","color=c=blue:s=180x320:r=30:d=4",
                     "-f","lavfi","-i","sine=frequency=420:duration=4",
                     "-c:v","mpeg4","-c:a","aac","-shortest",str(source)]
            subprocess.run(command,check=True,capture_output=True,timeout=40)
            cue={"pack":"neon_business","kind":"metric_card","word":"$500",
                 "at":.7,"end":2.7,"score":10,"phrase":"price"}
            overlays=render_components([cue],folder,180,320)
            self.assertEqual(len(overlays),1)
            self.assertGreater(overlays[0]["path"].stat().st_size,2000)
            self.assertEqual(overlays[0]["kind"], "metric_card")
            original=app.RENDER_WIDTH,app.RENDER_HEIGHT
            app.RENDER_WIDTH,app.RENDER_HEIGHT=180,320
            try:
                subs=folder/"caption.ass"
                preset=dict(app.presets()["medical_clean"])
                app.make_ass([{"start":.2,"end":1.1,"text":"Editing"}],preset,subs)
                output=folder/"final.mp4"
                app.render(source,subs,output,preset,[],4,True,[],None,overlays)
                self.assertTrue(app.probe(output)["has_audio"])
                self.assertTrue(app.probe(output)["has_video"])
                self.assertGreater(output.stat().st_size,4000)
            finally:
                app.RENDER_WIDTH,app.RENDER_HEIGHT=original


if __name__=="__main__":
    unittest.main()
