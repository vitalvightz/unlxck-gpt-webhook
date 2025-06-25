import unittest
from mental.map_mindcode_tags import map_mindcode_tags

class MapMindcodeTagsTest(unittest.TestCase):
    def test_basic_mapping(self):
        data = {
            "under_pressure": [
                "I hesitate before acting",
                "I feel calm and thrive under pressure",
            ],
            "post_mistake": ["I replay it over and over in my head"],
            "focus_breakers": ["The crowd / noise"],
            "confidence_profile": ["I train better than I perform"],
            "identity_traits": ["Confident", "Focused"],
            "elite_traits": ["Unshakeable focus", "Dominates under pressure"],
            "pressure_breath": "Hold my breath",
            "heart_response": "Spikes",
            "reset_duration": "Instantly",
            "motivator": "Small visible wins",
            "emotional_trigger": "Coach criticism",
            "past_mental_struggles": "",
        }
        tags = map_mindcode_tags(data)
        self.assertEqual(tags["under_pressure"], ["hesitate", "thrives"])
        self.assertEqual(tags["post_mistake"], ["mental_loop"])
        self.assertEqual(tags["focus_breakers"], ["focus_crowd"])
        self.assertEqual(tags["confidence_profile"], ["gym_performer"])
        self.assertEqual(tags["identity_traits"], ["trait_confident", "trait_focused"])
        self.assertEqual(tags["elite_traits"], ["elite_unshakeable_focus", "elite_dominates_under_pressure"])
        self.assertEqual(tags["breath_pattern"], "breath_hold")
        self.assertEqual(tags["hr_response"], "hr_up")
        self.assertEqual(tags["reset_speed"], "fast_reset")
        self.assertEqual(tags["motivation_type"], "reward_seeker")
        self.assertEqual(tags["threat_trigger"], "authority_threat")
        self.assertEqual(tags["mental_history"], "clear_history")

    def test_deduplication(self):
        data = {
            "under_pressure": ["I hesitate before acting", "I hesitate before acting"],
        }
        tags = map_mindcode_tags(data)
        self.assertEqual(tags["under_pressure"], ["hesitate"])

if __name__ == "__main__":
    unittest.main()
