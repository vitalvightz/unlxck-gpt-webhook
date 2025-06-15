from rapidfuzz import fuzz
import spacy

# load large English model once
nlp = spacy.load("en_core_web_lg")

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
        "fear of losing": "Practice detachment: spar as if outcome doesn't matter. Reflect after.",
        "fear of striking": "Use 'flow to fire' drill: start light, increase intensity across rounds. Focus on rhythm.",
        "fear of takedowns": "Introduce anti-takedown drills w/ cue focus. Visualize stuffing shot mid-fatigue.",
        "generic": "Visualize adversity (e.g. bad round, crowd noise, injury scare) and successful reaction."
    },
    "TAPER": {
        "confidence": "Watch best clips + write 'evidence list' of preparation daily.",
        "gas tank": "Use calm affirmations: 'My lungs are ready'. Rehearse controlled exchanges in head.",
        "injury fear": "Repeat safe movement patterns daily with speed. Use mirror to reinforce smoothness.",
        "pressure": "Create 2x/day decompression rituals (music, walk, short breath set).",
        "attention": "Limit device input. Add pre-bed mind dump and 2-min breath sessions AM/PM.",
        "motivation": "Shift to service mindset: 'who do I fight for?' Anchor this in visual and verbal form.",
        "fear of losing": "Walkthrough fight in head while smiling. Practice identity detachment.",
        "fear of striking": "Visualize first strike exchange with sharpness and control. Repeat daily.",
        "fear of takedowns": "Rehearse quick sprawl or frame and reset. Reduce panic impulse with breath cue.",
        "generic": "3x/day ritual: breathe → affirm → visualize (short, sharp, elite imagery only).",
        "pre-fight_activation": "Quick neural warm-up + 3 power breaths (6s inhale/10s exhale). Cue phrase 'I'm sharp' before walkout."
    }
}

mental_blocks = {
    "confidence": [
        "confid", "doubt", "belie", "impost", "insecure", "hesita", 
        "unsure", "timid", "shak", "unworthy", "sabotage", "incapable", 
        "inferior", "fraud", "fragile", "phony", "uncertain", "cautious", 
        "wavering", "crash", "pretend", "fail", "inadequate", "edge", "depth"
    ],
    "gas tank": [
        "gas", "cardi", "tire", "fade", "gassed", "condition", "exhaust", 
        "wind", "burn", "empty", "stamin", "breath", "heavy", "energ", 
        "wall", "drain", "spent", "weary", "fatigue", "zap", "unfit", 
        "overtrain", "dehydrate", "muscle", "sustain", "collapse", "pace"
    ],
    "injury fear": [
        "injur", "hurt", "pain", "tear", "reinjur", "body", "fragile", 
        "protect", "nag", "damage", "health", "glass", "vulnerable", 
        "heal", "twinge", "strain", "snap", "break", "limit", "favor", 
        "paranoid", "betray", "surgery", "trauma", "chronic", "worry", 
        "brittle", "compensate", "flinch", "anticipate", "avoid", "contact"
    ],
    "pressure": [
        "pressure", "nerve", "stress", "expect", "choke", "stage", 
        "overwhelm", "burden", "spotlight", "heat", "froze", "tight", 
        "analysis", "overthink", "crack", "fold", "moment", "disappoint", 
        "terror", "stake", "clutch", "failure", "judgment", "perfect", 
        "anxiety", "freez", "exposure", "shaky", "audience", "legacy", 
        "contract", "rank", "title", "break", "perform", "count", "blank"
    ],
    "attention": [
        "focus", "distract", "adhd", "concentrat", "lapse", "zone",
        "wander", "scatter", "overstim", "crowd", "noise", "trash",
        "personal", "emotional", "overload", "indecisive", "slow",
        "forget", "space", "deficit", "sensory", "thought", "lock",
        "sidetrack", "clarity", "fog", "brain", "decide", "fatigue",
        "aware", "opponent", "track", "chaotic", "sloppy", "mistake",
        "rush", "impulsive", "gameplan", "absent", "daydream", "unaware",
        "zoning", "zoned", "zoned out", "spacey", "dizzy", "spinning"
    ],
    "motivation": [
        "lazy", "bother", "energy", "motivat", "train", "inspire", 
        "motion", "procrastinate", "gym", "alarm", "discipline", 
        "burnout", "passion", "why", "drive", "stale", "indifferent", 
        "apathetic", "job", "dread", "practice", "excuse", "skip", 
        "rep", "effort", "autopilot", "fire", "spark", "purpose", 
        "empty", "detach", "isolate", "coach", "pity", "victim", 
        "goal", "direction", "potential", "regret"
    ],
    "fear of losing": [
        "lose", "loss", "afraid", "record", "undefeat", "win", 
        "streak", "legacy", "embarrass", "humiliat", "failure", 
        "exposure", "perfect", "stat", "rank", "contract", "sponsor", 
        "media", "critic", "fan", "respect", "teammate", "disapprove", 
        "shame", "social", "hate", "decline", "wash", "prime", 
        "irrelevant", "hype", "average", "pity", "identity"
    ],
    "fear of striking": [
        "strike", "punch", "hit", "hurt", "spar", "flinch", 
        "headshot", "terror", "chin", "glass", "jaw", "cut", 
        "swell", "panic", "concuss", "brain", "damage", "anticipate", 
        "shell", "cover", "combo", "power", "puncher", "phobia", 
        "counter", "anxiety", "exchange", "knee", "trauma", "body", 
        "liver", "nose", "break", "orbital", "fracture", "blood", 
        "freeze", "retreat"
    ],
    "fear of takedowns": [
        "takedown", "shot", "wrestle", "throw", "slam", "grapple",
        "ground", "panic", "position", "helpless", "submit", "dread",
        "control", "smother", "claustro", "mat", "return", "trauma",
        "slam", "anxiety", "suplex", "terror", "spinal", "neck",
        "shoulder", "reinjur", "knee", "pop", "stack", "guard",
        "pass", "pound", "fence", "cage", "pace", "scramble",
        "turtle", "clinch", "sprawl"
    ]
}


def semantic_match_block(text: str, threshold: float = 0.78) -> str:
    """Use spaCy embeddings to match unknown input to nearest mental block category."""
    if not text.strip():
        return "generic"

    doc_input = nlp(text.strip().lower())
    best_block = "generic"
    best_score = 0.0

    for block in mental_blocks.keys():
        doc_block = nlp(block)
        similarity = doc_input.similarity(doc_block)
        if similarity > best_score:
            best_block = block
            best_score = similarity
    return best_block if best_score >= threshold else "generic"

def classify_mental_block(text: str, top_n: int = 2, threshold: int = 85) -> list:
    """Classify the mental block using fuzzy matching and fallback to semantic similarity."""
    if not text or not isinstance(text, str):
        return ["generic"]

    text = text.lower().strip()
    # treat short negative replies as generic
    if text in {"no", "nope", "nah", "n/a", "none", "na", "idk"}:
        return ["generic"]

    scores = {}
    for block, keywords in mental_blocks.items():
        match_count = 0
        for kw in keywords:
            if kw in text or fuzz.partial_ratio(kw, text) >= threshold:
                match_count += 1
        if match_count:
            scores[block] = match_count

    if scores:
        sorted_blocks = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_blocks = [block for block, _ in sorted_blocks[:top_n]]
        return top_blocks

    # Fallback: semantic similarity
    fallback_block = semantic_match_block(text)
    return [fallback_block]

def get_mindset_by_phase(phase: str, flags: dict) -> str:
    """Get a brief mindset strategy for top blocks in this phase."""
    blocks = flags.get("mental_block", ["generic"])
    if isinstance(blocks, str):
        blocks = [blocks]

    phase = phase.upper()
    output_lines = []

    for block in blocks:
        tip = mindset_bank.get(phase, {}).get(block, mindset_bank[phase].get("generic", "Stay focused."))
        output_lines.append(f"**{block.title()}** → {tip}")

    if phase == "TAPER":
        activation = mindset_bank.get("TAPER", {}).get("pre-fight_activation")
        if activation:
            output_lines.append(f"**Pre-Fight Activation** → {activation}")

    return "\n\n".join(output_lines)

def get_mental_protocols(blocks: list) -> str:
    """Return full mindset training protocols across GPP → SPP → TAPER."""
    if isinstance(blocks, str):
        blocks = [blocks]

    sections = [f"# Mental Block Strategy: {', '.join(b.title() for b in blocks)}\n"]

    for phase in ["GPP", "SPP", "TAPER"]:
        phase_lines = [f"## {phase}"]
        for block in blocks:
            entry = mindset_bank.get(phase, {}).get(block, mindset_bank[phase]["generic"])
            phase_lines.append(f"**{block.title()}** → {entry}")
        if phase == "TAPER":
            activation = mindset_bank.get("TAPER", {}).get("pre-fight_activation")
            if activation:
                phase_lines.append(f"**Pre-Fight Activation** → {activation}")
        sections.append("\n".join(phase_lines))

    return "\n\n".join(sections)

def get_phase_mindset_cues(blocks) -> dict:
    """Return a short cue per phase based on top mental blocks."""
    if isinstance(blocks, str):
        blocks = [blocks]
    blocks = blocks[:2] if blocks else ["generic"]

    cues = {}
    for phase in ["GPP", "SPP", "TAPER"]:
        tips = []
        for block in blocks:
            tip = mindset_bank.get(phase, {}).get(block, mindset_bank[phase]["generic"])
            tips.append(f"{block.title()}: {tip}")
        cues[phase] = " | ".join(tips)
    return cues
    