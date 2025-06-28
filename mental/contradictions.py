
CONTRADICTION_PAIRS = {
    # ⬛ DECISION LOGIC
    (
        "decision_making:decide_fast",
        "overthink_type:overthinker",
    ): {
        "severity": "high",
        "note": "Claims fast decisions, yet overthinks under pressure — may be masking instinct with analysis. Validate through live scenario cues.",
    },
    (
        "decision_making:decide_fast",
        "overthink_type:doubter",
    ): {
        "severity": "high",
        "note": "Reports fast choices but admits to doubt — possible split between intent and execution. Test with consequence-based drills.",
    },
    (
        "decision_making:decide_fast",
        "freeze_type:mental_freeze",
    ): {
        "severity": "high",
        "note": "Mentally freezes yet claims instant decisions — suggests internal override loop. Use contrast exposure to reveal actual default.",
    },
    (
        "decision_making:decide_fast",
        "freeze_type:physical_freeze",
    ): {
        "severity": "high",
        "note": "Physical freeze reported but claims instant action — likely mismatch between mind and motor system. Introduce reaction under fatigue.",
    },
    (
        "decision_making:decide_fast",
        "decision_making:decide_mix",
    ): {
        "severity": "low",
        "note": "Self-reports both instant and mixed decisions — unclear mental identity. Require clarity drills under time pressure.",
    },

    # ⬛ CONFIDENCE / IDENTITY
    ("stable_confidence", "fragile_confidence"): {
        "severity": "high",
        "note": "Stable confidence claimed but emotional fragility admitted — surface identity may be untested. Use adversity cues in training.",
    },
    ("gym_performer", "stable_confidence"): {
        "severity": "high",
        "note": "Performs in gym, struggles in matches despite 'stable' claim — identity split likely. Contrast performance under public scrutiny.",
    },

    # ⬛ PRESSURE vs FREEZE
    ("freeze_type:physical_freeze", "focus_breaker:none_reported"): {
        "severity": "high",
        "note": "Physical freeze present but no focus break admitted — blind spot in awareness. Add pressure journaling post-drill.",
    },
    ("freeze_type:mental_freeze", "focus_breaker:none_reported"): {
        "severity": "high",
        "note": "Mentally freezes yet denies focus issues — suggests detachment or suppression. Use video review to build pattern recognition.",
    },
    ("freeze_type:physical_freeze", "breath_pattern:breath_normal"): {
        "severity": "high",
        "note": "Reports freezing but claims breath stays normal — possible dissociation or misread signal. Test with breathing audit during stress.",
    },
    ("freeze_type:physical_freeze", "hr_response:hr_stable"): {
        "severity": "high",
        "note": "Heart rate reported stable despite freeze — may be masking somatic symptoms. Validate with biometric feedback loops.",
    },

    # ⬛ RESET SPEED
    ("reset_speed:fast_reset", "mental_history:has_history"): {
        "severity": "high",
        "note": "Says they reset fast but has prior mental struggle — overclaim likely. Stress test with back-to-back error drills.",
    },
    (
        "reset_speed:fast_reset",
        "reset_speed:very_slow_reset",
    ): {
        "severity": "high",
        "note": "Reports both instant and very slow reset — mental rhythm unstable. Introduce 10-second breathing + cue switch reset protocol.",
    },

    # ⬛ THREAT + MOTIVATION
    (
        "motivation_type:reward_seeker",
        "threat_trigger:authority_threat",
    ): {
        "severity": "high",
        "note": "Seeks praise but threatened by coach criticism — external validation loop unstable. Introduce autonomy-based reinforcement.",
    },

    # ⬛ ORIGINAL HIGH-LEVEL CONTRADICTIONS
    ("decide_fast", "overthink"): {
        "severity": "high",
        "note": "Claims instinctive action but admits to overthinking — explore performance identity gap via pre-movement cue journaling.",
    },
    ("decide_fast", "hesitate"): {
        "severity": "low",
        "note": "Says they act fast but also hesitate — internal conflict present. Validate via competition footage or reaction speed mapping.",
    },
    ("decide_fast", "second_guess"): {
        "severity": "low",
        "note": "Fast decision reported but second-guessing follows — suggests impulsive action without ownership. Build ownership loop.",
    },
    ("thrives", "hesitate"): {
        "severity": "high",
        "note": "Says they thrive under pressure but also hesitate — performance story may be inflated. Apply high-pressure scenario testing.",
    },
    ("fast_reset", "slow_reset"): {
        "severity": "high",
        "note": "Instant reset claimed but struggles to recover from errors — inconsistency in recovery truth. Test reset drills with increasing delay.",
    },
}


def detect_contradictions(tags: set) -> list[str]:
    def _match(needle: str, pool: set[str]) -> bool:
        if needle in pool:
            return True
        if ":" not in needle:
            return any(t.split(":", 1)[-1] == needle for t in pool)
        return False

    flagged_notes: list[str] = []
    for pair, details in CONTRADICTION_PAIRS.items():
        if all(_match(p, tags) for p in pair):
            flagged_notes.append(details["note"])
    return flagged_notes
