import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import unittest
from mental.program import parse_mindcode_form

class ParseMindcodeFormTest(unittest.TestCase):
    def test_basic_fields_parsed(self):
        data = {
            "Full name": "Jane Doe",
            "Age": "23",
            "Sport": "Basketball",
            "Position/Style": "Point Guard",
            "Where are you at in your performance cycle?": "I\u2019m rebuilding, resetting, or in off-season",
            "How do you usually make decisions during performance? (Pick one)": "I act instantly and trust my instincts",
        }
        result = parse_mindcode_form(data)
        self.assertEqual(result["full_name"], "Jane Doe")
        self.assertEqual(result["age"], "23")
        self.assertEqual(result["sport"], "Basketball")
        self.assertEqual(result["position_style"], "Point Guard")
        self.assertEqual(result["mental_phase"], "GPP")
        self.assertEqual(result["decision_making"], "I act instantly and trust my instincts")

if __name__ == "__main__":
    unittest.main()
