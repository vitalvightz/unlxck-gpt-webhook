from __future__ import annotations

from typing import Any

_PHASE_VARIANTS: dict[str, tuple[dict[str, object], ...]] = {
    "GPP": (
        {
            "key": "style_baseline",
            "label": "GPP Tactical Watch: Style Baseline",
            "source": "your own recent footage or a fighter with a comparable style",
            "questions": (
                "What rhythm do I naturally settle into?",
                "Which action creates my cleanest entry?",
                "Where does my shape break after I attack?",
                "What reset returns me to stance fastest?",
            ),
        },
        {
            "key": "rhythm_control",
            "label": "GPP Tactical Watch: Rhythm Control",
            "source": "your own recent footage or a fighter with a comparable style",
            "questions": (
                "When do I control the pace instead of following it?",
                "What changes my rhythm without costing balance?",
                "Which repeated tempo makes me predictable?",
                "What cue brings me back to a calm pace?",
            ),
        },
        {
            "key": "entry_creation",
            "label": "GPP Tactical Watch: Entry Creation",
            "source": "your own recent footage or a fighter with a comparable style",
            "questions": (
                "What starts the cleanest entries?",
                "Which feint, touch, or movement earns the reaction?",
                "Which distance or angle makes the entry safest?",
                "What cue stops me forcing the entry?",
            ),
        },
        {
            "key": "exit_discipline",
            "label": "GPP Tactical Watch: Exit Discipline",
            "source": "your own recent footage or a fighter with a comparable style",
            "questions": (
                "Which exit is repeated after the combination?",
                "When do I stay in range one beat too long?",
                "Which side or position gives the safest reset?",
                "What cue keeps my stance intact on the exit?",
            ),
        },
        {
            "key": "defensive_reactions",
            "label": "GPP Tactical Watch: Defensive Reactions",
            "source": "your own recent footage or a fighter with a comparable style",
            "questions": (
                "What is my first reaction when pressure arrives?",
                "Which defensive habit creates the next opening?",
                "Where do my guard, posture, or feet separate?",
                "What simple response restores position?",
            ),
        },
        {
            "key": "reset_habits",
            "label": "GPP Tactical Watch: Reset Habits",
            "source": "your own recent footage or a fighter with a comparable style",
            "questions": (
                "What happens immediately after a missed attack?",
                "Which reaction causes rushing, freezing, or square feet?",
                "What body position tells me the exchange is lost?",
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
            "key": "main_danger",
            "label": "SPP Tactical Watch: Main Danger",
            "source": "the confirmed opponent or the closest available style match",
            "questions": (
                "Where is the opponent most dangerous?",
                "What mistake gives them that position or exchange?",
                "What is the earliest warning cue?",
                "What action removes me before the danger develops?",
            ),
        },
        {
            "key": "reset_response",
            "label": "SPP Tactical Watch: Reset Response",
            "source": "the confirmed opponent or the closest available style match",
            "questions": (
                "What does the opponent do after their first attack is stopped?",
                "Where do they expect the exchange to continue?",
                "What response breaks their follow-up pattern?",
                "What exact reset returns me to my preferred position?",
            ),
        },
        {
            "key": "round_one_sequence",
            "label": "SPP Tactical Watch: Round 1 Sequence",
            "source": "the confirmed opponent or the closest available style match",
            "questions": (
                "What information must I collect in the first minute?",
                "What first action tests the opponent safely?",
                "Which danger changes the plan immediately?",
                "What Round 1 sequence links entry, exit, and reset?",
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

_PROGRESSION_KEYS = {
    "GPP": "early_camp_foundation",
    "SPP": "opponent_specific",
    "TAPER": "fight_week_confirmation",
}


def _normalise_phase(phase: str | None, variation_seed: int | None = None) -> str:
    value = str(phase or "").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "EARLY_CAMP": "GPP",
        "FIGHT_WEEK": "TAPER",
        "FIGHTWEEK": "TAPER",
        "SPECIFIC_PREPARATION": "SPP",
        "TAPER_WEEK": "TAPER",
    }
    value = aliases.get(value, value)
    if value in _PHASE_VARIANTS:
        return value
    if variation_seed is not None:
        try:
            return "TAPER" if int(variation_seed) <= 7 else "SPP"
        except (TypeError, ValueError):
            pass
    return "SPP"


def _normalised_set(values: Any) -> set[str]:
    if values is None:
        return set()
    if isinstance(values, str):
        items = [values]
    elif isinstance(values, (list, tuple, set)):
        items = list(values)
    else:
        items = [values]
    return {
        str(value).strip().lower().replace(" ", "_")
        for value in items
        if str(value).strip()
    }


def _style_focus(athlete_model: dict[str, Any]) -> str:
    style_values = (
        _normalised_set(athlete_model.get("tactical_styles"))
        | _normalised_set(athlete_model.get("style_tactical"))
        | _normalised_set(athlete_model.get("technical_styles"))
        | _normalised_set(athlete_model.get("style_technical"))
        | _normalised_set(athlete_model.get("style"))
        | _normalised_set(athlete_model.get("sport"))
    )
    style_text = " ".join(style_values)
    if "counter" in style_text:
        return "Focus: bait reactions, exits, and the first counter after a feint."
    if "pressure" in style_text:
        return "Focus: entries, clinch risk, and angle exits."
    if "boxer" in style_text or "boxing" in style_text:
        return "Focus: jab rhythm, lead-hand battle, and exit side."
    if "kicker" in style_text or "kickboxing" in style_text or "muay" in style_text:
        return "Focus: range line, stance matchups, and check-counter timing."
    if "grappler" in style_text or "mma" in style_text or "wrestling" in style_text:
        return "Focus: level-change triggers, cage exits, and underhook habits."
    return ""


def build_tactical_watch_progression(
    athlete_model: dict[str, Any] | None = None,
    *,
    phase: str | None = None,
    variation_seed: int | None = None,
) -> dict[str, str]:
    athlete_model = athlete_model or {}
    phase_key = _normalise_phase(phase, variation_seed)
    variants = _PHASE_VARIANTS[phase_key]
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
    if phase_key == "TAPER":
        lines.append("Use confirmed cues only. Add no new tactical theory.")
    style_focus = _style_focus(athlete_model)
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
    return {
        "phase": phase_key,
        "variant": str(variant["key"]),
        "label": str(variant["label"]),
        "progression": _PROGRESSION_KEYS[phase_key],
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
    )["display_text"]


def install() -> None:
    from . import gap_fill_inserts as gap_module

    if getattr(gap_module, "_TACTICAL_WATCH_PROGRESSION_INSTALLED", False):
        return

    original_build_insert_role = gap_module._build_insert_role

    def build_insert_role(
        role_key: str,
        athlete_model: dict[str, Any],
        insert_offset: int,
        weekday: str | None = None,
        tactical_watch_phase: str | None = None,
    ) -> dict[str, Any]:
        role = original_build_insert_role(
            role_key,
            athlete_model,
            insert_offset,
            weekday,
        )
        if role_key != "tactical_watch":
            return role
        profile = build_tactical_watch_progression(
            athlete_model,
            phase=tactical_watch_phase,
            variation_seed=insert_offset,
        )
        role["athlete_facing_label"] = profile["label"]
        role["display_text"] = profile["display_text"]
        role["tactical_watch_phase"] = profile["phase"]
        role["tactical_watch_variant"] = profile["variant"]
        role["tactical_watch_progression"] = profile["progression"]
        return role

    def build_mandatory_tactical_watch(
        athlete_model: dict[str, Any],
        offset: int,
        weekday: str | None,
    ) -> dict[str, Any]:
        phase = "TAPER" if offset <= 7 else "SPP"
        watch = build_insert_role(
            "tactical_watch",
            athlete_model,
            offset,
            weekday,
            tactical_watch_phase=phase,
        )
        watch["camp_phase"] = phase
        watch["mandatory_tactical_watch"] = True
        watch["weekly_requirement"] = "fight_tactical_watch"
        watch["tactical_watch_segment"] = gap_module._segment_for_offset(offset)
        watch["governance"] = {
            **dict(watch.get("governance") or {}),
            "authority": "gap_fill_support_insert",
            "mandatory": True,
            "meaningful_stress": False,
        }
        return watch

    gap_module.build_tactical_watch_progression = build_tactical_watch_progression
    gap_module.build_tactical_watch_template = build_tactical_watch_template
    gap_module._build_insert_role = build_insert_role
    gap_module._build_mandatory_tactical_watch = build_mandatory_tactical_watch
    gap_module._TACTICAL_WATCH_PROGRESSION_INSTALLED = True

    from . import camp_week_fillers as camp_module

    def place_tactical_watch(
        week: dict[str, Any],
        session_roles: list[dict[str, Any]],
        athlete_model: dict[str, Any],
        day: str,
        *,
        phase: str,
        usage_ledger: dict[str, Any],
    ) -> dict[str, Any] | None:
        d_day = camp_module._calendar_d_day(week, day)
        if d_day is None or d_day <= 0:
            return None
        insert = build_insert_role(
            camp_module._TACTICAL_WATCH_ROLE_KEY,
            athlete_model,
            d_day,
            weekday=str(day).strip().title(),
            tactical_watch_phase=phase,
        )
        insert["camp_phase"] = phase
        camp_module._decorate_insert(
            insert,
            day=day,
            d_day=d_day,
            mandatory_tactical_watch=True,
        )
        session_roles.append(insert)
        gap_module._record_insert_usage(
            usage_ledger,
            camp_module._TACTICAL_WATCH_ROLE_KEY,
            d_day,
        )
        return insert

    def promote_existing_tactical_watch(
        week: dict[str, Any],
        role: dict[str, Any],
        athlete_model: dict[str, Any],
        *,
        phase: str,
        usage_ledger: dict[str, Any],
    ) -> bool:
        day = str(
            role.get("scheduled_day_hint") or role.get("real_weekday") or ""
        ).strip()
        d_day = camp_module._calendar_d_day(week, day)
        if not day or d_day is None or d_day <= 0:
            return False
        template = build_insert_role(
            camp_module._TACTICAL_WATCH_ROLE_KEY,
            athlete_model,
            d_day,
            weekday=day.title(),
            tactical_watch_phase=phase,
        )
        role.clear()
        role.update(template)
        role["camp_phase"] = phase
        camp_module._decorate_insert(
            role,
            day=day,
            d_day=d_day,
            mandatory_tactical_watch=True,
        )
        gap_module._record_insert_usage(
            usage_ledger,
            camp_module._TACTICAL_WATCH_ROLE_KEY,
            d_day,
        )
        return True

    camp_module.build_tactical_watch_template = build_tactical_watch_template
    camp_module._build_insert_role = build_insert_role
    camp_module._place_tactical_watch = place_tactical_watch
    camp_module._promote_existing_tactical_watch = promote_existing_tactical_watch
    camp_module._TACTICAL_WATCH_PROGRESSION_INSTALLED = True
