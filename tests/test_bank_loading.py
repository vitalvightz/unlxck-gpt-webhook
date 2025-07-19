import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import unittest
from mental import main

class DrillBankLoadTest(unittest.TestCase):
    def test_merged_bank_length(self):
        self.assertEqual(len(main.DRILL_BANK), 148)

if __name__ == "__main__":
    unittest.main()
