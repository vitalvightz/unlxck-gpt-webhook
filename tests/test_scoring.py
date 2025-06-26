import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import unittest
from mental.scoring import check_synergy_match, score_drill

class ScoringTests(unittest.TestCase):
    def test_check_synergy_match(self):
        drill = {"modalities": ["visualisation", "breathwork"]}
        self.assertTrue(check_synergy_match(drill, ["quick_reset"]))
        self.assertFalse(check_synergy_match(drill, ["overthink"]))
        drill2 = {"modalities": ["visualisation"]}
        self.assertFalse(check_synergy_match(drill2, ["quick_reset"]))

    def test_phase_intensity_penalty(self):
        drill = {"intensity": "high", "raw_traits": [], "modalities": []}
        athlete = {"sport": "football", "in_fight_camp": False}
        self.assertAlmostEqual(score_drill(drill, "GPP", athlete), 0.8)
        self.assertAlmostEqual(score_drill(drill, "TAPER", athlete), 0.4)

    def test_intensity_penalty_skipped_for_fighters(self):
        drill = {"intensity": "high", "raw_traits": [], "modalities": []}
        athlete = {"sport": "mma", "in_fight_camp": True}
        self.assertAlmostEqual(score_drill(drill, "GPP", athlete), 1.0)

    def test_elite_trait_synergy_penalty(self):
        drill = {"intensity": "medium", "raw_traits": ["ruthless"], "modalities": ["focus drill"]}
        athlete = {"sport": "football", "in_fight_camp": False, "tags": []}
        self.assertAlmostEqual(score_drill(drill, "SPP", athlete), 1.5)
        drill2 = {"intensity": "medium", "raw_traits": ["commanding"], "modalities": ["visualisation", "breathwork"]}
        athlete_synergy = {"sport": "football", "in_fight_camp": False, "tags": ["thrives"]}
        self.assertAlmostEqual(score_drill(drill2, "SPP", athlete_synergy), 1.7)

    def test_multiple_elite_trait_penalty(self):
        drill = {"intensity": "medium", "raw_traits": ["ruthless", "commanding"], "modalities": ["focus drill"]}
        athlete = {"sport": "football", "in_fight_camp": False, "tags": []}
        self.assertAlmostEqual(score_drill(drill, "SPP", athlete), 2.0)

    def test_theme_tag_and_sport_bonus(self):
        drill = {
            "theme_tags": ["fast_reset", "breath_hold"],
            "sports": ["mma"],
            "phase": "SPP",
            "intensity": "medium",
            "raw_traits": [],
            "modalities": [],
        }
        athlete = {
            "sport": "mma",
            "in_fight_camp": False,
            "tags": ["fast_reset", "breath_hold", "other"],
        }
        # 1.0 base +0.5 phase match +0.3 sport match -0.1 overload = 1.7
        self.assertAlmostEqual(score_drill(drill, "SPP", athlete), 1.7)

    def test_weakness_and_reinforcement_bonus(self):
        drill = {
            "theme_tags": ["overthink"],
            "modalities": ["visualisation"],
            "intensity": "medium",
            "phase": "GPP",
            "raw_traits": [],
            "sports": [],
        }
        athlete = {
            "sport": "football",
            "in_fight_camp": False,
            "weakness_tags": ["overthink"],
            "preferred_modality": ["visualisation"],
        }
        # 1.0 base +0.5 phase +0.15 weakness +0.1 reinforcement = 1.75
        self.assertAlmostEqual(score_drill(drill, "GPP", athlete), 1.75)

    def test_overload_penalty(self):
        drill = {
            "theme_tags": ["breath_hold"],
            "modalities": [],
            "intensity": "high",
            "phase": "GPP",
            "raw_traits": [],
            "sports": [],
        }
        athlete = {
            "sport": "football",
            "in_fight_camp": False,
            "tags": ["breath_hold"],
        }
        # Base 1.0 -0.5 taper penalty -0.2 overload = 0.3
        self.assertAlmostEqual(score_drill(drill, "TAPER", athlete), 0.3)

if __name__ == "__main__":
    unittest.main()
