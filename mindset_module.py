# Upgraded mindset.py with expanded categories and personalized tools

mindset_bank = {
    "GPP": {
        "confidence": "Use future-self visualization and complete 1 small, measurable success daily to rebuild belief.",
        "gas tank": "Anchor slow nasal breathwork post-cardio, record HR drop time to reinforce progress.",
        "injury fear": "Set weekly exposure targets with graded contact drills and track pain-free sessions.",
        "pressure": "Reframe pressure as privilege via journaling; write 'why I'm prepared' before each session.",
        "attention": "Use pre-session mindfulness reps (3 mins breath + 1 min sensory) to train attentional control.",
        "motivation": "Start 'why log' (3x/week). Reconnect with deeper reasons to train.",
        "fear of losing": "Record 3 worst-case outcomes and evidence how you'd recover. Reduce emotional weight.",
        "fear of striking": "Shadowbox with relaxed breath for 3 rounds daily. Gradually build intent and aggression.",
        "fear of takedowns": "Integrate wall wrestling reps with fixed grip/entry drills. Isolate fear with control.",
        "generic": "Establish AM mental warm-up (1 min breathe, 3 affirmations, 1 visualization rep)."
    },
    "SPP": {
        "confidence": "Pressure-test during fatigue drills using cue words. Use post-rep success anchor statements.",
        "gas tank": "Rehearse high-effort exchanges visually before pad/sparring rounds. Reinforce 'stay calm' cues.",
        "injury fear": "Reinforce robustness with performance reflection. Keep a 'pain-free milestone' tracker.",
        "pressure": "Schedule 2 pressure simulations weekly. Use self-talk script post-scenario.",
        "attention": "Set distraction triggers before training (e.g. song or phrase). Rate focus each session.",
        "motivation": "Create 'fight wall' with goals + competitors. Use as a pre-training activation ritual.",
        "fear of losing": "Practice detachment: spar as if outcome doesn’t matter. Reflect after.",
        "fear of striking": "Use 'flow to fire' drill: start light, increase intensity across rounds. Focus on rhythm.",
        "fear of takedowns": "Introduce anti-takedown drills w/ cue focus. Visualize stuffing shot mid-fatigue.",
        "generic": "Visualize adversity (e.g. bad round, crowd noise, injury scare) and successful reaction."
    },
    "Taper": {
        "confidence": "Watch best clips + write 'evidence list' of preparation daily.",
        "gas tank": "Use calm affirmations: 'My lungs are ready'. Rehearse controlled exchanges in head.",
        "injury fear": "Repeat safe movement patterns daily with speed. Use mirror to reinforce smoothness.",
        "pressure": "Create 2x/day decompression rituals (music, walk, short breath set).",
        "attention": "Limit device input. Add pre-bed mind dump and 2-min breath sessions AM/PM.",
        "motivation": "Shift to service mindset: 'who do I fight for?' Anchor this in visual and verbal form.",
        "fear of losing": "Walkthrough fight in head while smiling. Practice identity detachment.",
        "fear of striking": "Visualize first strike exchange with sharpness and control. Repeat daily.",
        "fear of takedowns": "Rehearse quick sprawl or frame and reset. Reduce panic impulse with breath cue.",
        "generic": "3x/day ritual: breathe → affirm → visualize (short, sharp, elite imagery only)."
    }
}


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
        "injury fear": ["injury", "hurt", "reinjure", "scared to tear", "pain", "body won't hold"],
        "pressure": ["pressure", "nerves", "stress", "expectation", "choke", "stage fright"],
        "attention": ["focus", "distracted", "adhd", "concentration", "mental lapse"],
        "motivation": ["lazy", "can't be bothered", "no energy", "no motivation", "struggling to train"],
        "fear of losing": ["lose", "loss", "afraid to lose", "record", "undefeated", "winning"],
        "fear of striking": ["striking", "punch", "hit", "hurt when hit", "sparring fear"],
        "fear of takedowns": ["takedown", "shot", "wrestling", "thrown", "slammed"]
    }

    for block, keywords in mental_blocks.items():
        if any(kw in text for kw in keywords):
            return block

    return "generic"


def get_mindset_by_phase(phase, block):
    return mindset_bank.get(phase, {}).get(block, mindset_bank[phase]["generic"])