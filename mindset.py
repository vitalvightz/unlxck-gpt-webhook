# mindset.py

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
        "injury fear": ["injury", "hurt", "reinjure", "tear", "pain"],
        "pressure": ["pressure", "nerves", "stress", "expectation", "choke"],
        "attention": ["focus", "distracted", "adhd", "concentration", "mental lapse"]
    }

    for block, keywords in mental_blocks.items():
        if any(kw in text for kw in keywords):
            return block
    return "generic"

def mindset_module(phase: str, block_text: str):
    category = classify_mental_block(block_text)

    anchors = {
        "GPP": {
            "confidence": "Visualization + self-talk twice weekly",
            "gas tank": "Mindfulness and breath control during base conditioning",
            "injury fear": "Graded exposure imagery and joint protection routines",
            "pressure": "Journaling + ego audits weekly",
            "attention": "10-min focus drills post-training",
            "generic": "10-min mindfulness + visualization (2x/week)"
        },
        "SPP": {
            "confidence": "Pressure scenario visualisation + power pose rituals",
            "gas tank": "Hypoxic cue training + high-intensity visualisation",
            "injury fear": "Reinforcement journaling and coach affirmations",
            "pressure": "Simulation of fight-week pressure in gym scenarios",
            "attention": "Short cue-word resets mid-workout",
            "generic": "Advanced cue training + 1x performance visualisation"
        },
        "TAPER": {
            "confidence": "Daily self-affirmation + controlled ego rehearsal",
            "gas tank": "Mental walk-throughs of final rounds",
            "injury fear": "Focus only on positive reps + short term confidence anchors",
            "pressure": "Full fight run-through in mind nightly",
            "attention": "No-tech evenings + calming rituals",
            "generic": "Final week: cue focus + visualisation 1x/day"
        }
    }

    tool = anchors.get(phase.upper(), {}).get(category, "Basic mindset check-ins (2x/week)")
    return f"**Mindset Tool ({phase} Phase):** {tool}\n"