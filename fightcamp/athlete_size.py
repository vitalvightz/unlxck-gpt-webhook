from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .conditioning import render_conditioning_block
from .rounds_format import canonicalize_rounds_format_sport

LIGHTWEIGHT_MAX_KG = 67.0
HEAVYWEIGHT_MIN_KG = 91.0
SUPPORTED_SPORTS = {"boxing", "mma", "muay_thai", "kickboxing"}

_COUNT_RANGE_PATTERN = re.compile(
    r"^(?P<low>\d+)(?:-(?P<high>\d+))?(?P<suffix>\s*x\b)",
    re.IGNORECASE,
)
_SECONDS_RANGE_PATTERN = re.compile(
    r"(?P<low>\d+)(?:-(?P<high>\d+))?(?P<suffix>\s*sec\b)",
    re.IGNORECASE,
)

SIZE_BAND_RULES: dict[str, dict[str, Any]] = {
    "light": {
        "phases": {
            "GPP": {
                "render_defaults": {
                    "dosage_template": "3-5 rounds of 3-5 min @ RPE 6-7, work:rest 1:0.75-1:0.5 (cap 22-32 min). Allow slightly more rhythm density when posture and breathing stay clean.",
                    "time_short": "Keep 2 aerobic rounds plus 1 short rhythm or footwork exposure.",
                    "fatigue_note": "If fatigue high: trim 1 round first, but a small rhythm dose is usually better tolerated than more junk volume.",
                },
                "render_append": {
                    "weekly_progression": "Optional support volume can live on the higher end when recovery and movement quality stay clean.",
                },
                "systems": {
                    "aerobic": {
                        "timing_note": "optional support volume can sit on the high end if recovery stays clean",
                    },
                },
            },
            "SPP": {
                "render_defaults": {
                    "dosage_template": "5-7 rounds of 2-4 min @ RPE 7-8, work:rest 1:0.75-1:0.5 (cap 20-28 min). Allow slightly more repeatability density when rhythm stays crisp.",
                    "time_short": "Keep 2-3 fight-pace rounds plus a short rhythm or footwork exposure.",
                    "fatigue_note": "If fatigue high: trim 1 round first, but lighter athletes can usually keep a small repeatability dose if sharpness stays clean.",
                },
                "render_append": {
                    "weekly_progression": "A lighter athlete can tolerate a little more repeatability work before adding more rest.",
                },
                "systems": {
                    "glycolytic": {
                        "count_shift": 1,
                        "rest_shift_sec": -15,
                        "timing_note": "light band can tolerate 1 extra short repeat if posture and pace stay clean",
                    },
                    "alactic": {
                        "rest_shift_sec": -15,
                        "load_note": "keep bursts crisp and relaxed; do not let extra density blur the speed",
                    },
                },
            },
            "TAPER": {
                "render_defaults": {
                    "dosage_template": "6-10 rounds of 6-10 sec @ RPE 8-9, rest 45-90 sec (cap 8-12 min). Keep rhythm and sharpness present without carrying fatigue.",
                    "fatigue_note": "If fatigue high: keep only a small burst dose plus rhythm work.",
                },
                "render_append": {
                    "time_short": "A short rhythm dose is usually enough; do not force extra burst work.",
                },
                "systems": {
                    "alactic": {
                        "rest_shift_sec": -15,
                    },
                },
            },
        },
    },
    "heavy": {
        "phases": {
            "GPP": {
                "render_defaults": {
                    "dosage_template": "3-4 rounds of 2-4 min @ RPE 6-7, work:rest 1:1-1:0.75 (cap 16-24 min). Bias low-damage support and controlled density.",
                    "time_short": "Keep 2 low-damage support rounds plus 1 small burst cluster; prefer sled, bike, bag, or other low-impact cyclical work over repeated jumps.",
                    "fatigue_note": "If fatigue high: cut density first, lengthen rest, and protect force quality.",
                },
                "render_append": {
                    "weekly_progression": "Keep optional support volume on the low end and add only when freshness holds.",
                },
                "systems": {
                    "aerobic": {
                        "timing_note": "keep optional support volume conservative and bias low-damage modes",
                    },
                },
            },
            "SPP": {
                "render_defaults": {
                    "dosage_template": "4-5 rounds of 2-4 min @ RPE 7-8, work:rest 1:1-1:0.75 (cap 14-20 min). Protect force quality and avoid junk density.",
                    "time_short": "Keep 2-3 fight-pace rounds plus a very small burst dose; use sled, bike, bag, or other low-impact cyclical work when possible.",
                    "fatigue_note": "If fatigue high: drop 1 round, extend rest slightly, and protect neural quality before adding more density.",
                },
                "render_append": {
                    "weekly_progression": "For heavier athletes, keep hard density on the low end and add support cautiously.",
                },
                "systems": {
                    "glycolytic": {
                        "count_shift": -1,
                        "rest_shift_sec": 15,
                        "timing_note": "keep round simulation on the low end if speed or posture fades",
                    },
                    "alactic": {
                        "count_shift": -1,
                        "rest_shift_sec": 15,
                        "load_note": "protect force quality and stop early when snap drops",
                    },
                },
            },
            "TAPER": {
                "render_defaults": {
                    "dosage_template": "4-6 rounds of 6-10 sec @ RPE 8-9, rest 75-120 sec (cap 6-10 min). Keep sharpness high and density low.",
                    "fatigue_note": "If fatigue high: keep only a very small burst dose and low-damage rhythm work.",
                },
                "render_append": {
                    "time_short": "Heavy athletes usually need less extra sharpness work, not more.",
                },
                "systems": {
                    "glycolytic": {
                        "count_shift": -1,
                        "rest_shift_sec": 15,
                    },
                    "alactic": {
                        "count_shift": -1,
                        "rest_shift_sec": 15,
                    },
                },
            },
        },
    },
}


def get_athlete_size_band(weight_kg: float | int | None) -> str | None:
    try:
        weight = float(weight_kg)
    except (TypeError, ValueError):
        return None

    if weight <= 0:
        return None
    if weight <= LIGHTWEIGHT_MAX_KG:
        return "light"
    if weight >= HEAVYWEIGHT_MIN_KG:
        return "heavy"
    return "middle"


def _append_sentence(base: str | None, extra: str | None) -> str | None:
    normalized_extra = str(extra or "").strip()
    if not normalized_extra:
        return base

    normalized_base = str(base or "").strip()
    if not normalized_base:
        return normalized_extra
    if normalized_extra.lower() in normalized_base.lower():
        return normalized_base
    return f"{normalized_base} {normalized_extra}"


def _merge_prescription(base: str | None, target: str | None, *, label: str) -> str | None:
    normalized_target = str(target or "").strip()
    if not normalized_target:
        return base

    normalized_base = str(base or "").strip()
    if not normalized_base:
        return normalized_target
    if normalized_target.lower() in normalized_base.lower():
        return normalized_base
    return f"{normalized_base}; {label}: {normalized_target}"


def _format_range(low: int, high: int) -> str:
    return str(low) if low == high else f"{low}-{high}"


def _shift_leading_count_range(text: str | None, delta: int | None) -> str | None:
    if not text or not isinstance(delta, int) or delta == 0:
        return text

    match = _COUNT_RANGE_PATTERN.search(text)
    if not match:
        return text

    low = int(match.group("low"))
    high = int(match.group("high") or low)
    shifted_low = max(1, low + delta)
    shifted_high = max(shifted_low, high + delta)
    replacement = f"{_format_range(shifted_low, shifted_high)}{match.group('suffix')}"
    return _COUNT_RANGE_PATTERN.sub(replacement, text, count=1)


def _shift_seconds_range(text: str | None, delta: int | None) -> str | None:
    if not text or not isinstance(delta, int) or delta == 0:
        return text

    match = _SECONDS_RANGE_PATTERN.search(text)
    if not match:
        return text

    low = int(match.group("low"))
    high = int(match.group("high") or low)
    shifted_low = max(15, low + delta)
    shifted_high = max(shifted_low, high + delta)
    replacement = f"{_format_range(shifted_low, shifted_high)}{match.group('suffix')}"
    return _SECONDS_RANGE_PATTERN.sub(replacement, text, count=1)


def _apply_system_modifiers(drill: dict[str, Any], system_rules: dict[str, Any]) -> dict[str, Any]:
    updated = dict(drill)
    generic_fallback = bool(updated.get("generic_fallback"))

    base_timing = updated.get("timing") or updated.get("duration")
    base_rest = updated.get("rest")
    base_load = updated.get("load") or updated.get("intensity")

    shifted_timing = _shift_leading_count_range(base_timing, system_rules.get("count_shift"))
    shifted_rest = _shift_seconds_range(base_rest, system_rules.get("rest_shift_sec"))

    if generic_fallback:
        if shifted_timing:
            updated["timing"] = shifted_timing
        if shifted_rest:
            updated["rest"] = shifted_rest
        if system_rules.get("load_note"):
            updated["load"] = _merge_prescription(
                base_load,
                system_rules.get("load_note"),
                label="size note",
            )
        return updated

    updated["timing"] = _merge_prescription(
        base_timing,
        system_rules.get("timing_note"),
        label="size target",
    )
    updated["rest"] = _merge_prescription(
        shifted_rest if shifted_rest != base_rest else base_rest,
        system_rules.get("rest_note"),
        label="size rest",
    )
    updated["load"] = _merge_prescription(
        base_load,
        system_rules.get("load_note"),
        label="size note",
    )
    return updated


def apply_athlete_size_modifiers(
    conditioning_blocks: dict[str, dict | None],
    *,
    sport: str | None,
    weight_kg: float | int | None,
) -> tuple[dict[str, dict | None], str | None]:
    normalized_sport = canonicalize_rounds_format_sport(sport)
    size_band = get_athlete_size_band(weight_kg)
    if normalized_sport not in SUPPORTED_SPORTS or not size_band:
        return conditioning_blocks, size_band

    rules = SIZE_BAND_RULES.get(size_band)
    if not rules:
        return conditioning_blocks, size_band

    updated_blocks = deepcopy(conditioning_blocks)

    for phase, block in updated_blocks.items():
        if not block:
            continue

        phase_rules = rules.get("phases", {}).get(str(phase).upper())
        if not phase_rules:
            continue

        grouped_drills = block.get("grouped_drills") or {}
        for system, drills in grouped_drills.items():
            system_rules = phase_rules.get("systems", {}).get(system)
            if not system_rules:
                continue
            grouped_drills[system] = [
                _apply_system_modifiers(drill, system_rules)
                for drill in drills
            ]

        merged_render_overrides = dict(block.get("render_overrides") or {})
        for key, value in phase_rules.get("render_defaults", {}).items():
            if key not in merged_render_overrides:
                merged_render_overrides[key] = value
        for key, value in phase_rules.get("render_append", {}).items():
            merged_render_overrides[key] = _append_sentence(
                merged_render_overrides.get(key),
                value,
            )

        block["size_band"] = size_band
        block["render_overrides"] = merged_render_overrides
        block["block"] = render_conditioning_block(
            grouped_drills,
            phase=phase,
            phase_color=block.get("phase_color", "#000"),
            missing_systems=block.get("missing_systems", []),
            num_sessions=block.get("num_sessions", 1),
            diagnostic_context=block.get("diagnostic_context", {}),
            sport=block.get("sport"),
            render_overrides=block.get("render_overrides"),
        )

    return updated_blocks, size_band
