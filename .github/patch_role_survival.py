from pathlib import Path

PIPELINE = Path("fightcamp/stage2_pipeline.py")
TEST = Path("tests/test_stage2_required_gap_fill_survival.py")

pipeline = PIPELINE.read_text()

anchor = '''def _rendered_countdown_labels(final_plan_text: str) -> set[str]:
    return {
        f"D-{int(match.group(1))}"
        for match in _COUNTDOWN_HEADER_RE.finditer(final_plan_text or "")
    }
'''

replacement = '''def _rendered_countdown_labels(final_plan_text: str) -> set[str]:
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
    role_key = re.sub(r"\\bday\\b$", "", role_key).strip()
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
'''

if anchor not in pipeline:
    raise SystemExit("rendered-countdown helper anchor not found")
pipeline = pipeline.replace(anchor, replacement, 1)

old = '''    rendered_labels = _rendered_countdown_labels(final_plan_text)
    warnings: list[dict[str, Any]] = []
'''
new = '''    rendered_sections = _rendered_countdown_sections(final_plan_text)
    warnings: list[dict[str, Any]] = []
'''
if old not in pipeline:
    raise SystemExit("rendered_labels anchor not found")
pipeline = pipeline.replace(old, new, 1)

old = '''        if countdown_label in rendered_labels:
            continue
'''
new = '''        if _required_role_survives_render(
            role=role,
            countdown_label=countdown_label,
            rendered_sections=rendered_sections,
        ):
            continue
'''
if old not in pipeline:
    raise SystemExit("header-only survival check anchor not found")
pipeline = pipeline.replace(old, new, 1)

PIPELINE.write_text(pipeline)

TEST.write_text('''from fightcamp.stage2_pipeline import _required_countdown_session_warnings\n\n\n_ROLE_LABELS = {\n    "strength_touch_day": "Strength Touch",\n    "tactical_watch": "Fight Tactical Watch",\n    "recovery_reset": "Recovery Reset",\n    "neural_power_day": "Neural Power",\n}\n\n\ndef _role(offset: int, role_key: str, category: str) -> dict:\n    return {\n        "countdown_offset": offset,\n        "countdown_label": f"D-{offset}",\n        "scheduled_countdown_label": f"D-{offset}",\n        "scheduled_day_hint": {\n            14: "friday",\n            11: "monday",\n            9: "wednesday",\n            8: "thursday",\n        }[offset],\n        "role_key": role_key,\n        "category": category,\n        "athlete_facing_label": _ROLE_LABELS[role_key],\n        "render_mandatory": True,\n    }\n\n\ndef _planning_brief() -> dict:\n    return {\n        "late_fight_session_sequence": [\n            _role(14, "strength_touch_day", "strength"),\n            _role(11, "tactical_watch", "support_insert"),\n            _role(9, "recovery_reset", "support_insert"),\n            _role(8, "neural_power_day", "power"),\n        ]\n    }\n\n\ndef test_final_plan_blocks_if_required_gap_fill_sessions_disappear():\n    warnings = _required_countdown_session_warnings(\n        planning_brief=_planning_brief(),\n        final_plan_text="""\nD-14 (Friday) — Strength touch\nD-8 (Thursday) — Neural power\n""",\n    )\n\n    missing = {\n        warning["expected_countdown_label"]\n        for warning in warnings\n        if warning["code"] == "late_fight_missing_required_countdown_session"\n    }\n    assert missing == {"D-11", "D-9"}\n\n\ndef test_final_plan_accepts_gap_fill_sessions_when_they_survive_rendering():\n    warnings = _required_countdown_session_warnings(\n        planning_brief=_planning_brief(),\n        final_plan_text="""\nD-14 (Friday) — Strength touch\nD-11 (Monday) — Fight Tactical Watch\nD-9 (Wednesday) — Recovery Reset\nD-8 (Thursday) — Neural power\n""",\n    )\n\n    assert warnings == []\n\n\ndef test_same_day_header_does_not_hide_a_missing_required_role():\n    planning_brief = {\n        "late_fight_session_sequence": [\n            _role(9, "tactical_watch", "support_insert"),\n            _role(9, "recovery_reset", "support_insert"),\n        ]\n    }\n\n    warnings = _required_countdown_session_warnings(\n        planning_brief=planning_brief,\n        final_plan_text="""\nD-9 (Wednesday) — Fight Tactical Watch\n- Review the selected tactical cue.\n""",\n    )\n\n    assert {warning["role_key"] for warning in warnings} == {"recovery_reset"}\n\n\ndef test_same_day_roles_both_pass_when_both_survive():\n    planning_brief = {\n        "late_fight_session_sequence": [\n            _role(9, "tactical_watch", "support_insert"),\n            _role(9, "recovery_reset", "support_insert"),\n        ]\n    }\n\n    warnings = _required_countdown_session_warnings(\n        planning_brief=planning_brief,\n        final_plan_text="""\nD-9 (Wednesday) — Fight Tactical Watch\n- Review the selected tactical cue.\n\nRecovery Reset\n- Easy breathing and mobility.\n""",\n    )\n\n    assert warnings == []\n''')
