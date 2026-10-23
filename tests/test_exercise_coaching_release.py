"""Release gate: model -> reconciliation -> conversion/fallback -> save -> React.

Run with backend dependencies and web/node_modules installed. Unlike a frozen
frontend fixture, every run builds and persists the release payload with the
current backend, then opens each real athlete-visible physical exercise row.
"""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from api.generation.stage2_runner import retry_structured_card_before_release
from api.services.effective_structured_plan import resolve_effective_structured_plan
from api.stage2_automation import OpenAIStage2Automator
from api.structured_plan_deterministic_fallback import build_deterministic_structured_plan
from api.structured_plan_generation import build_structured_plan_outcome
from fightcamp.exercise_coaching import exercise_coaching
from test_programme_fidelity_production import _persist_final, production_replay as _production_replay
from support import FakeOpenAIClient
from test_card_replay_representative_plans import replay as _representative_replay

production_replay = _production_replay
replay = _representative_replay

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("coaching_cues", "regression_options", "progression_rule", "stop_rules")
DOSE = ("sets", "reps", "rounds", "duration", "work", "rest", "distance", "effort", "load")
PHYSICAL = {"strength", "strength_speed", "plyometric_power", "speed", "accessory", "conditioning"}


def blocks(card):
    return [(w, b) for w in card["weeks"] for d in w["days"]
            for s in d.get("sessions", []) for b in s.get("blocks", [])
            if b.get("block_type") in PHYSICAL]


def canonical_cues(block):
    return [cue.removeprefix("Cue: ") for cue in block.get("coaching_cues", [])]


def response(text):
    return SimpleNamespace(id="offline", output_text=text,
                           usage=SimpleNamespace(input_tokens=1, output_tokens=1, total_tokens=2))


def ai_release_source(brief, text):
    """Explicit offline AI response fixture; production helpers author neither field."""
    from fightcamp.exercise_coaching_source import _EXERCISE, _LABEL
    from fightcamp.exercise_coaching_source import coaching_identity
    selected = {coaching_identity(a["name"]) for w in brief["weekly_role_map"]["weeks"]
                for r in w["session_roles"] for a in r.get("selected_exercise_assignments", [])
                if a.get("slot_group") in {"strength_slots", "conditioning_slots", "priority_microdose"}}
    lines = []
    for line in text.splitlines():
        label = _LABEL.match(line)
        if label and label[1].lower() in {"easier", "regression", "progress", "progression"}:
            continue
        lines.append(line)
        if (exercise := _EXERCISE.match(line)) and coaching_identity(exercise[1]) in selected:
            lines.extend([
                "  Easier: Use a smaller pain-free movement at the same dose.",
                "  Progress: At the same dose, refine movement control.",
            ])
    return "\n".join(lines)


@pytest.mark.parametrize("path", ["converted", "source_recovered", "not_attempted_fallback"])
@pytest.mark.skipif(not (ROOT / "web/node_modules/tsx").is_dir(),
                    reason="Release rendering requires npm ci in web; the coaching-release CI job installs it")
def test_final_persisted_physical_rows_keep_coaching_in_react(production_replay, monkeypatch, path):
    intake, stage1, reference_final, _ = production_replay
    brief = stage1["planning_brief"]
    source = ai_release_source(brief, reference_final["final_plan_text"])
    reference = build_deterministic_structured_plan(brief, plan_text=source)
    assert reference
    expected = blocks(reference)
    rules = [b["progression_rule"] for _, b in expected if b.get("progression_rule")]
    assert rules and all(rule == "At the same dose, refine movement control." for rule in rules)
    assert sum(bool(b.get("regression_options")) for _, b in expected) >= 20
    assert sum(bool(b.get("stop_rules")) for _, b in expected) >= 20
    candidate = deepcopy(reference)
    if path == "source_recovered":
        for _, block in blocks(candidate):
            for field in FIELDS:
                block.pop(field, None)
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "0" if path == "not_attempted_fallback" else "1")
    monkeypatch.delenv("UNLXCK_STAGE2_STRUCTURED_REPAIR", raising=False)
    raw = source
    client = FakeOpenAIClient([response(raw), response(json.dumps(candidate))])
    automator = OpenAIStage2Automator(client=client, model="offline")
    final = asyncio.run(automator.finalize(stage1_result=stage1))
    calls = len(client.responses.calls)
    if path == "converted":
        assert final.get("structured_plan"), final["stage2_validator_report"].get("structured_plan")
    if path == "source_recovered":
        report = final["stage2_validator_report"]["structured_plan"]
        assert report["status"] == "valid", report
        assert report["errors"] == []
        final = asyncio.run(retry_structured_card_before_release(
            stage2=automator, final_result=final, emit_milestone=lambda *a, **k: None))
        assert len(client.responses.calls) == calls == 2  # no repair/repeated conversion
    saved = _persist_final(intake, final)
    actual = resolve_effective_structured_plan(saved)
    assert actual
    actual_blocks = {b["block_id"]: b for _, b in blocks(actual)}
    for _, wanted in expected:
        found = actual_blocks[wanted["block_id"]]
        for field in (*FIELDS, *DOSE):
            if field == "coaching_cues":
                assert canonical_cues(found) == canonical_cues(wanted)
                continue
            if field in DOSE:
                from api.structured_plan_faithfulness import _prescription_value
                assert _prescription_value(found.get(field)) == _prescription_value(wanted.get(field)), (path, wanted["display_name"], field)
            else:
                assert found.get(field) == wanted.get(field), (path, wanted["display_name"], field)
    # Render the API payload AFTER persistence and the effective-plan resolver.
    result = subprocess.run(
        ["node", "--import", "tsx", "--import", "./test/register-css-stub.mjs",
         "test/assert-exercise-coaching-release.tsx"], cwd=ROOT / "web",
        input=json.dumps({"plan": actual, "expected": [
            {"id": b["block_id"], "fields": {
                k: canonical_cues(b) if k == "coaching_cues" else b[k] for k in FIELDS if k in b}}
        for _, b in expected]}), text=True, capture_output=True,
        env={**os.environ, "NODE_ENV": "test"},
    )
    assert result.returncode == 0, result.stderr
    coverage = json.loads(result.stdout.strip().splitlines()[-1])
    assert coverage["physicalCards"] == len(expected)
    print(path, coverage)


@pytest.mark.parametrize("field", FIELDS)
def test_a_converter_cannot_drop_any_applicable_coaching_field(production_replay, field):
    _, stage1, final, _ = production_replay
    brief = deepcopy(stage1["planning_brief"])
    source = ai_release_source(stage1["planning_brief"], final["final_plan_text"])
    candidate = build_deterministic_structured_plan(brief, plan_text=source)
    target = next(b for _, b in blocks(candidate) if b.get(field))
    expected = deepcopy(target[field])
    target.pop(field)
    outcome = build_structured_plan_outcome(candidate, raw_markdown=source,
                                           planning_brief=brief)
    # A dropped source coaching field is restored verbatim rather than costing the
    # athlete the whole converted card.
    assert outcome.structured_plan is not None, outcome.errors
    restored = next(b for _, b in blocks(outcome.structured_plan) if b.get("block_id") == target.get("block_id"))
    assert restored.get(field) == expected


@pytest.mark.parametrize("context", [
    {"phase": "TAPER"}, {"d_day": 7}, {"athlete": {"fatigue": "high"}},
    {"athlete": {"has_active_injury": True}}, {"athlete": {"weight_cut_risk": True}},
])
def test_maintenance_context_preserves_authored_easier_and_never_fabricates_it(context):
    a = {"name": "Barbell Thruster", "slot_group": "strength_slots", "source_phase": "SPP"}
    fields = exercise_coaching(a, {}, **context)
    assert fields["coaching_cues"] and fields["stop_rules"]
    assert not fields["regression_options"]  # Missing AI source is not fabricated.
    a["regression_options"] = ["Use a smaller pain-free movement at the same dose."]
    assert exercise_coaching(a, {}, **context)["regression_options"] == a["regression_options"]
    assert not fields.get("progression_rule")
    assert "effective_prescription" not in fields


def test_unknown_and_rehab_exercises_get_no_invented_progression():
    for a in ({"name": "Unknown Lift", "slot_group": "strength_slots"},
              {"name": "Knee Squat Rehab", "slot_group": "rehab_slots"}):
        assert not exercise_coaching(a, {}).get("progression_rule")


def test_existing_saved_card_recovers_missing_guidance_without_rewriting_doses(production_replay):
    _, stage1, final, _ = production_replay
    source = ai_release_source(stage1["planning_brief"], final["final_plan_text"])
    card = build_deterministic_structured_plan(stage1["planning_brief"], plan_text=source)
    original = deepcopy(card)
    for _, block in blocks(card):
        for field in ("regression_options", "progression_rule", "stop_rules"):
            block.pop(field, None)
    stored = deepcopy(card)
    recovered = resolve_effective_structured_plan({"planning_brief": stage1["planning_brief"],
                                                 "structured_plan": card, "plan_text": source})
    assert card == stored  # read-only recovery
    for (_, before), (_, after) in zip(blocks(original), blocks(recovered)):
        assert all(before.get(k) == after.get(k) for k in DOSE)
        assert before.get("regression_options") == after.get("regression_options")
        assert before.get("progression_rule") == after.get("progression_rule")
        # This read has no source text. Recover available authored/profile
        # guidance; an unknown movement must not gain a fabricated stop rule.
        if before.get("stop_rules"):
            assert after.get("stop_rules")
        else:
            assert not after.get("stop_rules")


def test_custom_plans_are_not_given_generated_coaching():
    from api.structured_plan_coaching import recover_selected_coaching
    plan = {"weeks": []}
    assert recover_selected_coaching(plan, {"custom_plan": True}) is plan


def test_representative_fallback_retains_execution_safety_at_fixed_doses(replay):
    name, brief, card = replay
    physical = blocks(card)
    # Direct countdown cards now retain their final selected primer too.
    # Validate its coaching and taper safety rather than skipping fight week.
    assert physical, name
    for week, block in physical:
        if block.get("regression_options"):
            assert block.get("coaching_cues") and block.get("stop_rules"), (name, block["display_name"])
        if week["phase_label"] == "TAPER" or brief["athlete_snapshot"].get("fatigue") == "high":
            from fightcamp.exercise_progression import progress_rejection
            assert not block.get("progression_rule") or progress_rejection(block["progression_rule"], None) is None
        for instruction in [*(block.get("regression_options") or []), block.get("progression_rule") or ""]:
            assert not any(word in instruction.lower() for word in ("add a set", "add reps", "shorten rest"))


