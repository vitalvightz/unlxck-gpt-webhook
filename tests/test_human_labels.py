import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import unittest
from mental.main import build_plan_output

class HumanLabelOutputTest(unittest.TestCase):
    def test_tags_humanized(self):
        drills = {
            "GPP": [
                {
                    "name": "Test Drill",
                    "description": "desc",
                    "cue": "cue",
                    "modalities": [],
                    "sports": [],
                    "intensity": "low",
                    "phase": "GPP",
                    "notes": "",
                    "raw_traits": ["hesitate"],
                    "theme_tags": ["decide_freeze", "hr_up"],
                }
            ]
        }
        athlete = {
            "full_name": "Test Athlete",
            "sport": "boxing",
            "position_style": "style",
            "mental_phase": "GPP",
            "all_tags": [],
        }
        output = build_plan_output(drills, athlete)
        self.assertIn("Hesitates Under Pressure", output)
        self.assertIn("Freezes Under Choice", output)
        self.assertIn("Heart Rate Spikes", output)
        self.assertNotIn("hr_up", output)

if __name__ == "__main__":
    unittest.main()
