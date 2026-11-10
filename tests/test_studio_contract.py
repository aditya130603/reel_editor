"""Verify studio API registration and upload constraints without a live VPS."""
import unittest
import app
from studio_pipeline import CLIP_TRANSITIONS, TITLE_EFFECTS


class StudioAPIContract(unittest.TestCase):
    def test_editor_root_and_routes_registered(self):
        paths = {r.path for r in app.app.routes}
        for route in (
            "/", "/api/studio/options", "/api/studio/jobs",
            "/api/studio/assets", "/api/admin/busy", "/api/jobs/{job_id}"
        ):
            self.assertIn(route, paths)

    def test_critical_options(self):
        self.assertIn("fade", CLIP_TRANSITIONS)
        self.assertIn("cut", CLIP_TRANSITIONS)
        self.assertIn("editorial", TITLE_EFFECTS)
        self.assertIn("poster", TITLE_EFFECTS)

    def test_safe_upload_resource_limit(self):
        self.assertGreater(app.MAX_UPLOAD_MB, 0)
        self.assertGreater(app.FFMPEG_TIMEOUT, 60)


if __name__ == "__main__":
    unittest.main()
