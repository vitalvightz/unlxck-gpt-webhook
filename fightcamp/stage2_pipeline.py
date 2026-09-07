from __future__ import annotations

import re
from typing import Any

from .stage2_policy import (
    apply_stage2_release_policy,
    admin_review_blocking_findings,
    is_hard_stage2_blocker,
    prompt_safe_validator_report,
)
from .stage2_repair import build_stage2_repair_prompt
from .stage2_validator import (
    _BULLET_PREFIX,
    _MARKDOWN_HEADER,
    _PHASE_HEADER,
    _WEEK_HEADER,
    validate_stage2_output,
)
from .stage2_validator_postprocess import postprocess_stage2_validator_report


_STATUS_READY = "READY"
_STATUS_PASS = "PASS"
_STATUS_WARN = "WARN"
_STATUS_FAIL = "FAIL"

_COUNTDOWN_HEADER_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?D-(\d{1,2})\b",
    re.IGNORECASE | re.MULTILINE,
)
STRUCTURAL_INTEGRITY_CODES = frozenset(
    {
        "phase_section_missing",
        "missing_week_session_role",
        "late_camp_session_incomplete",
        "late_fight_missing_required_countdown_session",
    }
)


def _require_dict(value: Any, *, name: str) -> dict:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be a dict")
    return value


def _require_stage1_field(stage1_result: dict, field: str) -> Any:
    if field not in stage1_result:
        raise KeyError(f"stage1_result missing required field: {field}")
    return stage1_result[field]


def _count_candidate_slots(planning_brief: dict) -> int:
    total = 0
    for phase_pool in (planning_brief.get("candidate_pools") or {}).values():
        total += len(phase_pool.get("strength_slots", []) or [])
        total += len(phase_pool.get("conditioning_slots", []) or [])
        total += len(phase_pool.get("rehab_slots", []) or [])
    return total


def _normalise_countdown_label(value: Any) -> str:
    match = re.search(r"\bD-(\d{1,2})\b", str(value or ""), re.IGNORECASE)
    if not match:
        return ""
    return f"D-{int(match.group(1))}"


def _rendered_countdown_labels(final_plan_text: str) -> set[str]:
    return {
        f"D-{int(match.group(1))}"
        for match in _COUNTDOWN_HEADER_RE.finditer(final_plan_text or "")
    }


def _normalise_render_match_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _rendered_countdown_sections(final_plan_text: str) -> dict[str, list[str]]:
    text = final_plan_text or ""
    matches = list(_COUNTDOWN_HEADER_RE.finditer(text))
    sections: dict[str, list[str]] = {}
    for index, match in enumerate(matches):
        countdown_label = f"D-{int(match.group(1))}"
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.setdefault(countdown_label, []).append(text[match.start():end])
    return sections


def _role_render_markers(role: dict[str, Any]) -> list[str]:
    markers: list[str] = []
    for key in (
        "athlete_facing_label",
        "label",
        "session_role_label",
        "role_label",
        "title",
        "name",
    ):
        marker = _normalise_render_match_text(role.get(key))
        if marker and marker not in markers:
            markers.append(marker)

    role_key = _normalise_render_match_text(str(role.get("role_key") or "").replace("_", " "))
    role_key = re.sub(r"\bday\b$", "", role_key).strip()
    if role_key and role_key not in markers:
        markers.append(role_key)
    return markers


def _required_role_survives_render(
    *,
    role: dict[str, Any],
    countdown_label: str,
    rendered_sections: dict[str, list[str]],
) -> bool:
    candidate_sections = rendered_sections.get(countdown_label, [])
    if not candidate_sections:
        return False

    markers = _role_render_markers(role)
    if not markers:
        # Preserve the legacy header-only fallback only for roles with no usable
        # identity marker. Scheduler-owned gap fillers carry athlete_facing_label.
        return True

    for section in candidate_sections:
        normalised_section = _normalise_render_match_text(section)
        if any(marker in normalised_section for marker in markers):
            return True
    return False


def _is_hidden_context_role(role: dict[str, Any]) -> bool:
    role_key = str(role.get("role_key") or "").strip().lower()
    category = str(role.get("category") or "").strip().lower()

    if role_key == "hard_sparring_day":
        return True
    if category == "sparring" and bool(role.get("coach_owned")):
        return True

    return False


def _sequence_from_value(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _selected_countdown_sequence(planning_brief: dict) -> list[dict[str, Any]]:
    # Prefer the top-level athlete-visible sequence when present because it is
    # the post-gap-fill sequence used for what the athlete actually does.
    for key in (
        "late_fight_session_sequence",
        "session_sequence",
        "countdown_sessions",
    ):
        sequence = _sequence_from_value(planning_brief.get(key))
        if sequence:
            return sequence

    spec = planning_brief.get("late_fight_plan_spec") or {}
    if isinstance(spec, dict):
        for key in (
            "visible_session_sequence",
            "session_sequence",
            "countdown_sessions",
            "sessions",
        ):
            sequence = _sequence_from_value(spec.get(key))
            if sequence:
                return sequence

    return []


def _role_countdown_label(role: dict[str, Any]) -> str:
    return (
        _normalise_countdown_label(role.get("scheduled_countdown_label"))
        or _normalise_countdown_label(role.get("countdown_label"))
        or _normalise_countdown_label(role.get("countdown_display_label"))
    )


def _role_display_label(role: dict[str, Any], countdown_label: str) -> str:
    display = str(role.get("countdown_display_label") or "").strip()
    if display:
        return display

    weekday = str(
        role.get("real_weekday")
        or role.get("countdown_weekday")
        or role.get("scheduled_day_hint")
        or ""
    ).strip()

    if weekday:
        return f"{countdown_label} ({weekday.title()})"

    return countdown_label


def _role_weekday(role: dict[str, Any]) -> str:
    return str(
        role.get("scheduled_day_hint")
        or role.get("real_weekday")
        or role.get("countdown_weekday")
        or ""
    ).strip()


def _role_countdown_from_week(week: dict[str, Any], role: dict[str, Any]) -> str:
    label = _role_countdown_label(role)
    if label:
        return label
    weekday = _role_weekday(role).lower()
    if not weekday:
        return ""
    for day in week.get("calendar_days") or []:
        if not isinstance(day, dict):
            continue
        if str(day.get("weekday") or "").strip().lower() != weekday:
            continue
        value = day.get("d_day")
        if isinstance(value, int) and value >= 0:
            return f"D-{value}"
    return ""


def _authoritative_role_body(role: dict[str, Any]) -> list[str] | None:
    """Return the role's authoritative athlete-facing body, or ``None``.

    Authoritative means content the deterministic planner already resolved: an
    explicit ``display_text``, or ``selected_exercise_assignments`` where every
    entry carries both a name and an approved ``effective_prescription``. It
    deliberately refuses to synthesise a body from ``preferred_exercise_names``
    or from the role category, so a role whose content is not fully resolved is
    left unrestored (and therefore held) rather than papered over with generic
    or unapproved text.
    """
    display_text = str(role.get("display_text") or "").strip()
    if display_text:
        return [line.rstrip() for line in display_text.splitlines() if line.strip()]

    assignments = _list_value(role.get("selected_exercise_assignments"))
    if not assignments:
        return None
    lines: list[str] = []
    for assignment in assignments:
        if not isinstance(assignment, dict):
            return None
        name = str(assignment.get("name") or assignment.get("exercise_name") or "").strip()
        prescription = assignment.get("effective_prescription")
        if isinstance(prescription, dict):
            display = str(
                prescription.get("display")
                or prescription.get("dose")
                or prescription.get("text")
                or ""
            ).strip()
        else:
            display = str(prescription or "").strip()
        # Require both an exercise name and an approved effective prescription.
        # A single partial assignment makes the whole role non-authoritative.
        if not name or not display:
            return None
        lines.append(f"- {name} — {display}")
    return lines or None


def _role_requires_authoritative_render(role: dict[str, Any]) -> bool:
    """Whether a missing role is app-rendered work this repair must own.

    Roles the deterministic layer marks non-mandatory, or coach-owned context
    days (declared hard sparring / coach-led contact), are never synthesised
    here. Their absence is not an app-content loss this repair can author, so
    they are neither restored nor counted as its unresolved diagnostics — the
    validator's own structural findings still hold the plan if their loss
    matters.
    """
    if role.get("render_mandatory") is False:
        return False
    if _is_hidden_context_role(role):
        return False
    return True


_WEEKDAY_CANONICAL = {
    "monday": "Monday",
    "mon": "Monday",
    "tuesday": "Tuesday",
    "tue": "Tuesday",
    "tues": "Tuesday",
    "wednesday": "Wednesday",
    "wed": "Wednesday",
    "thursday": "Thursday",
    "thu": "Thursday",
    "thur": "Thursday",
    "thurs": "Thursday",
    "friday": "Friday",
    "fri": "Friday",
    "saturday": "Saturday",
    "sat": "Saturday",
    "sunday": "Sunday",
    "sun": "Sunday",
}


def _canonical_weekday(value: Any) -> str:
    return _WEEKDAY_CANONICAL.get(str(value or "").strip().lower(), "")


def _first_weekday_in_text(text: str) -> str:
    for match in re.finditer(r"[A-Za-z]+", text or ""):
        canonical = _WEEKDAY_CANONICAL.get(match.group(0).lower())
        if canonical:
            return canonical
    return ""


def _is_week_or_phase_header(header_text: str) -> bool:
    return bool(_WEEK_HEADER.search(header_text) or _PHASE_HEADER.search(header_text))


def _is_day_block_start(raw_line: str) -> bool:
    """A day/session heading inside a week section (never a week/phase header)."""
    if _COUNTDOWN_HEADER_RE.match(raw_line or ""):
        return True
    header_match = _MARKDOWN_HEADER.match(raw_line or "")
    if not header_match:
        return False
    return not _is_week_or_phase_header(header_match.group(2).strip())


def _week_section_layout(lines: list[str]) -> dict[int, dict[str, int]]:
    """Map ``week_index -> {header_idx, section_end}`` for each rendered week.

    ``section_end`` is the line index of the next week or phase header (or EOF),
    so a week's canonical body is ``lines[header_idx + 1 : section_end]``. Only
    the first render of a week number is kept, so a stray duplicate heading can
    never create a second canonical section to insert into.
    """
    boundaries: list[tuple[int, int | None]] = []
    for idx, raw_line in enumerate(lines):
        header_match = _MARKDOWN_HEADER.match(raw_line)
        if not header_match:
            continue
        header_text = header_match.group(2).strip()
        week_match = _WEEK_HEADER.search(header_text)
        if week_match:
            boundaries.append((idx, int(week_match.group(1))))
        elif _PHASE_HEADER.search(header_text):
            boundaries.append((idx, None))

    layout: dict[int, dict[str, int]] = {}
    for position, (idx, week_no) in enumerate(boundaries):
        if week_no is None or week_no in layout:
            continue
        section_end = (
            boundaries[position + 1][0]
            if position + 1 < len(boundaries)
            else len(lines)
        )
        layout[week_no] = {"header_idx": idx, "section_end": section_end}
    return layout


def _day_blocks_in_section(lines: list[str], start: int, end: int) -> list[dict[str, Any]]:
    """Partition a week section into day blocks keyed by countdown/weekday."""
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for idx in range(max(start, 0), min(end, len(lines))):
        raw_line = lines[idx]
        if _is_day_block_start(raw_line):
            if current is not None:
                blocks.append(current)
            header_match = _MARKDOWN_HEADER.match(raw_line)
            heading = header_match.group(2).strip() if header_match else raw_line.strip()
            current = {
                "countdown": _normalise_countdown_label(heading),
                "weekday": _first_weekday_in_text(heading),
                "text": [heading],
            }
            continue
        if current is not None:
            cleaned = _BULLET_PREFIX.sub("", raw_line).strip()
            if cleaned:
                current["text"].append(cleaned)
    if current is not None:
        blocks.append(current)
    return blocks


def _role_survives_day_block(
    *,
    role: dict[str, Any],
    countdown_label: str,
    day_blocks: list[dict[str, Any]],
) -> bool:
    """Exact role/day survival check.

    The role's own countdown/weekday day block must exist and carry the role's
    identity marker. A matching marker somewhere else in the week (a repeated
    exercise, or a generic role name on another day) does not count — that was
    the loophole that let the wrong session appear to satisfy a missing one.
    """
    role_countdown = countdown_label or _role_countdown_label(role)
    role_weekday = _canonical_weekday(_role_weekday(role))
    markers = _role_render_markers(role)

    for block in day_blocks:
        block_countdown = str(block.get("countdown") or "")
        block_weekday = str(block.get("weekday") or "")
        same_day = False
        if role_countdown and block_countdown:
            same_day = block_countdown == role_countdown
        elif role_weekday and block_weekday:
            same_day = block_weekday == role_weekday
        if not same_day:
            continue
        rendered = _normalise_render_match_text(" ".join(block.get("text") or []))
        if not markers or any(marker in rendered for marker in markers):
            return True
    return False


def _restored_day_heading(role: dict[str, Any], countdown_label: str) -> str:
    label = (
        str(
            role.get("athlete_facing_label")
            or role.get("label")
            or role.get("role_key")
            or "Session"
        ).strip()
        or "Session"
    )
    weekday = _role_weekday(role)
    if weekday and countdown_label:
        return f"### {weekday.title()} ({countdown_label}) — {label}"
    if countdown_label:
        return f"### {countdown_label} — {label}"
    if weekday:
        return f"### {weekday.title()} — {label}"
    return f"### {label}"


def repair_stage2_structural_text(
    *,
    planning_brief: dict,
    final_plan_text: str,
    validator_report: dict | None = None,
) -> dict[str, Any]:
    """Restore known Stage 1 session roles that Stage 2 dropped, in place.

    This is deliberately narrow and fail-closed:

    * It only restores a role that carries **complete authoritative content**
      (``display_text`` or fully-priced ``selected_exercise_assignments``); it
      never synthesises a body from a category or from preferred exercise names.
    * It only restores app-rendered mandatory work — non-mandatory and
      coach-owned context roles are left to the validator.
    * It matches **exact role/day identity** and inserts the restored day into
      the role's own canonical week section. It never appends a second week or
      phase schedule, and it never restores a role whose canonical week is not
      already rendered.

    Every role it cannot fully and safely restore is reported in ``unresolved``
    so the caller can hold the plan instead of publishing a partial repair.
    """
    report = validator_report or _validator_report_with_required_countdown_sessions(
        planning_brief=planning_brief,
        final_plan_text=final_plan_text,
    )
    findings = structural_integrity_findings(report)
    if not findings:
        return {"text": final_plan_text, "applied": [], "unresolved": []}

    role_map = planning_brief.get("weekly_role_map") or {}
    weeks = [week for week in (role_map.get("weeks") or []) if isinstance(week, dict)]
    if not weeks:
        return {"text": final_plan_text, "applied": [], "unresolved": findings}

    lines = (final_plan_text or "").split("\n")
    layout = _week_section_layout(lines)

    applied: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    # (insert_at_index, [lines]) collected then applied bottom-up so an earlier
    # insertion never shifts a later insertion's index.
    pending_inserts: list[tuple[int, list[str]]] = []

    for week in weeks:
        week_index = int(week.get("week_index", 0) or 0)
        if week_index <= 0:
            continue
        roles = [role for role in (week.get("session_roles") or []) if isinstance(role, dict)]
        if not roles:
            continue

        phase = str(week.get("phase") or "").strip().upper()
        section = layout.get(week_index)
        day_blocks = (
            _day_blocks_in_section(lines, section["header_idx"] + 1, section["section_end"])
            if section
            else []
        )

        week_insert_lines: list[str] = []
        for role in roles:
            countdown_label = _role_countdown_from_week(week, role)
            if section and _role_survives_day_block(
                role=role,
                countdown_label=countdown_label,
                day_blocks=day_blocks,
            ):
                continue

            # Role is missing from its canonical day.
            if not _role_requires_authoritative_render(role):
                # Non-mandatory / coach-owned context: not this repair's to author.
                continue

            unresolved_entry = {
                "code": "structural_role_repair_unresolved",
                "week_index": week_index,
                "phase": phase,
                "role_key": role.get("role_key"),
                "countdown_label": countdown_label,
            }
            if section is None:
                unresolved_entry["message"] = (
                    "Canonical week is not rendered; cannot restore in place."
                )
                unresolved.append(unresolved_entry)
                continue

            body = _authoritative_role_body(role)
            if not body:
                unresolved_entry["message"] = (
                    "Missing role has no complete authoritative content to restore."
                )
                unresolved.append(unresolved_entry)
                continue

            heading = _restored_day_heading(role, countdown_label)
            week_insert_lines.extend(["", heading, *body])
            applied.append(
                {
                    "week_index": week_index,
                    "phase": phase,
                    "role_key": role.get("role_key"),
                    "countdown_label": countdown_label,
                }
            )

        if week_insert_lines and section is not None:
            pending_inserts.append((section["section_end"], week_insert_lines))

    if not pending_inserts:
        return {"text": final_plan_text, "applied": applied, "unresolved": unresolved}

    for insert_at, new_lines in sorted(pending_inserts, key=lambda item: item[0], reverse=True):
        lines[insert_at:insert_at] = new_lines

    return {"text": "\n".join(lines), "applied": applied, "unresolved": unresolved}


def structural_integrity_findings(validator_report: dict | None) -> list[dict[str, Any]]:
    report = validator_report if isinstance(validator_report, dict) else {}
    findings: list[dict[str, Any]] = []
    for key in ("errors", "blocking_warnings", "review_flags", "warnings"):
        for item in report.get(key) or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("code") or "").strip() in STRUCTURAL_INTEGRITY_CODES:
                findings.append(dict(item))
    seen: set[tuple] = set()
    deduped: list[dict[str, Any]] = []
    for item in findings:
        identity = (
            str(item.get("code") or "").strip(),
            str(item.get("phase") or "").strip(),
            str(item.get("week_index") or "").strip(),
            str(item.get("session_index") or "").strip(),
            str(item.get("requirement") or "").strip(),
            str(item.get("role_key") or "").strip(),
        )
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(item)
    return deduped


def apply_structural_integrity_hold(validator_report: dict) -> dict:
    findings = structural_integrity_findings(validator_report)
    if not findings:
        return validator_report
    report = dict(validator_report)
    errors = [dict(item) for item in report.get("errors") or [] if isinstance(item, dict)]
    errors.append(
        {
            "code": "structural_integrity_failure",
            "severity": "blocker",
            "message": "Stage 2 output still has unresolved Stage 1 structural loss.",
            "structural_findings": findings,
        }
    )
    report["errors"] = errors
    report["release_decision"] = "hold"
    report["is_athlete_releasable"] = False
    report["is_publishable"] = False
    report["validator_findings_observational"] = False
    return report


def _required_countdown_session_warnings(
    *,
    planning_brief: dict,
    final_plan_text: str,
) -> list[dict[str, Any]]:
    sequence = _selected_countdown_sequence(planning_brief)
    if not sequence:
        return []

    rendered_sections = _rendered_countdown_sections(final_plan_text)
    warnings: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for role in sequence:
        if _is_hidden_context_role(role):
            continue
        if role.get("render_mandatory") is False:
            continue

        countdown_label = _role_countdown_label(role)
        if not countdown_label or countdown_label == "D-0":
            continue

        role_key = str(role.get("role_key") or "").strip()
        identity = (countdown_label, role_key)
        if identity in seen:
            continue
        seen.add(identity)

        if _required_role_survives_render(
            role=role,
            countdown_label=countdown_label,
            rendered_sections=rendered_sections,
        ):
            continue

        display_label = _role_display_label(role, countdown_label)
        warnings.append(
            {
                "code": "late_fight_missing_required_countdown_session",
                "message": "Selected countdown session is missing from the final rendered plan.",
                "expected_countdown_label": countdown_label,
                "expected_display_label": display_label,
                "role_key": role_key,
                "category": role.get("category"),
                "stress_class": role.get("stress_class"),
                "scheduled_day_hint": role.get("scheduled_day_hint"),
                "rewrite_hint": f"Restore the selected countdown card: {display_label}.",
            }
        )

    return warnings


def _validator_report_with_required_countdown_sessions(
    *,
    planning_brief: dict,
    final_plan_text: str,
) -> dict:
    validator_report = validate_stage2_output(
        planning_brief=planning_brief,
        final_plan_text=final_plan_text,
    )
    validator_report = postprocess_stage2_validator_report(
        planning_brief=planning_brief,
        final_plan_text=final_plan_text,
        validator_report=validator_report,
    )

    warnings = list(validator_report.get("warnings", []) or [])
    warnings.extend(
        _required_countdown_session_warnings(
            planning_brief=planning_brief,
            final_plan_text=final_plan_text,
        )
    )

    return {
        **validator_report,
        "warnings": warnings,
    }


def _warning_buckets(validator_report: dict) -> tuple[list[dict], list[dict]]:
    warnings = list(validator_report.get("warnings", []) or [])
    blocking_warnings = [
        warning
        for warning in warnings
        if is_hard_stage2_blocker(str(warning.get("code") or ""))
    ]
    review_flags = [
        warning
        for warning in warnings
        if not is_hard_stage2_blocker(str(warning.get("code") or ""))
    ]
    return blocking_warnings, review_flags


def _enrich_validator_report(validator_report: dict) -> dict:
    blocking_warnings, review_flags = _warning_buckets(validator_report)
    return {
        **validator_report,
        "blocking_warnings": blocking_warnings,
        "review_flags": review_flags,
        "blocking_warning_count": len(blocking_warnings),
        "review_flag_count": len(review_flags),
        "is_publishable": not validator_report.get("errors") and not blocking_warnings,
    }


def _review_status(validator_report: dict) -> str:
    if validator_report.get("errors"):
        return _STATUS_FAIL
    if validator_report.get("blocking_warnings"):
        return _STATUS_WARN
    return _STATUS_PASS


def _warning_detail_line(warning: dict) -> str:
    if warning.get("code") == "missing_required_element":
        phase = warning.get("phase", "Unknown phase")
        requirement = str(warning.get("requirement", "required element")).replace("_", " ")
        return f"Restore {requirement} in {phase}."
    if warning.get("code") == "weak_anchor_session":
        return (
            f"Strength session quality drifted in {warning.get('phase', 'Unknown phase')} "
            f"session {warning.get('session_index', '?')}; restore a real anchor."
        )
    if warning.get("code") == "support_takeover_before_anchor":
        return (
            f"Move support work behind the anchor in {warning.get('phase', 'Unknown phase')} "
            f"session {warning.get('session_index', '?')}."
        )
    if warning.get("code") == "conditional_conditioning_choice":
        return "Resolve conditioning choices into one primary prescription and at most one fallback."
    if warning.get("code") == "too_many_fallbacks":
        return "Collapse extra fallback branches so the session reads like a final prescription."
    if warning.get("code") == "unresolved_access_fallback":
        return "Remove fallback branches unless a real unresolved access contingency remains."
    if warning.get("code") == "template_like_session_render":
        return "Rewrite template-like session blocks into one clean athlete-facing prescription."
    if warning.get("code") == "taper_option_overload":
        return "Simplify taper sessions so they stay short, decisive, and low-noise."
    if warning.get("code") == "equipment_incongruent_selection":
        return "Replace equipment-invalid selections with same-role options that match the athlete profile."
    if warning.get("code") == "missing_week_session_role":
        return "Restore the missing weekly session role so each active week stays structurally complete."
    if warning.get("code") == "late_camp_session_incomplete":
        return "Restore late-camp week structure so the final weeks stay complete and athlete-ready."
    if warning.get("code") == "weekly_session_overage":
        return "Trim extra weekly sessions so the final plan does not exceed the athlete's requested sessions per week."
    if warning.get("code") == "weekly_rhythm_broken":
        return "Restore the default boxer weekly rhythm with recovery immediately before the primary strength day."
    if warning.get("code") in {"gimmick_name", "overstyled_drill_name"}:
        return "Replace overstyled drill naming with plain coach-readable language."
    if warning.get("code") == "option_overload":
        return "Collapse choices to two or fewer safe options, or resolve the line to one final prescription."
    if warning.get("code") == "generic_filler_phrase":
        return "Replace low-trust filler with concrete coach language and next actions."
    if warning.get("code") == "generic_instruction_opener":
        return "Replace generic opener wording with a direct verb-led instruction."
    if warning.get("code") == "generic_motivation_cliche":
        return "Replace generic motivation cliches with specific confidence or execution language."
    if warning.get("code") == "hedged_adjustment_without_decision":
        return "Rewrite hedged adjustment language into one clear coaching call with a short why."
    if warning.get("code") == "empty_safety_language":
        return "Replace empty safety lines with operational guardrails that change what the athlete does next."
    if warning.get("code") == "late_fight_missing_required_countdown_session":
        display_label = str(
            warning.get("expected_display_label")
            or warning.get("expected_countdown_label")
            or "the selected countdown card"
        ).strip()
        return f"Restore the selected countdown card: {display_label}."
    if warning.get("code") == "late_fight_missing_countdown_header":
        return "Restore D-X countdown headers for every active late-fight day."
    if warning.get("code") == "late_fight_countdown_header_format":
        return "Rewrite countdown headers as D-X (Weekday) — session role."
    if warning.get("code") == "late_fight_d0_protocol_expanded":
        return "Reduce D-0 to fight day protocol only."
    if warning.get("code") == "coach_owned_sparring_overdetailed":
        return "Reduce hard sparring / contact days to the minimal hard-sparring/contact label and one freshness note."
    if warning.get("code") == "internal_render_contract_leak":
        return "Remove internal scaffolding labels from the athlete-facing plan."
    if warning.get("code") == "missing_injury_lead_summary":
        return "Add a short lead summary for active injury constraints."
    if warning.get("code") == "missing_weight_cut_lead_summary":
        return "Add a short lead summary for active weight-cut constraints."
    rewrite_hint = str(warning.get("rewrite_hint") or "").strip()
    if rewrite_hint:
        return rewrite_hint
    if warning.get("code") == "sport_language_leak":
        return "Rewrite cross-sport language so the plan reads cleanly for the athlete's sport."
    return str(warning.get("message", "Unknown validation warning."))


def _build_review_summary(validator_report: dict, status: str) -> tuple[str, list[str]]:
    errors = list(validator_report.get("errors", []) or [])
    blocking_warnings = list(validator_report.get("blocking_warnings", []) or [])
    summary_parts: list[str] = []
    detail_lines: list[str] = []

    if errors:
        summary_parts.append(f"{len(errors)} error{'s' if len(errors) != 1 else ''}")
        for error in errors:
            if error.get("code") == "restriction_violation":
                detail_lines.append(
                    f"Remove or replace restricted line '{error.get('line', '')}' ({error.get('restriction', 'unknown restriction')})."
                )
            else:
                detail_lines.append(str(error.get("message", "Unknown validation error.")))

    if blocking_warnings:
        summary_parts.append(f"{len(blocking_warnings)} blocking warning{'s' if len(blocking_warnings) != 1 else ''}")
        detail_lines.extend(_warning_detail_line(warning) for warning in blocking_warnings)

    if status == _STATUS_PASS:
        summary = "PASS: final plan cleared validation."
    elif status == _STATUS_WARN:
        summary = "WARN: final plan still has blocking review issues and needs revision before release"
        if summary_parts:
            summary += f" ({', '.join(summary_parts)})."
        else:
            summary += "."
    else:
        summary = "FAIL: final plan needs revision before use"
        if summary_parts:
            summary += f" ({', '.join(summary_parts)})."
        else:
            summary += "."

    return summary, detail_lines


def build_stage2_package(*, stage1_result: dict) -> dict:
    from .planner_authority_integrity import late_physical_planner_preflight
    stage1_result = _require_dict(stage1_result, name="stage1_result")
    planning_brief = _require_dict(_require_stage1_field(stage1_result, "planning_brief"), name="planning_brief")
    stage2_payload = _require_dict(_require_stage1_field(stage1_result, "stage2_payload"), name="stage2_payload")
    handoff_text = str(_require_stage1_field(stage1_result, "stage2_handoff_text") or "")

    phase_count = len((planning_brief.get("phase_strategy") or {}).keys())
    restriction_count = len((planning_brief.get("restrictions") or []))
    slot_count = _count_candidate_slots(planning_brief)
    preflight_findings = late_physical_planner_preflight(planning_brief)

    return {
        "status": "REVIEW_REQUIRED" if preflight_findings else _STATUS_READY,
        "planner_preflight_findings": preflight_findings,
        "planning_brief": planning_brief,
        "stage2_payload": stage2_payload,
        "handoff_text": handoff_text,
        "draft_plan_text": str(stage1_result.get("plan_text", "") or ""),
        "coach_notes": str(stage1_result.get("coach_notes", "") or ""),
        "summary": f"Stage 2 package ready: {phase_count} phase(s), {restriction_count} restriction(s), {slot_count} candidate slot(s).",
    }


def review_stage2_output(*, planning_brief: dict, final_plan_text: str) -> dict:
    planning_brief = _require_dict(planning_brief, name="planning_brief")
    validator_report = apply_stage2_release_policy(
        _enrich_validator_report(
            _validator_report_with_required_countdown_sessions(
                planning_brief=planning_brief,
                final_plan_text=final_plan_text,
            )
        )
    )
    status = _review_status(validator_report)
    summary, summary_lines = _build_review_summary(validator_report, status)
    return {
        "status": status,
        "validator_report": validator_report,
        "summary": summary,
        "summary_lines": summary_lines,
        "needs_retry": status != _STATUS_PASS,
    }


def build_stage2_retry(
    *,
    stage1_result: dict,
    final_plan_text: str,
    validator_report: dict | None = None,
) -> dict:
    stage1_result = _require_dict(stage1_result, name="stage1_result")
    planning_brief = _require_dict(_require_stage1_field(stage1_result, "planning_brief"), name="planning_brief")

    if validator_report is None:
        review = review_stage2_output(planning_brief=planning_brief, final_plan_text=final_plan_text)
        validator_report = review["validator_report"]
    else:
        validator_report = apply_stage2_release_policy(
            _enrich_validator_report(_require_dict(validator_report, name="validator_report"))
        )

    status = _review_status(validator_report)
    summary, summary_lines = _build_review_summary(validator_report, status)
    admin_blockers = admin_review_blocking_findings(validator_report)
    if admin_blockers and status == _STATUS_PASS:
        status = _STATUS_WARN
        summary = "WARN: final plan has admin-review blocking issues and needs revision before release"
        summary_lines = [_warning_detail_line(warning) for warning in admin_blockers]

    missing_closed_conditioning = any(
        isinstance(item, dict)
        and str(item.get("code") or "") == "missing_selected_conditioning_assignment"
        for item in validator_report.get("errors", []) or []
    )
    if validator_report.get("release_decision") != "hold" and not missing_closed_conditioning:
        return {
            "status": status,
            "validator_report": validator_report,
            "summary": summary,
            "summary_lines": summary_lines,
            "needs_retry": False,
            "repair_prompt": None,
        }

    goal_failures = [
        item
        for field in ("errors", "blocking_warnings")
        for item in validator_report.get(field, []) or []
        if isinstance(item, dict)
        and str(item.get("code") or "").strip() == "goal_preservation_failed"
    ]
    if goal_failures:
        return {
            "status": _STATUS_FAIL,
            "validator_report": validator_report,
            "summary": "FAIL: selected goal coverage requires deterministic planner repair",
            "summary_lines": summary_lines,
            "needs_retry": False,
            "requires_planner_regeneration": True,
            "repair_prompt": None,
        }

    repair_report = prompt_safe_validator_report(validator_report)
    repair_prompt = build_stage2_repair_prompt(
        planning_brief=planning_brief,
        failed_plan_text=final_plan_text,
        validator_report=repair_report,
    )
    return {
        "status": status,
        "validator_report": validator_report,
        "summary": summary,
        "summary_lines": summary_lines,
        "needs_retry": True,
        "repair_prompt": repair_prompt,
    }
