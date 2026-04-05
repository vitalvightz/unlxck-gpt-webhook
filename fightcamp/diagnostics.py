from __future__ import annotations

from typing import Any

SYSTEM_LABELS = {
    "aerobic": "AEROBIC",
    "glycolytic": "GLYCOLYTIC",
    "alactic": "ALACTIC/ATP-PCr",
}


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _days_until_fight(context: dict) -> int | None:
    direct = _parse_int(context.get("time_to_fight_days"))
    if direct is not None:
        return direct
    direct = _parse_int(context.get("days_until_fight"))
    if direct is not None:
        return direct
    weeks_out = _parse_int(context.get("weeks_out"))
    if weeks_out is not None:
        return weeks_out * 7
    return None


def _is_high_fatigue(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value >= 7
    text = str(value).strip().lower()
    return text in {"high", "very high", "very_high", "severe", "elevated"}


def _listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)]


def _has_lower_limb_injury(injuries: list[str]) -> bool:
    keywords = {
        "ankle",
        "foot",
        "toe",
        "calf",
        "achilles",
        "knee",
        "hamstring",
        "quad",
        "thigh",
        "hip",
        "groin",
        "shin",
        "tibia",
    }
    for entry in injuries:
        text = entry.lower()
        if any(keyword in text for keyword in keywords):
            return True
    return False


def _short_notice_lever(system_key: str) -> str:
    if system_key == "aerobic":
        return "Optional 1× 20–30 min Zone 2 if recovery/base is limiting."
    if system_key == "glycolytic":
        return "If output fades late, add 4–6 × 2:00 on / 1:00 off at controlled pace."
    return "If explosiveness fades, add 6–8 × 8–10s full-rest bursts (bike or track)."


def _late_fight_lever(system_key: str, days_until_fight: int) -> str:
    """Return a countdown-aware coach option for a missing system block during D-5 to D-0.

    Generic short-notice doses (e.g. '6–8 × 8–10s full-rest bursts') are too large
    for the final fight-week countdown.  This function returns prescriptions that
    stay within the freshness-preserving caps for each day.
    """
    if system_key == "alactic":
        if days_until_fight == 5:
            return (
                "If explosiveness fades, add up to 6 short alactic bursts "
                "(6–10 s @ full rest) — cap 8–10 min active."
            )
        if days_until_fight == 4:
            return (
                "If explosiveness fades, add up to 5 short alactic bursts "
                "(6–10 s @ full rest) — cap 6–8 min active."
            )
        if days_until_fight == 3:
            return (
                "If explosiveness fades, add up to 4 short alactic bursts "
                "(6–10 s @ full rest) if freshness allows — otherwise skip."
            )
        if days_until_fight == 2:
            return (
                "If explosiveness fades, add 2–4 very short alactic bursts "
                "(6–8 s @ full rest) — freshness first; cap 4–6 min active."
            )
        if days_until_fight == 1:
            return (
                "If explosiveness fades, add 2–3 short primer bursts only "
                "(6–8 s @ full rest) — no conditioning structure."
            )
        # days_until_fight == 0 / fight day
        return "Fight day — no alactic conditioning; walk-through activation only."
    if system_key == "glycolytic":
        if days_until_fight >= 4:
            return "Glycolytic conditioning paused for fight week — freshness priority."
        return "Glycolytic conditioning omitted — no lactate accumulation in final countdown."
    # aerobic system
    if days_until_fight == 5:
        return "Optional 15–20 min easy Zone 2 for blood flow only — keep effort minimal."
    if days_until_fight in (4, 3):
        return "Optional 10–15 min easy movement for recovery — no aerobic training load."
    if days_until_fight == 2:
        return "Light walk or easy mobility only — no aerobic conditioning."
    if days_until_fight == 1:
        return "Aerobic training omitted — light activation and movement only."
    # days_until_fight == 0
    return "No aerobic conditioning on fight day."


def format_missing_system_block(
    system_name: str,
    phase: str,
    sport: str,
    context: dict,
) -> str:
    """
    Returns a coach-facing cue for an omitted/empty system block.
    """
    system_key = (system_name or "").strip().lower()
    system_label = SYSTEM_LABELS.get(system_key, system_name.upper())
    phase_label = (phase or "").strip().upper()

    days_until = _days_until_fight(context)
    fatigue_level = context.get("fatigue_level", context.get("fatigue"))
    injuries = _listify(context.get("injuries"))

    if days_until is not None and days_until <= 14:
        reason = "Short-notice camp; priority is specificity and freshness."
        if days_until <= 5:
            lever = _late_fight_lever(system_key, days_until)
        else:
            lever = _short_notice_lever(system_key)
    elif phase_label == "TAPER":
        reason = "Tapering; volume reduced to preserve freshness."
        lever = "Optional 1 early-week exposure at 60–70% volume if athlete needs confidence."
    elif _is_high_fatigue(fatigue_level):
        reason = "Fatigue risk; system emphasis narrowed to reduce CNS load."
        lever = "Swap in low-impact steady work (bike/row) instead of high-impact intervals."
    elif _has_lower_limb_injury(injuries) and system_key in {"alactic", "atp", "atp-pcr"}:
        reason = "Injury constraint; high-speed exposure limited."
        lever = "Use bike sprints (8–10 × 10s) or shadow/footwork bursts if tolerated."
    else:
        reason = "System deprioritized by current phase emphasis."
        lever = "Add a minimal maintenance dose if needed."

    lines = [
        f"{system_label} (Status: Not prescribed)",
        f"Reason: {reason}",
        f"Coach option: {lever}",
    ]
    return "\n".join(lines)
