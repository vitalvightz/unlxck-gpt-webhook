from __future__ import annotations

from functools import wraps
from typing import Iterable

from .style_taper_governance import (
    D13_TO_D8,
    D7,
    D6_TO_D5,
    D4_TO_D2,
    D1,
    RPE_MAX_BY_WINDOW,
    style_taper_window_for_days,
)


def _format_cap(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def late_fight_dosage_caps(days_until_fight: int) -> str:
    """Return athlete-facing D13-D1 dosage that cannot exceed Style Taper governance."""
    window = style_taper_window_for_days(days_until_fight)
    if window is None:
        return (
            "Late-fight caps: no conditioning development; keep only low-volume rhythm, "
            "sharpness, or recovery work."
        )

    cap = _format_cap(RPE_MAX_BY_WINDOW[window])
    prefix = f"D-{int(days_until_fight)} late-fight caps: "

    if window == D13_TO_D8:
        return (
            f"{prefix}no conditioning development; 3-4 crisp alactic bursts max "
            f"(5-6 sec @ RPE ≤{cap}, rest 90-120 sec); technical touch 1-2 short rounds max "
            f"(≤2 min @ RPE ≤{cap}); no generic conditioning rounds; cap 6-8 min active. "
            "These caps override any drill default structure."
        )
    if window == D7:
        return (
            f"{prefix}no conditioning development; 3-4 crisp alactic bursts max "
            f"(5-6 sec @ RPE ≤{cap}, rest 90-120 sec); technical touch 1-2 short rounds max "
            f"(≤2 min @ RPE ≤{cap}); no generic conditioning rounds; cap 5-7 min active. "
            "These caps override any drill default structure."
        )
    if window == D6_TO_D5:
        return (
            f"{prefix}optional alactic sharpness only; 2-3 bursts max "
            f"(5-6 sec @ RPE ≤{cap}, rest 120 sec); technical touch 1-2 short rounds max "
            f"(≤2 min @ RPE ≤{cap}); no generic conditioning rounds; cap 5-7 min active. "
            "These caps override any drill default structure."
        )
    if window == D4_TO_D2:
        return (
            f"{prefix}0-2 optional crisp bursts only "
            f"(4-6 sec @ RPE ≤{cap}, full rest); technical walk-through only "
            f"(≤90 sec @ RPE ≤{cap}); no conditioning development; cap 3-5 min active. "
            "These caps override any drill default structure."
        )
    if window == D1:
        return (
            f"{prefix}no conditioning work; optional zero-contact rhythm touch only "
            f"(1-2 x 3-4 sec @ RPE ≤{cap}, full rest); easy shadow rehearsal, breathing "
            "and visualization only; cap 2-4 min active. "
            "These caps override any drill default structure."
        )

    raise AssertionError(f"Unhandled style taper window: {window}")


def _replace_dosage_template(rendered: str, replacement: str) -> str:
    marker = "**Dosage Template:**"
    lines = rendered.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(marker):
            lines[index] = f"{marker} {replacement}"
            return "\n".join(lines)
    return rendered


def install() -> None:
    """Install canonical D13-D1 taper dosage without changing shared bank-schema behavior."""
    from . import conditioning as conditioning_module

    if getattr(conditioning_module, "_STYLE_TAPER_DOSAGE_POLICY_INSTALLED", False):
        return

    original_render = conditioning_module.render_conditioning_block

    @wraps(original_render)
    def render_conditioning_block(
        grouped_drills: dict[str, list[dict]],
        *,
        phase: str,
        phase_color: str,
        missing_systems: Iterable[str] | None = None,
        num_sessions: int = 1,
        diagnostic_context: dict | None = None,
        sport: str | None = None,
        resolved_sessions: list[dict] | None = None,
    ) -> str:
        context = dict(diagnostic_context or {})
        days_until_fight = context.get("days_until_fight")
        if days_until_fight is None:
            days_until_fight = context.get("time_to_fight_days")

        window = style_taper_window_for_days(days_until_fight)
        if str(phase or "").upper() == "TAPER" and window is not None:
            # The legacy renderer can add a separate generic RPE 7-8 speed-dose line.
            # In D13-D1, the canonical Style Taper dosage already owns that exposure.
            context["speed_dose_allowed"] = False

        rendered = original_render(
            grouped_drills,
            phase=phase,
            phase_color=phase_color,
            missing_systems=missing_systems,
            num_sessions=num_sessions,
            diagnostic_context=context,
            sport=sport,
            resolved_sessions=resolved_sessions,
        )

        if str(phase or "").upper() == "TAPER" and window is not None:
            rendered = _replace_dosage_template(
                rendered,
                late_fight_dosage_caps(int(days_until_fight)),
            )
        return rendered

    conditioning_module._late_fight_dosage_caps = late_fight_dosage_caps
    conditioning_module.render_conditioning_block = render_conditioning_block
    conditioning_module._STYLE_TAPER_DOSAGE_POLICY_INSTALLED = True
