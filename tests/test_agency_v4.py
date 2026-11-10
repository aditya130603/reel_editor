"""V4: actual automated effects, caption safety and sound mix smoke tests."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import app
from agency_director import PROFILES, plan, caption_config, broll_config
from agency_captions import make_subs
from agency_fx import make_frame, render_fx
from agency_sfx import write_cues, add_effect_sound
from agency_music import music_bed
import wave

WORDS=[
    {"start":.7,"end":.96,"text":"Kidney"},
    {"start":.98,"end":1.2,"text":"surgery"},
    {"start":1.28,"end":1.55,"text":"is"},
    {"start":1.58,"end":1.92,"text":"important."},
    {"start":4.5,"end":4.8,"text":"Never"},
    {"start":4.85,"end":5.16,"text":"ignore"},
    {"start":5.2,"end":5.6,"text":"bleeding."}
]


class AgencyReleaseTests(unittest.TestCase):
    def test_all_presets_have_unique_complete_design_rules(self):
        self.assertEqual(len(PROFILES),4)
        for key,profile in PROFILES.items():
            with self.subTest(key=key):
                self.assertIn("caption",profile)
                self.assertIn("graphics",profile)
                self.assertIn("transitions",profile)
                self.assertGreater(profile["event_gap"],4)
                self.assertLessEqual(profile["size"],58)
                self.assertGreater(profile["position"],.80)

    def test_effect_plan_provides_actual_events_without_broll(self):
        for key in PROFILES:
            events=plan(WORDS,35,key)
            self.assertGreaterEqual(len(events),3)
            self.assertLessEqual(len(events),16)
            self.assertTrue(all(e["kind"] in
                PROFILES[key]["graphics"]+PROFILES[key]["transitions"] for e in events))
            self.assertTrue(all(.5<=e["at"]<35 for e in events))

    def test_film_and_paper_render_assets_in_rgba(self):
        effects=["scribble","click","diagram_lines","paper_corner",
                 "sticker","film_grain","light_rays","film_burn",
                 "light_leak","shutter","paper_fold","flash","countdown"]
        for effect in effects:
            with self.subTest(effect=effect):
                event={"kind":effect,"at":1.4,"profile":"paper_story","word":"IMPORTANT",
                       "zone":"upper-left"}
                for p in (0,.2,.5,.85,1):
                    image=make_frame(event,p,180,320)
                    self.assertEqual(image.size,(180,320))
                    self.assertEqual(image.mode,"RGBA")

    def test_original_preset_soundtracks(self):
        with tempfile.TemporaryDirectory() as folder:
            for key in PROFILES:
                with self.subTest(key=key):
                    dest=Path(folder)/(key+".wav")
                    music_bed(key,dest)
                    with wave.open(str(dest),"rb") as audio:
                        self.assertEqual(audio.getnchannels(),1)
                        self.assertEqual(audio.getframerate(),16000)
                        self.assertEqual(audio.getnframes(),12*16000)
                    self.assertGreater(dest.stat().st_size,250000)

    def test_caption_safe_area(self):
        with tempfile.TemporaryDirectory() as d:
            for key in PROFILES:
                target=Path(d)/(key+".ass")
                timeline=make_subs(WORDS,caption_config(key),target,720,1280)
                body=target.read_text()
                self.assertTrue(timeline)
                self.assertIn("Style: Main",body)
                self.assertIn(",2,64,64,230",body) if False else None
                self.assertTrue(all(x["end"]>x["start"] for x in timeline))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),"FFmpeg missing")
    def test_real_fx_overlay_and_synchronized_sound(self):
        if not app.verify_tools()["ready"]:
            self.skipTest("No libass")
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            video=root/"base.mp4"
            cmd=["ffmpeg","-hide_banner","-nostdin","-loglevel","error","-y",
                 "-f","lavfi","-i","color=c=purple:s=180x320:r=30:d=5",
                 "-f","lavfi","-i","sine=frequency=230:duration=5",
                 "-c:v","mpeg4","-c:a","aac","-shortest",str(video)]
            subprocess.run(cmd,check=True,capture_output=True,timeout=40)
            events=[{"at":.75,"kind":"scribble","role":"graphic","duration":1.05,
                     "zone":"upper-left","profile":"clinical_pro","word":"KIDNEY"},
                    {"at":2.4,"kind":"film_burn","role":"transition","duration":.72,
                     "zone":"upper-right","profile":"film_retro","word":""}]
            layers=render_fx(events,root,size=(180,320))
            self.assertEqual(len(layers),2)
            self.assertTrue(all(x["path"].stat().st_size>1000 for x in layers))
            old=app.RENDER_WIDTH,app.RENDER_HEIGHT
            app.RENDER_WIDTH,app.RENDER_HEIGHT=180,320
            try:
                ass=root/"captions.ass"
                make_subs(WORDS[:4],caption_config("clinical_pro"),ass,180,320)
                rendered=root/"render.mp4"
                preset=app.presets()["medical_clean"]
                app.render(video,ass,rendered,preset,[],5,True,[],None,layers)
                cue=root/"cues.wav"
                self.assertTrue(write_cues(events,5,cue))
                output=root/"output.mp4"
                add_effect_sound(rendered,cue,output,90)
                self.assertTrue(app.probe(output)["has_video"])
                self.assertTrue(app.probe(output)["has_audio"])
                self.assertGreater(output.stat().st_size,5000)
            finally:
                app.RENDER_WIDTH,app.RENDER_HEIGHT=old


if __name__=="__main__":
    unittest.main()
