import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import unittest
from mental.main import bucket_drills_by_phase

class BucketDrillsTest(unittest.TestCase):
    def test_universal_kept_separate(self):
        drills = [
            {"phase": "UNIVERSAL", "score": 1},
            {"phase": "GPP", "score": 2},
        ]
        buckets = bucket_drills_by_phase(drills)
        self.assertEqual(len(buckets["GPP"]), 1)
        self.assertEqual(len(buckets["UNIVERSAL"]), 1)
        self.assertEqual(len(buckets["SPP"]), 0)

if __name__ == "__main__":
    unittest.main()
