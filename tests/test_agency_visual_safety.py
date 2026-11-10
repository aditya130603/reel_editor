"""Rendering layout contracts: never place decorative callouts over a center face."""
import re
import tempfile
import unittest
from pathlib import Path

from agency_captions import make_subs
from agency_director import PROFILES
from agency_fx import make_frame


class AgencyVisualSafety(unittest.TestCase):
    def test_callout_pixels_stay_in_side_gutters(self):
        for kind in ("scribble","click","diagram_lines","sticker"):
            for zone in ("upper-left","upper-right"):
                with self.subTest(kind=kind,zone=zone):
                    cue={"kind":kind,"zone":zone,"word":"YES",
                         "at":2,"profile":"clinical_pro"}
                    image=make_frame(cue,.6,360,640)
                    # Face-safe central band at eye/forehead height:
                    center=image.getchannel("A").crop((119,70,241,280))
                    self.assertIsNone(center.getbbox(),
                                      f"{kind} intersects central face band")

    def test_each_caption_phrase_has_at_most_two_bounded_lines(self):
        words=[
            {"start":.3+i*.22,"end":.49+i*.22,"text":w}
            for i,w in enumerate(["Endometriosis","surgery","requires",
                                   "specialized","clinical","experience",
                                   "and","careful","recovery."])
        ]
        for preset in PROFILES:
            with self.subTest(preset=preset),tempfile.TemporaryDirectory() as d:
                ass=Path(d)/"captions.ass"
                timeline=make_subs(words, {
                    "caption":PROFILES[preset]["caption"],
                    "size":PROFILES[preset]["size"],
                    "palette":PROFILES[preset]["palette"]
                },ass,720,1280)
                self.assertTrue(timeline)
                body=ass.read_text()
                for line in body.splitlines():
                    if line.startswith("Dialogue:") and "\\p1" not in line:
                        self.assertLessEqual(line.count(r"\N"),1)
                self.assertNotIn("Style: Main,DejaVu Sans,120",body)


if __name__=="__main__":
    unittest.main()
