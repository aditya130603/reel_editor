"""Release regression for job persistence used by the GitHub auto-sync timer."""
import tempfile
import unittest
from pathlib import Path

import app


class PersistentStudioJob(unittest.TestCase):
    def test_job_survives_service_restart(self):
        previous_data, previous_jobs = app.DATA, app.jobs
        with tempfile.TemporaryDirectory() as d:
            try:
                app.DATA = Path(d)
                jobid = "1234567890abcdef1234567890abcdef"
                (app.DATA / jobid).mkdir()
                app.jobs = {jobid: {"id": jobid, "state": "rendering"}}
                app.status(jobid, state="completed", url=f"/api/jobs/{jobid}/download")
                app.jobs = {}
                restored = app.get_job(jobid)
                self.assertEqual(restored["state"], "completed")
                self.assertTrue((app.DATA / jobid / "job.json").is_file())
            finally:
                app.DATA, app.jobs = previous_data, previous_jobs


if __name__ == "__main__":
    unittest.main()
