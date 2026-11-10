import unittest
import agency_fx

class MotionFrameRateTest(unittest.TestCase):
    def test_agency_motion_is_smooth(self):
        self.assertGreaterEqual(agency_fx.FPS,24)

if __name__ == "__main__":
    unittest.main()
