import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import unittest
from mental.tags import map_tags

class MapTagsPreferredStruggleTest(unittest.TestCase):
    def test_preferred_modality_and_struggles(self):
        data = {
            "tool_preferences": ["Breathwork", "Visualisation"],
            "key_struggles": ["Overthinking", "Emotional reactions"],
        }
        tags = map_tags(data)
        self.assertEqual(tags["preferred_modality"], ["pref_breathwork", "pref_visualisation"])
        self.assertEqual(tags["struggles_with"], ["overthink", "emotional"])

    def test_deduplication(self):
        data = {
            "tool_preferences": ["Breathwork", "Breathwork"],
            "key_struggles": ["Overthinking", "Overthinking"],
        }
        tags = map_tags(data)
        self.assertEqual(tags["preferred_modality"], ["pref_breathwork"])
        self.assertEqual(tags["struggles_with"], ["overthink"])

if __name__ == "__main__":
    unittest.main()
