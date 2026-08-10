import logging

from fightcamp.athlete_model import _build_athlete_model
from fightcamp.input_parsing import PlanInput
from fightcamp.plan_pipeline_runtime import build_runtime_context
from fightcamp.stage2_render_guards import (
    _append_render_guard_writing_rules,
    _render_guard_flags,
)
from fightcamp.tactical_watch_library import (
    build_watch_display_text,
    extract_tactical_style,
    select_tactical_watch,
    watch_metadata,
)


def _payload(fields: list[dict]) -> dict:
    return {"data": {"fields": fields}}


def _athlete_model_for(style: str, *, stance: str = "Orthodox") -> dict:
    plan_input = PlanInput.from_payload(
        _payload(
            [
                {"label": "Full name", "value": "Test Athlete"},
                {"label": "Fighting Style (Technical)", "value": "Boxing"},
                {"label": "Fighting Style (Tactical)", "value": style},
                {"label": "Stance", "value": stance},
                {"label": "Professional Status", "value": "Amateur"},
                {"label": "Current Record", "value": "3-1"},
                {"label": "Rounds x Minutes", "value": "3 x 3"},
                {"label": "Weekly Training Frequency", "value": "3"},
                {"label": "Training Availability", "value": "Monday, Wednesday, Friday"},
            ]
        )
    )
    runtime = build_runtime_context(
        plan_input=plan_input,
        random_seed=1,
        logger=logging.getLogger(__name__),
    )
    return _build_athlete_model(
        training_context=runtime.training_context,
        sport=runtime.mapped_format,
        record=plan_input.record,
        rounds_format=plan_input.rounds_format,
        camp_length_weeks=runtime.camp_len,
        short_notice=runtime.short_notice,
    )


def _identity_rules_for(athlete_model: dict) -> tuple[dict, str]:
    guidance = _append_render_guard_writing_rules(
        {"writing_rules": []},
        athlete_model=athlete_model,
        payload_mode="camp_payload",
        days_until_fight=30,
    )
    return guidance, "\n".join(guidance["writing_rules"])


def test_pressure_fighter_survives_normalization_and_hybrid_stance_in_athlete_view():
    athlete_model = _athlete_model_for("Pressure Fighter", stance="Hybrid")

    # This is the real runtime programming shape: intake normalization lowercases
    # the selection and the legacy stance bridge appends Hybrid.
    assert athlete_model["tactical_styles"] == ["pressure fighter", "hybrid"]

    guidance, rules = _identity_rules_for(athlete_model)
    assert guidance["render_guards"]["declared_tactical_styles"] == ["Pressure Fighter"]
    assert "Pressure Fighter" in rules
    assert "stance-derived programming signals" in rules
    assert "Pressure Fighter, Hybrid" not in rules


def test_pressure_fighter_uses_brawler_programming_without_brawler_visible_copy():
    athlete_model = _athlete_model_for("Pressure Fighter", stance="Hybrid")

    internal_style = extract_tactical_style(athlete_model)
    assert internal_style == "brawler"
    assert internal_style.display_label == "Pressure Fighter"

    watch = select_tactical_watch(internal_style, "SPP")
    metadata = watch_metadata(watch)
    display_text = build_watch_display_text(watch)

    # The parent family remains available to selection/scoring metadata.
    assert watch.style == "brawler"
    assert metadata["tactical_watch_style"] == "brawler"
    assert "brawler" in metadata["preferred_tags"]

    # Athlete-facing content uses the selected identity instead.
    assert metadata["tactical_watch_display_style"] == "Pressure Fighter"
    assert metadata["tactical_watch"]["mindset"]["context"] == "SPP pocket planning for a pressure fighter."
    assert "pressure fighter" in display_text.lower()
    assert "brawler" not in display_text.lower()


def test_brawler_legacy_selection_remains_brawler_in_athlete_view():
    athlete_model = _athlete_model_for("Brawler")
    guidance, rules = _identity_rules_for(athlete_model)

    assert guidance["render_guards"]["declared_tactical_styles"] == ["Brawler"]
    assert "Brawler" in rules

    internal_style = extract_tactical_style(athlete_model)
    assert internal_style == "brawler"
    assert internal_style.display_label == "Brawler"
    watch = select_tactical_watch(internal_style, "SPP")
    assert "for a brawler" in build_watch_display_text(watch).lower()


def test_hybrid_tactical_selection_is_not_removed_as_if_it_were_only_a_stance_signal():
    athlete_model = _athlete_model_for("Hybrid", stance="Hybrid")

    assert athlete_model["tactical_styles"] == ["hybrid"]
    guards = _render_guard_flags(
        athlete_model=athlete_model,
        payload_mode="camp_payload",
        days_until_fight=30,
    )
    assert guards["declared_tactical_styles"] == ["Hybrid"]


def test_no_declared_style_does_not_invent_identity_contract():
    guidance = _append_render_guard_writing_rules(
        {"writing_rules": []},
        athlete_model={"has_active_injury": False},
        payload_mode="camp_payload",
        days_until_fight=30,
    )

    assert guidance["render_guards"]["declared_tactical_styles"] == []
    assert not any("ATHLETE IDENTITY CONTRACT" in rule for rule in guidance["writing_rules"])
