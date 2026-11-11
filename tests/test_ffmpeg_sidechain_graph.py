"""Regression: FFmpeg audio filter pads cannot be consumed twice.

Ubuntu 24.04 / FFmpeg 6.1 rejects reuse of [voice] for both
sidechaincompress and amix. The mixer must fan out with asplit.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import studio_pipeline


class SidechainGraphTest(unittest.TestCase):
    def test_ducking_uses_two_distinct_voice_outputs(self):
        captured = []
        with patch.object(studio_pipeline, "run", side_effect=lambda args, timeout: captured.append(args)):
            studio_pipeline.mix_music(Path("video.mp4"), Path("music.wav"), Path("output.mp4"), .10)
        args = captured[0]
        graph = args[args.index("-filter_complex") + 1]
        self.assertIn("asplit=2[voice_main][voice_detector]", graph)
        self.assertIn("[bed][voice_detector]sidechaincompress=", graph)
        self.assertIn("[voice_main][duck]amix=", graph)
        self.assertNotIn("[bed][voice]sidechaincompress", graph)

if __name__ == "__main__":
    unittest.main()
