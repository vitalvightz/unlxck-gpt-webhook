from fightcamp.injury_awareness import (
    build_injury_awareness_support,
    merge_injury_awareness,
)
from fightcamp.stage2_payload import build_computed_support


def _entry(location="shoulder", side="left", injury_type="strain", impact="not_limiting"):
    entry = {"canonical_location": location, "side": side, "injury_type": injury_type}
    if impact:
        entry["training_impact"] = impact
    return entry


def test_only_not_limiting_entries_produce_awareness():
    assert build_injury_awareness_support([_entry(impact=None)]) is None
    support = build_injury_awareness_support([_entry(), _entry(location="knee", impact=None)])
    assert [r["area"] for r in support["injuries"]] == ["left shoulder"]
    assert support["plan_note"]["category"] == "injury"
    assert "not limiting" in support["plan_note"]["text"]
    assert "Left shoulder strain" in support["plan_note"]["text"]
    (rule,) = support["red_flag_rules"]
    assert rule["severity"] == "amber"
    assert "left shoulder" in rule["display_text"]
    assert "stop" in rule["display_text"]


def test_merge_adds_note_and_rule_without_touching_existing():
    support = build_injury_awareness_support([_entry()])
    plan = {
        "plan_notes": [{"category": "weight_cut", "text": "Small routine cut."}],
        "red_flag_rules": [{"rule_id": "pain", "display_text": "If pain above 4/10, stop."}],
    }
    merged = merge_injury_awareness(plan, support)
    assert [n["category"] for n in merged["plan_notes"]] == ["weight_cut", "injury"]
    assert len(merged["red_flag_rules"]) == 2
    # idempotent
    again = merge_injury_awareness(merged, support)
    assert again["plan_notes"] == merged["plan_notes"]
    assert again["red_flag_rules"] == merged["red_flag_rules"]


def test_merge_skips_when_plan_already_covers_area():
    support = build_injury_awareness_support([_entry()])
    plan = {
        "plan_notes": [{"category": "injury", "text": "Left shoulder: keep it warm."}],
        "red_flag_rules": [{"display_text": "Stop if your left shoulder gives sharp pain."}],
    }
    merged = merge_injury_awareness(plan, support)
    assert len(merged["plan_notes"]) == 1
    assert len(merged["red_flag_rules"]) == 1


def test_merge_noop_without_awareness():
    plan = {"plan_notes": [], "red_flag_rules": []}
    assert merge_injury_awareness(plan, None) is plan


def test_computed_support_carries_awareness_only_when_present():
    base = {"phase": "GPP", "fatigue": "low", "weight": 70.0, "age": 25}
    without = build_computed_support(flags=base, phases=["GPP"])
    assert "injury_awareness" not in without
    with_aw = build_computed_support(
        flags={**base, "non_limiting_injuries": [_entry()]}, phases=["GPP"]
    )
    assert with_aw["injury_awareness"]["injuries"][0]["area"] == "left shoulder"


def _awareness_support():
    return build_computed_support(
        flags={
            "phase": "GPP",
            "fatigue": "low",
            "weight": 70.0,
            "non_limiting_injuries": [_entry()],
        },
        phases=["GPP"],
    )


def test_published_card_carries_injury_note_and_reinjury_rule():
    from api.structured_plan_generation import build_structured_plan_outcome
    from test_structured_plan_models import _valid_plan
    from test_structured_plan_safety import _faithful_source

    plan = _valid_plan()
    outcome = build_structured_plan_outcome(
        plan, raw_markdown=_faithful_source(plan), computed_support=_awareness_support()
    )

    card = outcome.structured_plan
    assert card is not None
    assert any(
        note["category"] == "injury" and "not limiting" in note["text"]
        for note in card["plan_notes"]
    )
    assert any(
        str(rule.get("rule_id", "")).startswith("non_limiting_injury_reinjury")
        for rule in card["red_flag_rules"]
    )


def test_conversion_prompt_never_sees_non_limiting_injuries():
    from api.structured_plan_generation import build_structured_plan_prompt

    prompt = build_structured_plan_prompt(
        plan_markdown="PLAN",
        planning_brief={"computed_support": _awareness_support()},
    )
    assert "injury_awareness" not in prompt
    assert "left shoulder" not in prompt.lower()


def test_side_is_not_doubled_when_area_already_names_it():
    from fightcamp.injury_awareness import awareness_plan_note, build_injury_awareness

    records = build_injury_awareness(
        [{"guided_area": "Left bicep", "side": "left", "injury_type": "cut", "training_impact": "not_limiting"}]
    )
    assert records == [{"area": "left bicep", "injury_type": "cut"}]
    assert awareness_plan_note(records)["text"].startswith("Left bicep cut is logged")


def test_bilateral_injury_note_uses_plural_grammar():
    from fightcamp.injury_awareness import awareness_plan_note, build_injury_awareness

    records = build_injury_awareness(
        [{"guided_area": "knee", "side": "bilateral", "injury_type": "", "training_impact": "not_limiting"}]
    )
    text = awareness_plan_note(records)["text"]
    assert text.startswith("Both knees are logged as not limiting, so they do not change")
    assert "Warm them up properly, keep an eye on them," in text
