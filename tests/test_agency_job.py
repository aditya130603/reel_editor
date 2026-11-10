"""End-to-end agency preset render: actual POST worker path without model downloads."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import app
from studio_routes import process_studio


class OneClickRenderTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg missing")
    def test_one_preset_end_to_end_with_generated_fx_music_and_captions(self):
        if not app.verify_tools()["ready"]:
            self.skipTest("libass missing")
        with tempfile.TemporaryDirectory() as d:
            previous=(app.DATA,app.jobs,app.RENDER_WIDTH,app.RENDER_HEIGHT,
                      app.whisper_words,app.FFMPEG_TIMEOUT)
            root=Path(d)
            jobid="abcdef1234567890abcdef1234567890"
            folder=root/jobid
            folder.mkdir()
            original=folder/"clip_00.mp4"
            cmd=["ffmpeg","-hide_banner","-nostdin","-loglevel","error","-y",
                 "-f","lavfi","-i","color=c=purple:s=180x320:r=30:d=7",
                 "-f","lavfi","-i","sine=frequency=245:duration=7",
                 "-c:v","mpeg4","-c:a","aac","-shortest",str(original)]
            subprocess.run(cmd,check=True,capture_output=True,timeout=40)
            try:
                app.DATA=root;app.RENDER_WIDTH=180;app.RENDER_HEIGHT=320
                app.FFMPEG_TIMEOUT=120
                app.jobs={jobid:{"id":jobid,"state":"queued","message":"test"}}
                app.whisper_words=lambda path:[
                    {"start":.7,"end":1.0,"text":"Important"},
                    {"start":1.05,"end":1.37,"text":"kidney"},
                    {"start":1.42,"end":1.7,"text":"health."},
                    {"start":4.1,"end":4.4,"text":"Always"},
                    {"start":4.5,"end":4.85,"text":"remember."}]
                process_studio(jobid,[original],None,"medical_clean",None,
                               "fade","none",.1,False,"off","clinical_pro")
                self.assertEqual(app.jobs[jobid]["state"],"completed",
                                 app.jobs[jobid].get("message"))
                output=folder/"output.mp4"
                self.assertTrue(output.is_file())
                self.assertTrue(app.probe(output)["has_audio"])
                self.assertTrue(app.probe(output)["has_video"])
                self.assertGreater(output.stat().st_size,8000)
                self.assertTrue((folder/"edit_plan.json").is_file())
                self.assertTrue((folder/"captions.ass").is_file())
            finally:
                (app.DATA,app.jobs,app.RENDER_WIDTH,app.RENDER_HEIGHT,
                 app.whisper_words,app.FFMPEG_TIMEOUT)=previous
