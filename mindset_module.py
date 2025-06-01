def classify_mental_block(block_text):
    if not block_text or not isinstance(block_text, str):
        return "generic"

    text = block_text.lower().strip()
    non_answers = ["n/a", "none", "nothing", "idk", "not sure", "no", "skip", "na"]
    if any(phrase in text for phrase in non_answers) or len(text.split()) < 2:
        return "generic"

    mental_blocks = {
        "confidence": ["confidence", "doubt", "self-belief", "don't believe", "imposter"],
        "gas tank": ["gas", "cardio", "tired", "fade", "gassed", "conditioning"],
        "injury fear": ["injury", "hurt", "reinjure", "scared to tear", "pain"],
        "pressure": ["pressure", "nerves", "stress", "expectation", "choke"],
        "attention": ["focus", "distracted", "adhd", "concentration", "mental lapse"]
    }

    for block, keywords in mental_blocks.items():
        if any(kw in text for kw in keywords):
            return block

    return "generic"


def get_mindset_by_phase(phase, block):
    mindset_bank = {
        "GPP": {
            "confidence": "Use visualization + foundational wins to build belief.",
            "gas tank": "Anchor breathwork post-session to gain control.",
            "injury fear": "Set technical goals with light contact to rebuild confidence.",
            "pressure": "Journaling + goal reframing to remove outcome obsession.",
            "attention": "Use mindfulness reps before sessions to sharpen focus.",
            "generic": "Establish morning visualizations + baseline affirmations."
        },
        "SPP": {
            "confidence": "Pressure-test with cue words during fatigue blocks.",
            "gas tank": "Visualize executing under pressure, reinforce with cue words.",
            "injury fear": "Layer intensity gradually. Affirm pain-free milestones.",
            "pressure": "Use high-pressure sparring to simulate and reframe nerves.",
            "attention": "Eliminate distractions pre-session. Use short breath resets.",
            "generic": "Refine visualizations to include adversity & setbacks."
        },
        "Taper": {
            "confidence": "Daily affirmations + clips of peak training moments.",
            "gas tank": "Mental rehearsal of pacing and control under fatigue.",
            "injury fear": "Visualization of smooth performance with no reinjury.",
            "pressure": "Pre-fight relaxation scripts. Walkthrough routines daily.",
            "attention": "Set pre-fight focus rituals. Limit external inputs.",
            "generic": "Reinforce calm, clarity, and confidence through daily reps."
        }
    }
    return mindset_bank.get(phase, {}).get(block, mindset_bank[phase]["generic"])