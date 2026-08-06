from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GAP_FILE = ROOT / "fightcamp" / "gap_fill_inserts.py"
CAMP_FILE = ROOT / "fightcamp" / "camp_week_fillers.py"
TEST_FILE = ROOT / "tests" / "test_mandatory_weekly_tactical_watch.py"


def replace_between(
    text: str,
    start_marker: str,
    end_marker: str,
    replacement: str,
    *,
    label: str,
) -> str:
    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError(f"Could not find start marker for {label}: {start_marker!r}")
    end = text.find(end_marker, start)
    if end < 0:
        raise RuntimeError(f"Could not find end marker for {label}: {end_marker!r}")
    return text[:start] + replacement.rstrip() + "\n\n" + text[end + 2 :]


def patch_gap_fill_inserts() -> None:
    text = GAP_FILE.read_text()

    progression_block = r'''_TACTICAL_WATCH_PHASE_VARIANTS: dict[str, tuple[dict[str, object], ...]] = {
    "GPP": (
        {
            "key": "style_baseline",
            "label": "GPP Tactical Watch: Style Baseline",
            "source": (
                "your own recent footage or a fighter with a comparable style"
            ),
            "questions": (
                "What rhythm do I naturally settle into?",
                "Which action creates my cleanest entry?",
                "Where does my shape break after I attack?",
                "What reset returns me to stance fastest?",
            ),
        },
        {
            "key": "entry_exit_audit",
            "label": "GPP Tactical Watch: Entry and Exit Audit",
            "source": (
                "your own recent footage or a fighter with a comparable style"
            ),
            "questions": (
                "What starts the cleanest entries?",
                "Which distance or angle makes the entry safest?",
                "Which exit is repeated after the combination?",
                "What cue keeps balance when the exchange breaks down?",
            ),
        },
        {
            "key": "reset_habits",
            "label": "GPP Tactical Watch: Reset Habits",
            "source": (
                "your own recent footage or a fighter with a comparable style"
            ),
            "questions": (
                "What happens immediately after a missed attack?",
                "Where do the guard and feet separate under pressure?",
                "Which reaction causes rushing, freezing, or square feet?",
                "What single reset action fixes the pattern?",
            ),
        },
    ),
    "SPP": (
        {
            "key": "rhythm_triggers",
            "label": "SPP Tactical Watch: Rhythm Triggers",
            "source": "the confirmed opponent or the closest available style match",
            "questions": (
                "What rhythm does the opponent prefer?",
                "What visible trigger starts their attack?",
                "Where is the cleanest entry against that rhythm?",
                "What reset denies their second attack?",
            ),
        },
        {
            "key": "first_exchange",
            "label": "SPP Tactical Watch: First Exchange",
            "source": "the confirmed opponent or the closest available style match",
            "questions": (
                "What is their first move after the bell or a restart?",
                "What do they test first: range, guard, lead hand, or position?",
                "What is the safest first scoring entry?",
                "What is the main danger in the opening exchange?",
            ),
        },
        {
            "key": "entry_route",
            "label": "SPP Tactical Watch: Entry Route",
            "source": "the confirmed opponent or the closest available style match",
            "questions": (
                "Which line or angle gets past their first defence?",
                "What reaction opens that route?",
                "Which counter is most likely to meet the entry?",
                "How do I exit and reset after using it?",
            ),
        },
        {
            "key": "danger_reset",
            "label": "SPP Tactical Watch: Danger and Reset",
            "source": "the confirmed opponent or the closest available style match",
            "questions": (
                "Where is the opponent most dangerous?",
                "What mistake gives them that position or exchange?",
                "What is the earliest warning cue?",
                "What exact reset response removes the danger?",
            ),
        },
    ),
    "TAPER": (
        {
            "key": "round_one_confirmation",
            "label": "TAPER Tactical Watch: Round 1 Confirmation",
            "source": "familiar opponent footage and already-confirmed camp clips",
            "questions": (
                "Confirm the first safe action already trained in camp.",
                "Confirm the range or position to own in Round 1.",
                "Confirm the danger cue that cannot be ignored.",
                "Confirm the reset phrase to use under pressure.",
            ),
        },
        {
            "key": "danger_reset_confirmation",
            "label": "TAPER Tactical Watch: Danger and Reset Confirmation",
            "source": "familiar opponent footage and already-confirmed camp clips",
            "questions": (
                "Confirm one familiar entry that has worked in training.",
                "Confirm one familiar danger to avoid.",
                "Confirm one rehearsed reset response.",
                "Confirm one Round 1 instruction. Add no new theory.",
            ),
        },
    ),
}

_TACTICAL_WATCH_PROGRESSION = {
    "GPP": "early_camp_foundation",
    "SPP": "opponent_specific",
    "TAPER": "fight_week_confirmation",
}


def _normalise_tactical_watch_phase(
    phase: str | None,
    variation_seed: int | None = None,
) -> str:
    value = str(phase or "").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "FIGHT_WEEK": "TAPER",
        "FIGHTWEEK": "TAPER",
        "TAPER_WEEK": "TAPER",
        "EARLY_CAMP": "GPP",
        "SPECIFIC_PREPARATION": "SPP",
    }
    value = aliases.get(value, value)
    if value in _TACTICAL_WATCH_PHASE_VARIANTS:
        return value
    if variation_seed is not None:
        try:
            return "TAPER" if int(variation_seed) <= 7 else "SPP"
        except (TypeError, ValueError):
            pass
    return "SPP"


def _tactical_watch_style_focus(athlete_model: dict[str, Any]) -> str:
    style_values = (
        _normalised_set(athlete_model.get("tactical_styles", []))
        | _normalised_set(athlete_model.get("style_tactical", []))
        | _normalised_set(athlete_model.get("technical_styles", []))
        | _normalised_set(athlete_model.get("style_technical", []))
        | _normalised_set(athlete_model.get("style", []))
        | _normalised_set(athlete_model.get("sport", []))
    )
    style_text = " ".join(style_values)
    if "counter" in style_text:
        return "Focus: bait reactions, exits, and the first counter after a feint."
    if "pressure" in style_text:
        return "Focus: entries, clinch risk, and angle exits."
    if "boxer" in style_text or "boxing" in style_text:
        return "Focus: jab rhythm, lead-hand battle, and exit side."
    if (
        "kicker" in style_text
        or "kickboxing" in style_text
        or "muay" in style_text
    ):
        return "Focus: range line, stance matchups, and check-counter timing."
    if (
        "grappler" in style_text
        or "mma" in style_text
        or "wrestling" in style_text
    ):
        return "Focus: level-change triggers, cage exits, and underhook habits."
    return ""


def build_tactical_watch_progression(
    athlete_model: dict[str, Any] | None = None,
    *,
    phase: str | None = None,
    variation_seed: int | None = None,
) -> dict[str, str]:
    athlete_model = athlete_model or {}
    phase_key = _normalise_tactical_watch_phase(phase, variation_seed)
    variants = _TACTICAL_WATCH_PHASE_VARIANTS[phase_key]
    try:
        seed = max(0, int(variation_seed or 0))
    except (TypeError, ValueError):
        seed = 0
    variant = variants[(seed // 7) % len(variants)]
    questions = tuple(str(question) for question in variant["questions"])
    question_lines = "\n".join(
        f"{index}. {question}" for index, question in enumerate(questions, start=1)
    )
    lines = [
        f"{variant['label']} - 8-12 min",
        "",
        f"Footage source: {variant['source']}.",
        "Watch 1-2 rounds or 10-20 clips.",
    ]
    style_focus = _tactical_watch_style_focus(athlete_model)
    if style_focus:
        lines.append(style_focus)
    lines.extend(
        [
            "",
            "Study this week:",
            question_lines,
            "",
            "Output (write exactly these 4 lines):",
            "Entry cue: 1 way I get in.",
            "Danger cue: 1 thing that gets me hurt.",
            "Reset cue: 1 phrase to recover when it goes bad.",
            "Round 1: 1 instruction I follow from the first bell.",
        ]
    )
    if phase_key == "TAPER":
        lines.insert(4, "Use confirmed cues only. Add no new tactical theory.")
    return {
        "phase": phase_key,
        "variant": str(variant["key"]),
        "label": str(variant["label"]),
        "progression": _TACTICAL_WATCH_PROGRESSION[phase_key],
        "display_text": "\n".join(lines),
    }


def build_tactical_watch_template(
    athlete_model: dict[str, Any] | None = None,
    *,
    phase: str | None = None,
    variation_seed: int | None = None,
) -> str:
    return build_tactical_watch_progression(
        athlete_model,
        phase=phase,
        variation_seed=variation_seed,
    )["display_text"]'''

    text = replace_between(
        text,
        "def build_tactical_watch_template(",
        "\n\ndef _first_allowed",
        progression_block,
        label="Tactical Watch progression builder",
    )

    build_role_block = r'''def _build_insert_role(
    role_key: str,
    athlete_model: dict[str, Any],
    insert_offset: int,
    weekday: str | None = None,
    tactical_watch_phase: str | None = None,
) -> dict[str, Any]:
    meta = _INSERT_META[role_key]
    watch_profile = None
    if role_key == "tactical_watch":
        watch_profile = build_tactical_watch_progression(
            athlete_model,
            phase=tactical_watch_phase,
            variation_seed=insert_offset,
        )
        label = watch_profile["label"]
        display_text = watch_profile["display_text"]
    else:
        label = str(meta["label"])
        display_text = str(meta["display_text"])

    role: dict[str, Any] = {
        "session_index": None,
        "category": "support_insert",
        "role_key": role_key,
        "scheduled_day_hint": weekday,
        "athlete_facing_label": label,
        "display_text": display_text,
        "duration_min": list(meta["duration_min"]),
        "rpe_max": int(meta["rpe_max"]),
        "support_insert_category": _insert_category(role_key),
        "support_insert_cost_category": _cost_category(role_key),
        "mechanical_load_regions": list(insert_mechanical_load_regions(role_key)),
        "countdown_offset": insert_offset,
        "countdown_label": f"D-{insert_offset}",
        "scheduled_countdown_label": f"D-{insert_offset}",
        "stress_class": "support",
        "cost_class": "low",
        "governance": {
            "authority": "gap_fill_support_insert",
            "meaningful_stress": False,
        },
    }
    if watch_profile is not None:
        role["tactical_watch_phase"] = watch_profile["phase"]
        role["tactical_watch_variant"] = watch_profile["variant"]
        role["tactical_watch_progression"] = watch_profile["progression"]
    if weekday:
        role["real_weekday"] = weekday
        role["countdown_display_label"] = (
            f"D-{insert_offset} ({weekday.title()})"
        )
    return role'''

    text = replace_between(
        text,
        "def _build_insert_role(",
        "\n\ndef select_gap_fill_insert",
        build_role_block,
        label="support insert role builder",
    )

    mandatory_block = r'''def _late_fight_watch_phase(offset: int) -> str:
    return "TAPER" if offset <= 7 else "SPP"


def _build_mandatory_tactical_watch(
    athlete_model: dict[str, Any],
    offset: int,
    weekday: str | None,
) -> dict[str, Any]:
    phase = _late_fight_watch_phase(offset)
    watch = _build_insert_role(
        "tactical_watch",
        athlete_model,
        offset,
        weekday,
        tactical_watch_phase=phase,
    )
    watch["camp_phase"] = phase
    watch["mandatory_tactical_watch"] = True
    watch["weekly_requirement"] = "fight_tactical_watch"
    watch["tactical_watch_segment"] = _segment_for_offset(offset)
    watch["governance"] = {
        **dict(watch.get("governance") or {}),
        "authority": "gap_fill_support_insert",
        "mandatory": True,
        "meaningful_stress": False,
    }
    return watch'''

    text = replace_between(
        text,
        "def _mandatory_watch_guidance(",
        "\n\ndef _promote_mandatory_tactical_watch",
        mandatory_block,
        label="late-fight Tactical Watch builder",
    )

    GAP_FILE.write_text(text)


def patch_camp_week_fillers() -> None:
    text = CAMP_FILE.read_text()
    import_line = "    build_tactical_watch_template,\n"
    if import_line not in text:
        raise RuntimeError("Expected Tactical Watch template import was not found")
    text = text.replace(import_line, "", 1)

    text = replace_between(
        text,
        "def _phase_watch_guidance(",
        "\n\ndef _decorate_insert",
        "",
        label="legacy phase guidance",
    )

    place_block = r'''def _place_tactical_watch(
    week: dict[str, Any],
    session_roles: list[dict[str, Any]],
    athlete_model: dict[str, Any],
    day: str,
    *,
    phase: str,
    usage_ledger: dict[str, Any],
) -> dict[str, Any] | None:
    d_day = _calendar_d_day(week, day)
    if d_day is None or d_day <= 0:
        return None

    insert = _build_insert_role(
        _TACTICAL_WATCH_ROLE_KEY,
        athlete_model,
        d_day,
        weekday=str(day).strip().title(),
        tactical_watch_phase=phase,
    )
    insert["camp_phase"] = phase
    _decorate_insert(
        insert,
        day=day,
        d_day=d_day,
        mandatory_tactical_watch=True,
    )
    session_roles.append(insert)
    _record_insert_usage(usage_ledger, _TACTICAL_WATCH_ROLE_KEY, d_day)
    return insert'''

    text = replace_between(
        text,
        "def _place_tactical_watch(",
        "\n\ndef _promote_existing_tactical_watch",
        place_block,
        label="normal-camp Tactical Watch placement",
    )

    promote_block = r'''def _promote_existing_tactical_watch(
    week: dict[str, Any],
    role: dict[str, Any],
    athlete_model: dict[str, Any],
    *,
    phase: str,
    usage_ledger: dict[str, Any],
) -> bool:
    day = str(role.get("scheduled_day_hint") or role.get("real_weekday") or "").strip()
    d_day = _calendar_d_day(week, day)
    if not day or d_day is None or d_day <= 0:
        return False

    template = _build_insert_role(
        _TACTICAL_WATCH_ROLE_KEY,
        athlete_model,
        d_day,
        weekday=day.title(),
        tactical_watch_phase=phase,
    )
    for key, value in template.items():
        role[key] = value
    role["camp_phase"] = phase
    _decorate_insert(
        role,
        day=day,
        d_day=d_day,
        mandatory_tactical_watch=True,
    )
    _record_insert_usage(usage_ledger, _TACTICAL_WATCH_ROLE_KEY, d_day)
    return True'''

    text = replace_between(
        text,
        "def _promote_existing_tactical_watch(",
        "\n\ndef _eligible_unused_entries",
        promote_block,
        label="existing normal-camp Tactical Watch promotion",
    )

    CAMP_FILE.write_text(text)


def patch_tests() -> None:
    text = TEST_FILE.read_text()
    old_import = "from fightcamp.gap_fill_inserts import apply_gap_fill_inserts\n"
    new_import = (
        "from fightcamp.gap_fill_inserts import (\n"
        "    apply_gap_fill_inserts,\n"
        "    build_tactical_watch_template,\n"
        ")\n"
    )
    if old_import not in text and "build_tactical_watch_template" not in text:
        raise RuntimeError("Expected gap-fill import was not found in Tactical Watch tests")
    if old_import in text:
        text = text.replace(old_import, new_import, 1)

    sentinel = "def test_tactical_watch_content_progresses_by_phase_and_week():"
    if sentinel not in text:
        text += r'''


def _assert_four_line_output(display_text: str) -> None:
    assert display_text.count("Entry cue:") == 1
    assert display_text.count("Danger cue:") == 1
    assert display_text.count("Reset cue:") == 1
    assert display_text.count("Round 1:") == 1


def test_tactical_watch_content_progresses_by_phase_and_week():
    role_map = {
        "weeks": [
            _week("GPP", 49),
            _week("GPP", 42),
            _week("SPP", 28),
            _week("SPP", 21),
            _week("TAPER", 7),
        ]
    }
    apply_camp_week_fillers(role_map, _athlete(days_until_fight=49))

    watches = [_watches(week["session_roles"])[0] for week in role_map["weeks"]]
    assert [watch["tactical_watch_phase"] for watch in watches] == [
        "GPP",
        "GPP",
        "SPP",
        "SPP",
        "TAPER",
    ]
    assert watches[0]["tactical_watch_variant"] != watches[1]["tactical_watch_variant"]
    assert watches[2]["tactical_watch_variant"] != watches[3]["tactical_watch_variant"]
    assert len({watch["display_text"] for watch in watches}) == len(watches)
    assert watches[0]["athlete_facing_label"].startswith("GPP Tactical Watch:")
    assert watches[2]["athlete_facing_label"].startswith("SPP Tactical Watch:")
    assert watches[4]["athlete_facing_label"].startswith("TAPER Tactical Watch:")
    assert "own recent footage" in watches[0]["display_text"].lower()
    assert "confirmed opponent" in watches[2]["display_text"].lower()
    assert "add no new tactical theory" in watches[4]["display_text"].lower()
    for watch in watches:
        _assert_four_line_output(watch["display_text"])


def test_direct_tactical_watch_template_keeps_output_contract_across_phases():
    templates = [
        build_tactical_watch_template(_athlete(), phase="GPP", variation_seed=42),
        build_tactical_watch_template(_athlete(), phase="SPP", variation_seed=21),
        build_tactical_watch_template(_athlete(), phase="TAPER", variation_seed=7),
    ]
    assert len(set(templates)) == 3
    for template in templates:
        _assert_four_line_output(template)


def test_late_fight_watch_progression_uses_spp_then_taper():
    sequence = apply_gap_fill_inserts(
        [_session(21), _session(16), _session(11), _session(6)],
        _athlete(days_until_fight=21),
    )
    watches_by_segment = {
        watch["tactical_watch_segment"]: watch for watch in _watches(sequence)
    }
    assert watches_by_segment[0]["tactical_watch_phase"] == "TAPER"
    assert watches_by_segment[1]["tactical_watch_phase"] == "SPP"
    assert watches_by_segment[2]["tactical_watch_phase"] == "SPP"
    assert (
        watches_by_segment[1]["tactical_watch_variant"]
        != watches_by_segment[2]["tactical_watch_variant"]
    )
    assert "add no new tactical theory" in (
        watches_by_segment[0]["display_text"].lower()
    )
    assert "confirmed opponent" in watches_by_segment[1]["display_text"].lower()
'''

    TEST_FILE.write_text(text)


def main() -> None:
    patch_gap_fill_inserts()
    patch_camp_week_fillers()
    patch_tests()


if __name__ == "__main__":
    main()
