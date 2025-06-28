TAG_LABELS = {
    # Pressure traits
    "overthink": "Overthinker",
    "hesitate": "Hesitates Under Pressure",
    "freeze": "Freezes or Blanks",
    "second_guess": "Second-Guesses Self",
    "avoidant": "Avoids Risk",
    "emotional": "Emotionally Reactive",
    "audio_cutoff": "Stops Listening",
    "demand_avoidance": "Avoids Responsibility",
    "thrives": "Thrives Under Pressure",

    # Post-mistake traits
    "mental_loop": "Overthinks Mistakes",
    "shutdown": "Withdraws After Error",
    "compensate": "Overcompensates Immediately",
    "disengage": "Disengages Mentally",
    "self_anger": "Gets Angry at Self",
    "quick_reset": "Resets Quickly",
    "external_judgement": "Worries What Others Think",

    # Confidence types
    "gym_performer": "Performs Better in Training",
    "fragile_confidence": "Fragile Confidence",
    "stage_fear": "Struggles Under Spotlight",
    "pressure_distrust": "Distrusts Self in Pressure",
    "emotional_performer": "Performs Best When Emotional",
    "control_needed": "Needs Control to Perform",
    "stable_confidence": "Stable Self-Confidence",

    # Focus traits
    "focus_crowd": "Focus Breaks from Crowd",
    "focus_coach": "Distracted by Coach",
    "focus_decision_fear": "Fear of Wrong Decision",
    "focus_fatigue": "Focus Breaks When Tired",
    "focus_self_critic": "Focus Breaks from Inner Critic",
    "focus_social": "Focus Breaks from Others",
    "focus_locked": "Rarely Loses Focus",

    # Preference flags
    "pref_breathwork": "Prefers Breathwork",
    "pref_cold_exposure": "Prefers Cold Exposure",
    "pref_journaling": "Prefers Journaling",
    "pref_anchor_cue": "Uses Cues or Anchors",
    "pref_visualisation": "Uses Visualisation",
    "pref_unknown": "No Preferred Tools Reported",

    # Key struggles
    "slow_reset": "Slow to Reset",
    "unknown_struggle": "Unclear Struggles",

    # Also ensure the below are humanized if surfaced anywhere
    "decide_freeze": "Freezes Under Choice",
    "decide_think": "Deliberate Thinker",
    "decide_wait": "Deferential Decision-Maker",
    "decide_fast": "Instinctive Decision-Maker",
    "decide_mix": "Adaptive Decision Style",

    # Physiological responses
    "breath_hold": "Holds Breath",
    "breath_fast": "Breathing Speeds Up",
    "breath_normal": "Breath Remains Normal",
    "breath_unknown": "Breath Pattern Unknown",

    "hr_up": "Heart Rate Spikes",
    "hr_down": "Heart Rate Drops",
    "hr_stable": "Heart Rate Stable",
    "hr_unknown": "Heart Rate Unknown",

    # Motivation
    "reward_seeker": "Motivated by Rewards",
    "avoid_failure": "Avoids Failure",
    "competitive": "Competitive Drive",
    "external_validation": "Seeks External Validation",
    "motivation_unknown": "Motivation Unclear",

    # Threat triggers
    "authority_threat": "Threatened by Authority",
    "peer_threat": "Threatened by Peers",
    "audience_threat": "Threatened by Audience",
    "general_threat": "Generalized Threat Response",

    # History
    "has_history": "Has Past Mental Struggles",
    "clear_history": "No Mental Struggles Reported",

    # Reset speeds
    "fast_reset": "Resets Instantly",
    "medium_reset": "Resets in 10–30s",
    "very_slow_reset": "Very Slow Reset",

    # Additional theme tags
    "distracted_by_crowd": "Focus Breaks from Crowd",
    "coach_noise": "Coach-Driven Distraction",
    "opponent_noise": "Opponent Distraction",
    "self_conflict": "Inner Conflict",
    "fatigue": "Focus Breaks When Tired",
    "physical_freeze": "Physical Freeze",
    "mental_freeze": "Mental Freeze",
    "overthinker": "Overthinker",
    "doubter": "Doubter",
    "stay_loose": "Stays Loose",
    "breath_slow": "Breath Slows Down",
    "decisive": "Decisive",
    "aggressive": "Aggressive",
    "aware": "Aware",
    "calm": "Calm",
    "commanding": "Commanding Presence",
    "confident": "Confident",
    "dominant": "Dominant",
    "focused": "Focused",
    "free": "Plays with Freedom",
    "hungry": "Hungry",
    "joyful": "Joyful",
    "locked-in": "Locked In",
    "playful": "Playful",
    "precise": "Precise",
    "relaxed": "Relaxed",
    "resilient": "Resilient",
    "ruthless": "Ruthless",
    "tactical": "Tactically Minded",
    "wild": "Wild",

    # Generic category labels
    "focus_breaker": "Focus Breaker",
    "overthink_type": "Overthinking Style",
    "under_pressure": "Under-Pressure Trait",
    "post_mistake": "Post-Mistake Trait",
    "reset_speed": "Reset Speed",
    "mental_history": "Mental History",
    "threat_trigger": "Threat Trigger",
    "confidence_profile": "Confidence Profile",
}


def human_label(tag: str) -> str:
    """Return human-readable label for a backend tag."""
    return TAG_LABELS.get(tag, tag)


def humanize_list(tags):
    """Convert a list of tags to their human-readable labels."""
    return [human_label(t) for t in tags]
