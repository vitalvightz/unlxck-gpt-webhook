from pathlib import Path
import re


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"marker not found in {path}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1))


# 1) Normal role-budget owner: required conditioning systems get first claim on
# the existing adaptive phase/limiter order. No universal SPP pair is invented.
p = Path("fightcamp/stage2_role_map.py")
text = p.read_text()
if "def _prioritize_must_keep_conditioning_systems(" not in text:
    match = re.search(
        r"(def _preferred_boxer_conditioning_sequence\(.*?^\s*return ordered\n)",
        text,
        flags=re.S | re.M,
    )
    if not match:
        raise SystemExit("preferred boxer conditioning helper not found")
    helper = '''\n\ndef _prioritize_must_keep_conditioning_systems(\n    conditioning_sequence: list[str],\n    must_keep: list[str],\n) -> list[str]:\n    \"\"\"Prioritize required systems without hard-coding an SPP pair.\"\"\"\n    supported = {\"aerobic\", \"glycolytic\", \"alactic\"}\n    required = [\n        str(token).strip().lower()\n        for token in clean_list(must_keep)\n        if str(token).strip().lower() in supported\n    ]\n    ordered: list[str] = []\n    for system in [*required, *conditioning_sequence]:\n        normalized = str(system).strip().lower()\n        if normalized in supported and normalized not in ordered:\n            ordered.append(normalized)\n    return ordered\n'''
    text = text[: match.end()] + helper + text[match.end() :]

old = '''        if sport_key == "boxing" and week_entry.get("phase", "").upper() in {"GPP", "SPP"} and int(session_counts.get("conditioning", 0) or 0) >= 2:\n            conditioning_sequence = _preferred_boxer_conditioning_sequence(\n                week_entry.get("phase", ""),\n                conditioning_sequence,\n            )\n        session_roles: list[dict] = []\n'''
new = '''        if sport_key == "boxing" and week_entry.get("phase", "").upper() in {"GPP", "SPP"} and int(session_counts.get("conditioning", 0) or 0) >= 2:\n            conditioning_sequence = _preferred_boxer_conditioning_sequence(\n                week_entry.get("phase", ""),\n                conditioning_sequence,\n            )\n        resolved_must_keep = clean_list(\n            (week_entry.get("resolved_rule_state") or {}).get(\n                "must_keep", week_entry.get("must_keep", [])\n            )\n        )\n        conditioning_sequence = _prioritize_must_keep_conditioning_systems(\n            conditioning_sequence, resolved_must_keep\n        )\n        session_roles: list[dict] = []\n'''
if old not in text:
    raise SystemExit("conditioning sequence insertion point not found")
p.write_text(text.replace(old, new, 1))


# 2) Handoff owner: derive the parent requirements from the actual D-13 parent
# week and pass them into the existing finished late-fight path.
p = Path("fightcamp/camp_week_fillers.py")
text = p.read_text()
old = '''    finished_tail = build_finished_late_fight_tail(\n        days_until_fight,\n        athlete_model,\n        start_day=13,\n    )\n'''
new = '''    parent_week = _week_for_d_day(weeks, 13)\n    parent_state = dict(parent_week.get("resolved_rule_state") or {}) if parent_week else {}\n    parent_required = list(\n        parent_state.get("must_keep")\n        or (parent_week.get("must_keep") if parent_week else [])\n        or []\n    )\n    parent_required_conditioning = [\n        str(token).strip().lower()\n        for token in parent_required\n        if str(token).strip().lower() in {"aerobic", "glycolytic", "alactic"}\n    ]\n    finished_tail = build_finished_late_fight_tail(\n        days_until_fight,\n        athlete_model,\n        start_day=13,\n        parent_required_conditioning_systems=parent_required_conditioning,\n    )\n'''
if old not in text:
    raise SystemExit("finished-tail call marker not found")
text = text.replace(old, new, 1)
old = '''            week["late_fight_tail_complete_week"] = bool(\n                calendar_d_days and max(calendar_d_days) <= 13\n            )\n            summaries = [\n'''
new = '''            week["late_fight_tail_complete_week"] = bool(\n                calendar_d_days and max(calendar_d_days) <= 13\n            )\n            week_state = dict(week.get("resolved_rule_state") or {})\n            raw_required = list(week_state.get("must_keep") or week.get("must_keep") or [])\n            week["late_fight_tail_parent_requirements"] = {\n                "source": "normal_week_before_d13_handoff",\n                "required_conditioning_systems": [\n                    str(token).strip().lower()\n                    for token in raw_required\n                    if str(token).strip().lower() in {"aerobic", "glycolytic", "alactic"}\n                ],\n                "primary_strength_required": any(\n                    str(token).strip().lower() == "primary_strength"\n                    for token in raw_required\n                ),\n                "handoff_rule": (\n                    "Preserve parent-week intent only where the finished D-13 "\n                    "late-fight path can express it legally; countdown safety "\n                    "always wins and forbidden hard work is never resurrected."\n                ),\n            }\n            summaries = [\n'''
if old not in text:
    raise SystemExit("tail metadata insertion point not found")
p.write_text(text.replace(old, new, 1))


# 3) Existing late-fight owner receives parent intent as input context.
p = Path("fightcamp/late_fight_tail.py")
text = p.read_text()
old = '''def build_finished_late_fight_tail(\n    source_days_until_fight: Any,\n    athlete_model: dict[str, Any],\n    *,\n    start_day: int = 13,\n) -> dict[str, Any]:\n'''
new = '''def build_finished_late_fight_tail(\n    source_days_until_fight: Any,\n    athlete_model: dict[str, Any],\n    *,\n    start_day: int = 13,\n    parent_required_conditioning_systems: list[str] | None = None,\n) -> dict[str, Any]:\n'''
if old not in text:
    raise SystemExit("late tail signature marker not found")
text = text.replace(old, new, 1)
old = '''    tail_athlete = late_fight._shifted_segment_athlete_model(\n        source_days,\n        start,\n        athlete_model,\n    )\n\n    base_spec = late_fight._build_late_fight_plan_spec(start, tail_athlete)\n'''
new = '''    tail_athlete = late_fight._shifted_segment_athlete_model(\n        source_days,\n        start,\n        athlete_model,\n    )\n    tail_athlete["late_fight_parent_required_conditioning_systems"] = [\n        str(system).strip().lower()\n        for system in (parent_required_conditioning_systems or [])\n        if str(system).strip().lower() in {"aerobic", "glycolytic", "alactic"}\n    ]\n\n    base_spec = late_fight._build_late_fight_plan_spec(start, tail_athlete)\n'''
if old not in text:
    raise SystemExit("late tail athlete marker not found")
p.write_text(text.replace(old, new, 1))


# 4) Canonical D-13 role selector: if the parent SPP week requires alactic and
# D-13 safety still permits it, include the existing alactic sharpness role.
# Glycolytic is NOT restored because standalone glycolytic is explicitly banned
# in D-13..D-8. This is intent transfer through the existing late-fight owner,
# not filler-created stress.
p = Path("fightcamp/stage2_payload_late_fight.py")
text = p.read_text()
old = '''    if mode == "pre_fight_compressed_payload":\n        strength_selection_rule = "Use one meaningful strength or power touch only."\n'''
new = '''    if mode == "pre_fight_compressed_payload":\n        parent_required_conditioning = {\n            str(system).strip().lower()\n            for system in clean_list(\n                athlete_model.get("late_fight_parent_required_conditioning_systems", [])\n            )\n        }\n        strength_selection_rule = "Use one meaningful strength or power touch only."\n'''
if old not in text:
    raise SystemExit("pre-fight candidate marker not found")
text = text.replace(old, new, 1)
old = '''        if not _suppress_standalone_glycolytic(preserved_hard_days, athlete_model):\n            candidates.append(\n                _late_fight_role_entry(\n                    category="conditioning",\n                    role_key="light_fight_pace_touch_day",\n'''
new = '''        if "alactic" in parent_required_conditioning and not preserved_hard_days:\n            candidates.append(\n                _late_fight_role_entry(\n                    category="conditioning",\n                    role_key="alactic_sharpness_day",\n                    preferred_pool="conditioning_slots",\n                    preferred_system="alactic",\n                    selection_rule=(\n                        "Carry the parent week's required speed-system intent as one brief alactic sharpness touch. "\n                        "This is a freshness-preserving expression, not a conditioning build."\n                    ),\n                    placement_rule="Keep this brief, crisp, and away from collision load; never turn it into density work.",\n                    selection_priority=107,\n                    required=True,\n                    legal_countdown_labels=legal_countdown_labels,\n                )\n            )\n        if not _suppress_standalone_glycolytic(preserved_hard_days, athlete_model):\n            candidates.append(\n                _late_fight_role_entry(\n                    category="conditioning",\n                    role_key="light_fight_pace_touch_day",\n'''
if old not in text:
    raise SystemExit("late-fight conditioning insertion marker not found")
p.write_text(text.replace(old, new, 1))


# 5) Finalizer receives the handoff contract and cannot silently delete the
# already-surviving role map.
p = Path("fightcamp/stage2_finalizer_packet_impl.py")
text = p.read_text()
old = '''                    "intentional_compression": week.get("intentional_compression"),\n                    "session_count_summary": _session_count_summary(week, athlete_model),\n'''
new = '''                    "intentional_compression": week.get("intentional_compression"),\n                    "late_fight_tail_days": week.get("late_fight_tail_days"),\n                    "late_fight_tail_complete_week": week.get("late_fight_tail_complete_week"),\n                    "late_fight_tail_parent_requirements": week.get("late_fight_tail_parent_requirements"),\n                    "session_count_summary": _session_count_summary(week, athlete_model),\n'''
if old not in text:
    raise SystemExit("finalizer compact-week marker not found")
text = text.replace(old, new, 1)
old = '''            "weekly_role_map.weeks[*].calendar_days is the only authority for weekday and D-day labels.",\n'''
new = '''            "weekly_role_map.weeks[*].calendar_days is the only authority for weekday and D-day labels.",\n            "Every athlete-visible weekly_role_map.weeks[*].session_roles entry is a deterministic structural requirement. Render each surviving role exactly once on its scheduled day; do not omit it, merge it away, move it to another week, or replace it with a different role. The finalizer may improve athlete-facing wording and express the already-selected compliant exercise, but it does not own weekly role survival.",\n            "When late_fight_tail_days are present, the finished D-13 late-fight tail owns those days. late_fight_tail_parent_requirements records parent-week intent crossing the boundary, but never authorizes restoring work that countdown safety removed or softened.",\n'''
if old not in text:
    raise SystemExit("finalizer hard-rule marker not found")
p.write_text(text.replace(old, new, 1))


# 6) Release policy: the three deterministic authority failures cannot publish.
p = Path("fightcamp/stage2_policy.py")
text = p.read_text()
old = '''_RELEASE_COLLECTION_FIELDS = (\n    "errors",\n    "warnings",\n    "review_flags",\n    "blocking_warnings",\n)\n'''
new = '''_RELEASE_COLLECTION_FIELDS = (\n    "errors",\n    "warnings",\n    "review_flags",\n    "blocking_warnings",\n)\n_RELEASE_HOLD_CODES = frozenset(\n    {\n        "missing_week_session_role",\n        "late_camp_session_incomplete",\n        "goal_preservation_failed",\n    }\n)\n'''
if old not in text:
    raise SystemExit("release collection marker not found")
text = text.replace(old, new, 1)
old = '''    quality_findings = _dedupe_findings([*all_findings, *malformed_findings])\n    admin_findings = admin_review_blocking_findings(collections)\n    release_decision = "publish_with_flags" if quality_findings else "publish"\n\n    return {\n'''
new = '''    quality_findings = _dedupe_findings([*all_findings, *malformed_findings])\n    admin_findings = admin_review_blocking_findings(collections)\n    release_hold_findings = [\n        item\n        for item in quality_findings\n        if str(item.get("code") or "").strip() in _RELEASE_HOLD_CODES\n    ]\n    release_decision = (\n        "hold"\n        if release_hold_findings\n        else ("publish_with_flags" if quality_findings else "publish")\n    )\n\n    return {\n'''
if old not in text:
    raise SystemExit("release decision marker not found")
text = text.replace(old, new, 1)
old = '''        "release_policy_malformed_fields": malformed_fields,\n        "validator_findings_observational": True,\n        "release_decision": release_decision,\n        "is_athlete_releasable": True,\n        "is_publishable": True,\n'''
new = '''        "release_policy_malformed_fields": malformed_fields,\n        "release_hold_findings": release_hold_findings,\n        "release_hold_finding_count": len(release_hold_findings),\n        "validator_findings_observational": not bool(release_hold_findings),\n        "release_decision": release_decision,\n        "is_athlete_releasable": not bool(release_hold_findings),\n        "is_publishable": not bool(release_hold_findings),\n'''
if old not in text:
    raise SystemExit("release return marker not found")
p.write_text(text.replace(old, new, 1))


# 7) Focused regressions, including the production-shaped D-22 -> D-13 handoff.
Path("tests/test_d14_role_authority_surgical.py").write_text(r'''from __future__ import annotations

from fightcamp import camp_week_fillers
from fightcamp.late_fight_tail import build_finished_late_fight_tail
from fightcamp.stage2_finalizer_packet_impl import _compact_weekly_role_map
from fightcamp.stage2_policy import apply_stage2_release_policy
from fightcamp.stage2_role_map import _prioritize_must_keep_conditioning_systems


def test_required_conditioning_systems_take_first_claim_without_fixed_pair() -> None:
    assert _prioritize_must_keep_conditioning_systems(
        ["aerobic", "glycolytic", "alactic"],
        ["rehab", "glycolytic", "alactic", "primary_strength"],
    ) == ["glycolytic", "alactic", "aerobic"]
    assert _prioritize_must_keep_conditioning_systems(
        ["glycolytic", "aerobic", "alactic"], ["aerobic"]
    ) == ["aerobic", "glycolytic", "alactic"]


def _d22_athlete() -> dict:
    return {
        "sport": "boxing",
        "days_until_fight": 22,
        "fight_date": "2026-09-28",
        "plan_creation_weekday": "sunday",
        "fatigue": "moderate",
        "training_frequency": 4,
        "training_days": ["monday", "wednesday", "friday", "sunday"],
        "hard_sparring_days": [],
        "support_work_days": [],
        "technical_skill_days": [],
        "key_goals": ["conditioning", "speed"],
        "weaknesses": ["conditioning"],
        "weight_cut_risk": False,
        "cut_severity_bucket": "low",
        "injuries": [],
        "readiness_flags": [],
    }


def test_finished_d13_tail_carries_legal_parent_alactic_but_not_hard_glycolytic() -> None:
    tail = build_finished_late_fight_tail(
        22,
        _d22_athlete(),
        start_day=13,
        parent_required_conditioning_systems=["glycolytic", "alactic"],
    )
    roles = [role for role in tail.get("session_sequence", []) if isinstance(role, dict)]
    d13_to_d8 = [
        role for role in roles
        if 8 <= int(role.get("countdown_offset") or -1) <= 13
    ]
    keys = {str(role.get("role_key") or "") for role in d13_to_d8}
    assert "alactic_sharpness_day" in keys
    assert "fight_pace_repeatability_day" not in keys
    assert "controlled_repeatability_day" not in keys


def test_d14_d13_handoff_passes_real_parent_requirements(monkeypatch) -> None:
    week = {
        "week_index": 2,
        "phase": "SPP",
        "calendar_days": [
            {"weekday": "monday", "d_day": 14},
            {"weekday": "tuesday", "d_day": 13},
            {"weekday": "wednesday", "d_day": 12},
        ],
        "resolved_rule_state": {
            "must_keep": ["rehab", "glycolytic", "alactic", "primary_strength"]
        },
        "session_roles": [
            {"role_key": "neural_plus_strength_day", "category": "strength", "scheduled_day_hint": "monday"},
            {"role_key": "fight_pace_repeatability_day", "category": "conditioning", "preferred_system": "glycolytic", "scheduled_day_hint": "tuesday"},
        ],
        "intentionally_unused_days": [],
    }
    weekly = {"weeks": [week]}
    seen = {}

    def fake_tail(*_args, **kwargs):
        seen.update(kwargs)
        return {
            "session_sequence": [
                {"role_key": "alactic_sharpness_day", "category": "conditioning", "countdown_offset": 12, "scheduled_day_hint": "wednesday"}
            ],
            "segments": [],
            "day_metadata": {12: {}},
        }

    monkeypatch.setattr(camp_week_fillers, "build_finished_late_fight_tail", fake_tail)
    assert camp_week_fillers._splice_late_fight_tail(weekly, {"days_until_fight": 22}) is True
    assert seen["parent_required_conditioning_systems"] == ["glycolytic", "alactic"]
    contract = week["late_fight_tail_parent_requirements"]
    assert contract["required_conditioning_systems"] == ["glycolytic", "alactic"]
    keys = [role["role_key"] for role in week["session_roles"]]
    assert "neural_plus_strength_day" in keys  # D-14 normal ownership survives
    assert "fight_pace_repeatability_day" not in keys  # D-13 hard glycolytic does not leak through
    assert "alactic_sharpness_day" in keys  # legal late-fight expression replaces it


def test_finalizer_compaction_keeps_tail_handoff_contract() -> None:
    compact = _compact_weekly_role_map(
        {
            "weeks": [
                {
                    "week_index": 2,
                    "phase": "SPP",
                    "session_roles": [{"role_key": "alactic_sharpness_day", "category": "conditioning"}],
                    "late_fight_tail_days": [13, 12, 11],
                    "late_fight_tail_complete_week": False,
                    "late_fight_tail_parent_requirements": {
                        "required_conditioning_systems": ["glycolytic", "alactic"],
                        "primary_strength_required": True,
                    },
                }
            ]
        },
        {},
    )
    week = compact["weeks"][0]
    assert week["late_fight_tail_days"] == [13, 12, 11]
    assert week["late_fight_tail_parent_requirements"]["required_conditioning_systems"] == ["glycolytic", "alactic"]


def test_structural_authority_failures_hold_release() -> None:
    for code in (
        "missing_week_session_role",
        "late_camp_session_incomplete",
        "goal_preservation_failed",
    ):
        report = apply_stage2_release_policy(
            {
                "errors": [],
                "warnings": [{"code": code, "week_index": 2}],
                "review_flags": [],
                "blocking_warnings": [],
            }
        )
        assert report["release_decision"] == "hold"
        assert report["is_publishable"] is False
        assert report["is_athlete_releasable"] is False


def test_non_authority_warning_still_publishes_with_flags() -> None:
    report = apply_stage2_release_policy(
        {
            "errors": [],
            "warnings": [{"code": "gimmick_name"}],
            "review_flags": [],
            "blocking_warnings": [],
        }
    )
    assert report["release_decision"] == "publish_with_flags"
    assert report["is_publishable"] is True
''')
