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
        self.assertAlmostEqual(score_drill(drill, [], "GPP", athlete), 0.8)
        self.assertAlmostEqual(score_drill(drill, [], "TAPER", athlete), 0.5)

    def test_intensity_penalty_skipped_for_fighters(self):
        drill = {"intensity": "high", "raw_traits": [], "modalities": []}
        athlete = {"sport": "mma", "in_fight_camp": True}
        self.assertAlmostEqual(score_drill(drill, [], "GPP", athlete), 1.0)

    def test_elite_trait_synergy_penalty(self):
        drill = {"intensity": "medium", "raw_traits": ["ruthless"], "modalities": ["focus drill"]}
        athlete = {"sport": "football", "in_fight_camp": False}
        self.assertAlmostEqual(score_drill(drill, [], "SPP", athlete), 0.8)
        drill2 = {"intensity": "medium", "raw_traits": ["commanding"], "modalities": ["visualisation", "breathwork"]}
        self.assertAlmostEqual(score_drill(drill2, ["thrives"], "SPP", athlete), 1.0)

if __name__ == "__main__":
    unittest.main()
