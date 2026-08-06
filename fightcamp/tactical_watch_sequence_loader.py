from __future__ import annotations

from typing import Any

_CONTENT_FIELDS = (
    "athlete_facing_label",
    "display_text",
    "tactical_watch_phase",
    "tactical_watch_variant",
    "tactical_watch_progression",
)


def _copy_content(target: dict[str, Any], source: dict[str, Any]) -> None:
    for field in _CONTENT_FIELDS:
        target[field] = source[field]


def install() -> None:
    from . import gap_fill_inserts as gap_module

    if getattr(gap_module, "_TACTICAL_WATCH_SEQUENCE_INSTALLED", False):
        return

    base_build_mandatory = gap_module._build_mandatory_tactical_watch

    def build_mandatory_tactical_watch(
        athlete_model: dict[str, Any],
        offset: int,
        weekday: str | None,
    ) -> dict[str, Any]:
        watch = base_build_mandatory(athlete_model, offset, weekday)
        phase = "TAPER" if offset <= 7 else "SPP"
        progression_index = 0
        if phase == "SPP":
            try:
                horizon = min(
                    21,
                    max(offset, int(athlete_model.get("days_until_fight"))),
                )
            except (TypeError, ValueError):
                horizon = min(21, offset)
            progression_index = max(
                0,
                gap_module._segment_for_offset(horizon)
                - gap_module._segment_for_offset(offset),
            )
        content = gap_module._build_insert_role(
            "tactical_watch",
            athlete_model,
            offset,
            weekday,
            tactical_watch_phase=phase,
            tactical_watch_variation_seed=progression_index * 7,
        )
        _copy_content(watch, content)
        watch["camp_phase"] = phase
        return watch

    gap_module._build_mandatory_tactical_watch = build_mandatory_tactical_watch
    gap_module._TACTICAL_WATCH_SEQUENCE_INSTALLED = True

    from . import camp_week_fillers as camp_module

    base_apply_camp_week_fillers = camp_module.apply_camp_week_fillers

    def apply_camp_week_fillers(
        weekly_role_map: dict[str, Any],
        athlete_model: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        athlete_model = athlete_model or {}
        result = base_apply_camp_week_fillers(weekly_role_map, athlete_model)
        phase_counts: dict[str, int] = {}
        for week in result.get("weeks", []) if isinstance(result, dict) else []:
            if not isinstance(week, dict):
                continue
            phase = str(week.get("phase") or "").strip().upper()
            if phase not in {"GPP", "SPP", "TAPER"}:
                continue
            progression_index = phase_counts.get(phase, 0)
            phase_counts[phase] = progression_index + 1
            for role in week.get("session_roles", []) or []:
                if not isinstance(role, dict):
                    continue
                if str(role.get("role_key") or "") != "tactical_watch":
                    continue
                try:
                    offset = int(role.get("countdown_offset"))
                except (TypeError, ValueError):
                    continue
                weekday = str(
                    role.get("scheduled_day_hint") or role.get("real_weekday") or ""
                ).strip() or None
                content = gap_module._build_insert_role(
                    "tactical_watch",
                    athlete_model,
                    offset,
                    weekday,
                    tactical_watch_phase=phase,
                    tactical_watch_variation_seed=progression_index * 7,
                )
                _copy_content(role, content)
                role["camp_phase"] = phase
        return result

    camp_module.apply_camp_week_fillers = apply_camp_week_fillers
    camp_module._TACTICAL_WATCH_SEQUENCE_INSTALLED = True
