from fightcamp.tactical_watch_library import (
    build_watch_display_text,
    experience_overlay_instructions,
    extract_tactical_style,
    select_tactical_watch,
    watch_metadata,
)


def _watch_for_maturity(competitive_maturity: str):
    style = extract_tactical_style(
        {
            "tactical_styles": ["pressure fighter"],
            "competitive_maturity": competitive_maturity,
        }
    )
    return select_tactical_watch(style, "SPP")


def test_extract_tactical_style_carries_competitive_maturity_context():
    style = extract_tactical_style(
        {
            "tactical_styles": ["pressure fighter"],
            "competitive_maturity": "established_pro",
        }
    )

    assert style == "brawler"
    assert style.display_label == "Pressure Fighter"
    assert style.competitive_maturity == "established_pro"


def test_pro_overlay_does_not_change_the_selected_watch_identity():
    base_watch = _watch_for_maturity("")
    pro_watch = _watch_for_maturity("established_pro")

    assert pro_watch.key == base_watch.key
    assert pro_watch.name == base_watch.name
    assert pro_watch.style == base_watch.style
    assert pro_watch.phase == base_watch.phase


def test_novice_amateur_keeps_base_tactical_watch_depth():
    watch = _watch_for_maturity("novice_amateur")
    metadata = watch_metadata(watch)

    assert metadata["tactical_watch_experience_overlay"] is None
    assert metadata["tactical_watch_experience_overlay_steps"] == []
    assert metadata["tactical_watch"]["instructions"] == list(watch.instructions)
    assert "opponent danger cue" not in build_watch_display_text(watch)


def test_early_pro_gets_one_extra_danger_cue():
    watch = _watch_for_maturity("early_pro")
    metadata = watch_metadata(watch)

    assert metadata["tactical_watch_experience_overlay"] == "early_pro"
    assert metadata["tactical_watch_experience_overlay_steps"] == list(
        experience_overlay_instructions("early_pro")
    )
    assert len(metadata["tactical_watch"]["instructions"]) == len(watch.instructions) + 1
    assert any(
        "opponent danger cue" in instruction
        for instruction in metadata["tactical_watch"]["instructions"]
    )


def test_developing_pro_gets_danger_cue_and_round_phase():
    watch = _watch_for_maturity("developing_pro")
    instructions = watch_metadata(watch)["tactical_watch"]["instructions"]

    assert len(instructions) == len(watch.instructions) + 2
    assert any("opponent danger cue" in instruction for instruction in instructions)
    assert any("round phase" in instruction for instruction in instructions)


def test_established_pro_gets_full_advanced_cue_stack():
    watch = _watch_for_maturity("established_pro")
    metadata = watch_metadata(watch)
    instructions = metadata["tactical_watch"]["instructions"]

    assert metadata["tactical_watch_competitive_maturity"] == "established_pro"
    assert metadata["tactical_watch_experience_overlay"] == "established_pro"
    assert len(instructions) == len(watch.instructions) + 4
    assert any("opponent danger cue" in instruction for instruction in instructions)
    assert any("control window" in instruction for instruction in instructions)
    assert any("exit or reset" in instruction for instruction in instructions)
    assert any("do-not-chase rule" in instruction for instruction in instructions)
    assert metadata["governance"]["experience_overlay_locked"] is True


def test_established_pro_overlay_stays_inside_one_zero_load_watch_card():
    watch = _watch_for_maturity("established_pro")
    text = build_watch_display_text(watch)
    lines = text.splitlines()

    assert lines[0].startswith("Why: ")
    assert lines[1].startswith(f"- {watch.name}: ")
    assert "tactical review only. No physical load." in lines[1]
    assert [line for line in lines if line.startswith("- ")] == [lines[1]]
    assert all(line.startswith("  ") for line in lines[2:])
    assert any("opponent danger cue" in line for line in lines)
    assert any("do-not-chase rule" in line for line in lines)
