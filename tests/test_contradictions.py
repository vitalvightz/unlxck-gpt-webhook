import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import unittest

from mental.contradictions import detect_contradictions
from mental.main import build_plan_output

class ContradictionDetectionTest(unittest.TestCase):
    def test_detects_pair(self):
        tags = {"decision_making:decide_fast", "overthink_type:overthinker"}
        notes = detect_contradictions(tags)
        self.assertTrue(any("overthinks under pressure" in n for n in notes))

    def test_no_contradiction(self):
        tags = {"decision_making:decide_fast", "overthink_type:decisive"}
        self.assertEqual(detect_contradictions(tags), [])

class PlanInjectionTest(unittest.TestCase):
    def test_injects_coach_note(self):
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
                    "raw_traits": [],
                    "theme_tags": [],
                }
            ]
        }
        athlete = {
            "full_name": "Test Athlete",
            "sport": "boxing",
            "position_style": "style",
            "mental_phase": "GPP",
            "all_tags": ["decision_making:decide_fast", "overthink_type:overthinker"],
        }
        text = build_plan_output(drills, athlete)
        self.assertIn("COACH REVIEW FLAGS", text)

if __name__ == "__main__":
    unittest.main()
