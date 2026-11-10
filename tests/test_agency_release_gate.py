"""Final acceptance gates before allowing an agency preset release."""
import tempfile
import unittest
from pathlib import Path

from agency_director import PROFILES,plan
from agency_captions import make_subs


class ReleaseContracts(unittest.TestCase):
    def test_one_preset_user_interface(self):
        html=(Path(__file__).resolve().parents[1]/"static"/"studio.html").read_text()
        self.assertEqual(html.count('class="preset"')+html.count('class="preset selected"'),4)
        self.assertIn("agency_preset",html)
        self.assertNotIn("id=\"motionpack\"",html)
        self.assertNotIn("id=\"caption-style\"",html)

    def test_preset_fx_are_not_repeated_on_adjacent_beats(self):
        words=[{"start":float(i)+.2,"end":float(i)+.45,"text":"Important"}
               for i in range(60)]
        for key in PROFILES:
            cues=plan(words,60,key)
            self.assertGreaterEqual(len(cues),5)
            self.assertNotEqual(cues[0]["kind"],cues[1]["kind"])

    def test_real_caption_underlays_generated(self):
        words=[{"start":.3,"end":.7,"text":"Kidney"},
               {"start":.75,"end":1.1,"text":"treatment"}]
        for style in ("clinical_box","paper_tape"):
            with self.subTest(style=style),tempfile.TemporaryDirectory() as d:
                p=Path(d)/"caption.ass"
                make_subs(words,{"caption":style,"size":52,"palette":["#6AE0D4"]},
                          p,720,1280)
                text=p.read_text()
                self.assertIn(r"\p1",text)
                self.assertIn("Dialogue: 1,",text)
                self.assertNotIn(r"{\\r}",text)

if __name__=="__main__":
    unittest.main()
