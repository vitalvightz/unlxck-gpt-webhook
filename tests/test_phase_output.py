import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import unittest
from mental.main import build_plan_output

class PhaseRestrictionTest(unittest.TestCase):
    def test_selected_and_following_phases_rendered(self):
        drills = {
            "GPP": [
                {
                    "name": "GPP Drill",
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
            ],
            "SPP": [
                {
                    "name": "SPP Drill",
                    "description": "desc",
                    "cue": "cue",
                    "modalities": [],
                    "sports": [],
                    "intensity": "low",
                    "phase": "SPP",
                    "notes": "",
                    "raw_traits": [],
                    "theme_tags": [],
                }
            ],
            "UNIVERSAL": [
                {
                    "name": "Universal",
                    "description": "desc",
                    "cue": "",
                    "modalities": [],
                    "sports": [],
                    "intensity": "low",
                    "phase": "UNIVERSAL",
                    "notes": "",
                    "raw_traits": [],
                    "theme_tags": [],
                }
            ],
        }
        athlete = {
            "full_name": "Test Athlete",
            "sport": "boxing",
            "position_style": "style",
            "mental_phase": "SPP",
            "all_tags": [],
        }
        output = build_plan_output(drills, athlete)
        self.assertIn("SPP DRILLS", output)
        self.assertIn("SPP Drill", output)
        self.assertIn("TAPER DRILLS", output)
        self.assertIn("Universal", output)
        self.assertNotIn("GPP DRILLS", output)

    def test_gpp_renders_all_phases(self):
        drills = {
            "GPP": [{"name": "GPP", "description": "d", "cue": "", "modalities": [], "sports": [], "intensity": "low", "phase": "GPP", "notes": "", "raw_traits": [], "theme_tags": []}],
            "SPP": [{"name": "SPP", "description": "d", "cue": "", "modalities": [], "sports": [], "intensity": "low", "phase": "SPP", "notes": "", "raw_traits": [], "theme_tags": []}],
            "TAPER": [{"name": "TAPER", "description": "d", "cue": "", "modalities": [], "sports": [], "intensity": "low", "phase": "TAPER", "notes": "", "raw_traits": [], "theme_tags": []}],
        }
        athlete = {
            "full_name": "Test Athlete",
            "sport": "boxing",
            "position_style": "style",
            "mental_phase": "GPP",
            "all_tags": [],
        }
        output = build_plan_output(drills, athlete)
        self.assertIn("GPP DRILLS", output)
        self.assertIn("SPP DRILLS", output)
        self.assertIn("TAPER DRILLS", output)

if __name__ == "__main__":
    unittest.main()
