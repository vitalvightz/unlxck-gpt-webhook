from __future__ import annotations

import importlib.util
import re
from collections import Counter
from difflib import SequenceMatcher

_RAPIDFUZZ_AVAILABLE = importlib.util.find_spec("rapidfuzz") is not None

__all__ = [
    "classify_mental_block",
    "get_phase_mindset_cues",
    "get_mindset_by_phase",
]

try:  # pragma: no cover - optional dependency
    if _RAPIDFUZZ_AVAILABLE:
        from rapidfuzz import fuzz
    else:
        raise ImportError
except Exception:  # pragma: no cover - fallback when rapidfuzz missing/invalid
    class _FuzzFallback:
        @staticmethod
        def partial_ratio(a: str, b: str) -> int:
            return int(SequenceMatcher(None, a, b).ratio() * 100)

    fuzz = _FuzzFallback()

BLOCK_PRIORITY = [
    "confidence",
    "gas tank",
    "injury fear",
    "pressure",
    "attention",
    "motivation",
    "fear of takedowns",
    "rushing",
    "breath control",
    "composure",
    "generic",
]

BLOCK_KEYWORDS = {
    "confidence": [
        "confidence",
        "self belief",
        "self-belief",
        "belief",
        "self doubt",
        "self-doubt",
        "insecure",
        "hesitant",
    ],
    "gas tank": [
        "gas tank",
        "cardio",
        "conditioning",
        "stamina",
        "gassing",
        "tired",
        "fatigue",
        "winded",
    ],
    "injury fear": [
        "injury fear",
        "fear of injury",
        "reinjury",
        "re-injury",
        "pain",
        "getting hurt",
    ],
    "pressure": [
        "pressure",
        "performance anxiety",
        "big stage",
        "expectations",
        "nerves",
        "stress",
    ],
    "attention": [
        "attention",
        "focus",
        "concentration",
        "distracted",
        "mind wandering",
    ],
    "motivation": [
        "motivation",
        "drive",
        "discipline",
        "consistency",
        "commitment",
        "burnout",
        "burned out",
        "procrastination",
    ],
    "fear of takedowns": [
        "fear of takedowns",
        "fear of takedown",
        "takedown defense",
        "takedown threat",
        "sprawl",
        "wrestling defense",
        "wrestling threat",
        "grappling defense",
        "grappling threat",
        "clinch defense",
        "clinch threat",
        "ground game",
        "cage wrestling",
        "wall wrestling",
    ],
    "rushing": [
        "rushing",
        "rushes",
        "rushed",
        "hurrying",
        "hurried",
        "frantic",
        "frenzied",
        "panicked exchanges",
        "chaotic pace",
        "fast pace",
        "too fast",
        "speed up",
        "sped up",
        "speeds up",
        "get it back",
        "getting it back",
        "trying to get it back",
        "chase",
        "chasing",
    ],
    "breath control": [
        "breath control",
        "breathing",
        "breathwork",
        "breath",
        "loses breath",
        "out of breath",
        "holding breath",
        "shallow breathing",
        "rapid breathing",
        "hyperventilating",
        "respiratory",
        "nasal breathing",
    ],
    "composure": [
        "composure",
        "loses composure",
        "lost composure",
        "losing composure",
        "emotional control",
        "calm",
        "calmness",
        "staying calm",
        "keep cool",
        "cool head",
        "level headed",
        "level-headed",
        "rattled",
        "flustered",
        "overwhelmed",
        "falls apart",
        "unravels",
    ],
}

MINDSET_BANK = {
    "GPP": {
        "confidence": "Track one daily win and visualize the first exchange before each session.",
        "gas tank": "Use nasal breathing warm-ups and log recovery time to reinforce progress.",
        "injury fear": "Set graded exposure targets and celebrate pain-free rep quality.",
        "pressure": "Reframe pressure as preparation: write one sentence on why you are ready.",
        "attention": "Use a single-word cue before each set to lock attention on the task.",
        "motivation": "Commit to a non-negotiable warm-up ritual to build consistency.",
        "fear of takedowns": "Spend 5 minutes on level-change awareness and reset calmly after each rep.",
        "rushing": "Practice resetting to stance after each combination; count to 2 before re-engaging.",
        "breath control": "Establish nasal breathing baseline during warm-ups; exhale fully on power shots.",
        "composure": "Build a pre-round reset routine: shoulders down, jaw loose, deep exhale before engaging.",
        "generic": "Pick a simple daily intention and review one win after each session.",
    },
    "SPP": {
        "confidence": "Simulate competition pace and finish with a confidence recap of best rounds.",
        "gas tank": "Anchor hard efforts with controlled recovery breathing between rounds.",
        "injury fear": "Trust the plan: emphasize crisp technique and controlled intensity.",
        "pressure": "Use pre-round routines to quiet noise and focus on one controllable goal.",
        "attention": "Limit cues to one technical focus per round to avoid overload.",
        "motivation": "Visualize the fight night outcome and connect it to today's work.",
        "fear of takedowns": "Rehearse calm defense entries and reset posture before each exchange.",
        "rushing": "After clean shots, deliberately reset to stance instead of chasing; use 'breathe-reset' cue.",
        "breath control": "Practice round-rhythm breathing: exhale on strikes, nasal recovery between exchanges.",
        "composure": "Implement post-exchange check-in: check jaw, shoulders, breathing before next engagement.",
        "generic": "Train with a clear performance cue and keep the focus on execution quality.",
    },
    "TAPER": {
        "confidence": "Review highlight moments and rehearse the opening sequence with calm breathwork.",
        "gas tank": "Prioritize relaxation between efforts and trust the base you built.",
        "injury fear": "Stay precise and light; reinforce trust in healthy movement.",
        "pressure": "Keep routines simple and rehearse calm starts to protect composure.",
        "attention": "Use short, quiet breathing to center attention before sessions.",
        "motivation": "Reconnect with why you fight and keep sessions short and sharp.",
        "fear of takedowns": "Visualize clean defense triggers and smooth resets without rushing.",
        "rushing": "Visualize taking clean shots and resetting calmly; rehearse patience between combinations.",
        "breath control": "Keep breathing smooth and relaxed; practice calm exhales during light sparring.",
        "composure": "Rehearse your reset ritual: calm breath, loose jaw, ready stance before each round.",
        "generic": "Keep cues simple, visualize the opening exchange, and stay calm.",
    },
}

PHASE_CUE_BANK = {
    "GPP": {
        "confidence": "Build belief through small daily wins.",
        "gas tank": "Prioritize aerobic patience and steady breathing.",
        "injury fear": "Focus on safe movement quality and gradual exposure.",
        "pressure": "Treat sessions as practice reps under light stress.",
        "attention": "Stay present with one cue per set.",
        "motivation": "Keep momentum with consistent routines.",
        "fear of takedowns": "Stay calm on level changes and reset posture.",
        "rushing": "Practice deliberate resets between combinations.",
        "breath control": "Build nasal breathing habits and exhale control.",
        "composure": "Develop pre-engagement reset routine.",
        "generic": "Keep focus on consistency and process.",
    },
    "SPP": {
        "confidence": "Link preparation to performance-ready mindset.",
        "gas tank": "Breathe through hard rounds and recover on command.",
        "injury fear": "Trust technique and avoid rushed effort.",
        "pressure": "Embrace intensity while staying composed.",
        "attention": "Lock in on one key cue per round.",
        "motivation": "Connect effort to fight-specific goals.",
        "fear of takedowns": "Stay balanced and ready to reset.",
        "rushing": "Reset after clean shots instead of chasing.",
        "breath control": "Master round-rhythm breathing patterns.",
        "composure": "Check posture and breath between exchanges.",
        "generic": "Train with intent and fight-ready focus.",
    },
    "TAPER": {
        "confidence": "Hold calm confidence and rehearse success.",
        "gas tank": "Stay relaxed and keep breathing smooth.",
        "injury fear": "Move cleanly and trust your body.",
        "pressure": "Stay composed and keep routines steady.",
        "attention": "Short cues, quiet mind.",
        "motivation": "Focus on readiness and belief.",
        "fear of takedowns": "Visualize calm defense triggers.",
        "rushing": "Rehearse patient resets between shots.",
        "breath control": "Maintain smooth, relaxed breathing.",
        "composure": "Practice reset ritual: breath, jaw, stance.",
        "generic": "Keep it simple and stay calm.",
    },
}


def _split_phrases(text: str) -> list[str]:
    cleaned = re.sub(r"[;|]", ",", text)
    cleaned = re.sub(r"\b(?:and|or)\b", ",", cleaned)
    return [chunk.strip() for chunk in re.split(r"[,/]+", cleaned) if chunk.strip()]


def _normalize_blocks(blocks: list[str] | str | None) -> list[str]:
    if not blocks:
        return ["generic"]
    if isinstance(blocks, str):
        blocks = [blocks]
    normalized = [block.strip().lower() for block in blocks if block and block.strip()]
    return normalized or ["generic"]


def _matches_block(phrase: str, block: str, keywords: list[str]) -> bool:
    if block in phrase:
        return True
    for keyword in keywords:
        if keyword in phrase:
            return True
        if fuzz.partial_ratio(keyword, phrase) >= 85:
            return True
    if fuzz.partial_ratio(block, phrase) >= 85:
        return True
    return False


def classify_mental_block(raw_text: str) -> list[str]:
    text = (raw_text or "").strip().lower()
    if not text or text in {"none", "n/a", "na", "no", "nope"}:
        return ["generic"]

    phrases = _split_phrases(text)
    if not phrases:
        return ["generic"]

    counts: Counter[str] = Counter()
    for phrase in phrases:
        for block, keywords in BLOCK_KEYWORDS.items():
            if _matches_block(phrase, block, keywords):
                counts[block] += 1

    if not counts:
        return ["generic"]

    def sort_key(item: tuple[str, int]) -> tuple[int, int]:
        block, count = item
        priority = BLOCK_PRIORITY.index(block) if block in BLOCK_PRIORITY else len(BLOCK_PRIORITY)
        return (-count, priority)

    ordered = sorted(counts.items(), key=sort_key)
    return [block for block, _ in ordered[:2]]


# Backwards compatible alias if older code used an alternate helper name.
classify_blocks = classify_mental_block


def get_phase_mindset_cues(blocks: list[str] | str | None) -> dict[str, str]:
    normalized = _normalize_blocks(blocks)
    cues = {}
    for phase in ("GPP", "SPP", "TAPER"):
        phase_bank = PHASE_CUE_BANK.get(phase, {})
        selected = [phase_bank.get(block, phase_bank.get("generic", "")) for block in normalized]
        cues[phase] = " ".join(filter(None, selected))
    return cues


def get_mindset_by_phase(phase: str, flags: dict) -> str:
    phase_key = phase.upper()
    blocks = _normalize_blocks(flags.get("mental_block"))
    phase_bank = MINDSET_BANK.get(phase_key, MINDSET_BANK["GPP"])
    lines = []
    for block in blocks:
        cue = phase_bank.get(block, phase_bank.get("generic", ""))
        label = block.title()
        if cue:
            lines.append(f"- **{label}:** {cue}")
    return "\n".join(lines) if lines else f"- **Generic:** {phase_bank.get('generic', '')}"
