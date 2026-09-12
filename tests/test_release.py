import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from omarchy import Error, check_release

class ReleaseTests(unittest.TestCase):
    def report(self, profile, image="tested", passed=True):
        return {"profile": profile, "image_id": image, "passed": passed}

    def test_changed_image_cannot_be_published(self):
        with self.assertRaisesRegex(Error, "image changed"):
            check_release({"image_id": "tested"}, "rebuilt", [self.report("light"), self.report("standard")])

    def test_other_images_smoke_does_not_count(self):
        with self.assertRaisesRegex(Error, "both light and standard"):
            check_release({"image_id": "tested"}, "tested", [self.report("light"), self.report("standard", "older")])

    def test_failed_smoke_does_not_authorize_publication(self):
        with self.assertRaisesRegex(Error, "both light and standard"):
            check_release({"image_id": "tested"}, "tested", [self.report("light"), self.report("standard", passed=False)])

    def test_both_profiles_allow_the_exact_tested_image(self):
        check_release({"image_id": "tested"}, "tested", [self.report("light"), self.report("standard")])
