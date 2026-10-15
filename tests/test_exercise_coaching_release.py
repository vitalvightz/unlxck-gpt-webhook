"""Release gate: model -> reconciliation -> conversion/fallback -> save -> React.

Run with backend dependencies and web/node_modules installed. Unlike a frozen
frontend fixture, every run builds and persists the release payload with the
current backend, then opens each real athlete-visible physical exercise row.
"""
import asyncio
from copy import deepcopy
import json
import os
import re
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
from fightcamp.exercise_progression import build_progression_context
from fightcamp.programme_fidelity import reconcile_authoritative_programme
from test_programme_fidelity_production import FIXTURES, _persist_final, production_replay as _production_replay
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


@pytest.mark.parametrize("path", ["converted", "rejected_fast_fallback", "not_attempted_fallback"])
@pytest.mark.skipif(not (ROOT / "web/node_modules/tsx").is_dir(),
                    reason="Release rendering requires npm ci in web; the coaching-release CI job installs it")
def test_final_persisted_physical_rows_keep_coaching_in_react(production_replay, monkeypatch, path):
    intake, stage1, reference_final, _ = production_replay
    brief = stage1["planning_brief"]
    source = reference_final["final_plan_text"]
    reference = build_deterministic_structured_plan(brief, plan_text=source)
    assert reference
    expected = blocks(reference)
    # The affected programme repeats fixed doses. Quality text is not Progress.
    assert not any(b.get("progression_rule") for _, b in expected)
    assert sum(bool(b.get("regression_options")) for _, b in expected) >= 20
    assert sum(bool(b.get("stop_rules")) for _, b in expected) >= 20
    for week, block in expected:
        if week["phase_label"] == "TAPER":
            assert not block.get("progression_rule"), block["display_name"]
    candidate = deepcopy(reference)
    if path == "rejected_fast_fallback":
        for _, block in blocks(candidate):
            for field in FIELDS:
                block.pop(field, None)
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "0" if path == "not_attempted_fallback" else "1")
    monkeypatch.delenv("UNLXCK_STAGE2_STRUCTURED_REPAIR", raising=False)
    raw = (FIXTURES / "production_render.txt").read_text(encoding="utf8")
    client = FakeOpenAIClient([response(raw), response(json.dumps(candidate))])
    automator = OpenAIStage2Automator(client=client, model="offline")
    final = asyncio.run(automator.finalize(stage1_result=stage1))
    calls = len(client.responses.calls)
    if path == "converted":
        assert final.get("structured_plan"), final["stage2_validator_report"].get("structured_plan")
    if path == "rejected_fast_fallback":
        report = final["stage2_validator_report"]["structured_plan"]
        assert report["status"] == "invalid_fallback_used", report
        assert any("COACHING_DROPPED" in e for e in report["errors"])
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
    source = final["final_plan_text"]
    if field == "progression_rule":
        # A controlled fixture with an explicitly authorised future rep increase.
        # Candidate/budget changes may move the appointment or select another
        # lift. Exercise the release contract using a real comparable pair,
        # without hard-coding the old programme's date or thruster selection.
        pair = next(c for c in build_progression_context(brief).values()
                    if c['next'] and c['current']['role'].get('category') == 'strength'
                    and not c['current']['blocked'] and not c['next']['blocked']
                    and c['current']['phase'] == c['next']['phase']
                    and c['current']['dose'] == c['next']['dose']
                    and c['next']['dose'].get('reps'))
        role = pair['next']['role']
        member = pair['next']['assignment']
        future = next(p for p in role['effective_strength_prescriptions']
                      if p['name'] == member['name'] and p.get('slot_id') == member.get('slot_id'))
        future['effective_prescription'] = re.sub(
            r'(\b\d+\s*x\s*)(\d+)', lambda m: m[1] + str(int(m[2]) + 1),
            future['effective_prescription'], count=1,
        )
        source = reconcile_authoritative_programme(brief, source)["text"]
    candidate = build_deterministic_structured_plan(brief, plan_text=source)
    target = next(b for _, b in blocks(candidate) if b.get(field))
    target.pop(field)
    outcome = build_structured_plan_outcome(candidate, raw_markdown=source,
                                           planning_brief=brief)
    assert outcome.structured_plan is None
    assert any("COACHING_DROPPED" in e and field in e for e in outcome.errors)


@pytest.mark.parametrize("context", [
    {"phase": "TAPER"}, {"d_day": 7}, {"athlete": {"fatigue": "high"}},
    {"athlete": {"has_active_injury": True}}, {"athlete": {"weight_cut_risk": True}},
])
def test_maintenance_contexts_have_easier_and_stop_without_progress(context):
    a = {"name": "Barbell Thruster", "slot_group": "strength_slots", "source_phase": "SPP"}
    fields = exercise_coaching(a, {}, **context)
    assert fields["coaching_cues"] and fields["regression_options"] and fields["stop_rules"]
    assert not fields.get("progression_rule")
    assert "effective_prescription" not in fields


def test_unknown_and_rehab_exercises_get_no_invented_progression():
    for a in ({"name": "Unknown Lift", "slot_group": "strength_slots"},
              {"name": "Knee Squat Rehab", "slot_group": "rehab_slots"}):
        assert not exercise_coaching(a, {}).get("progression_rule")


def test_existing_saved_card_recovers_missing_guidance_without_rewriting_doses(production_replay):
    _, stage1, final, _ = production_replay
    card = build_deterministic_structured_plan(stage1["planning_brief"], plan_text=final["final_plan_text"])
    original = deepcopy(card)
    for _, block in blocks(card):
        for field in ("regression_options", "progression_rule", "stop_rules"):
            block.pop(field, None)
    stored = deepcopy(card)
    recovered = resolve_effective_structured_plan({"planning_brief": stage1["planning_brief"],
                                                 "structured_plan": card})
    assert card == stored  # read-only recovery
    for (_, before), (_, after) in zip(blocks(original), blocks(recovered)):
        assert all(before.get(k) == after.get(k) for k in DOSE)
        assert before.get("regression_options") == after.get("regression_options")
        assert before.get("progression_rule") == after.get("progression_rule")
        # A selected exercise with no authored Stop must not gain an invented
        # trigger merely to fill the card. Restore only originally known rules.
        assert before.get("stop_rules") == after.get("stop_rules")


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
            assert not block.get("progression_rule"), (name, block["display_name"])
        for instruction in [*(block.get("regression_options") or []), block.get("progression_rule") or ""]:
            assert not any(word in instruction.lower() for word in ("add a set", "add reps", "shorten rest"))


