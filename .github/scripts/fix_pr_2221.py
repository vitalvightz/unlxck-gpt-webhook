from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")


def replace_tail(path: str, marker: str, replacement: str) -> None:
    text = read(path)
    index = text.index(marker)
    write(path, text[:index] + replacement.rstrip() + "\n")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match in {path}, found {count}: {old[:100]!r}")
    write(path, text.replace(old, new, 1))


CAMP_TAIL = r'''def _tactical_watch_roles(session_roles: list[Any]) -> list[dict[str, Any]]:
    return [
        role
        for role in session_roles
        if isinstance(role, dict)
        and str(role.get("role_key") or "") == _TACTICAL_WATCH_ROLE_KEY
    ]


def _phase_watch_guidance(phase: str) -> str:
    if phase == "GPP":
        return (
            "Camp focus: review your latest clean round or a fighter with a similar "
            "style. Find repeatable habits before opponent-specific planning."
        )
    if phase == "TAPER":
        return (
            "Camp focus: review familiar opponent footage and confirmed cues only. "
            "Do not add a new tactical theory this week."
        )
    return (
        "Camp focus: study the confirmed opponent. If footage is limited, use the "
        "closest style match and connect each cue to this week's technical work."
    )


def _decorate_insert(
    insert: dict[str, Any],
    *,
    day: str,
    d_day: int,
    mandatory_tactical_watch: bool = False,
) -> dict[str, Any]:
    day_title = str(day).strip().title()
    insert["session_index"] = 0
    insert["scheduled_day_hint"] = day_title
    insert["real_weekday"] = day_title
    insert["countdown_display_label"] = f"D-{d_day} ({day_title})"
    insert["camp_week_filler"] = True
    if mandatory_tactical_watch:
        insert["mandatory_tactical_watch"] = True
        insert["weekly_requirement"] = "fight_tactical_watch"
        insert["governance"] = {
            **dict(insert.get("governance") or {}),
            "authority": "gap_fill_support_insert",
            "mandatory": True,
            "meaningful_stress": False,
        }
    return insert


def _place_adaptive_filler(
    week: dict[str, Any],
    session_roles: list[dict[str, Any]],
    athlete_model: dict[str, Any],
    day: str,
    *,
    hard_days: set[str],
    usage_ledger: dict[str, Any],
    allow_physical: bool,
) -> dict[str, Any] | None:
    d_day = _calendar_d_day(week, day)
    if d_day is None or d_day <= 0:
        return None

    insert = select_gap_fill_insert(
        athlete_model,
        d_day,
        on_hard_sparring_day=_canonical_day(day) in hard_days,
        usage_ledger=usage_ledger,
    )
    if insert is None:
        return None
    if not allow_physical and insert.get("role_key") in PHYSICAL_INSERTS:
        return None

    _decorate_insert(insert, day=day, d_day=d_day)
    session_roles.append(insert)
    _record_insert_usage(usage_ledger, str(insert.get("role_key") or ""), d_day)
    return insert


def _place_tactical_watch(
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
    )
    insert["display_text"] = (
        f"{build_tactical_watch_template(athlete_model)}\n\n"
        f"{_phase_watch_guidance(phase)}"
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
    return insert


def _promote_existing_tactical_watch(
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
    )
    for key, value in template.items():
        if role.get(key) in (None, "", []):
            role[key] = value
    role["display_text"] = (
        f"{build_tactical_watch_template(athlete_model)}\n\n"
        f"{_phase_watch_guidance(phase)}"
    )
    role["camp_phase"] = phase
    _decorate_insert(
        role,
        day=day,
        d_day=d_day,
        mandatory_tactical_watch=True,
    )
    _record_insert_usage(usage_ledger, _TACTICAL_WATCH_ROLE_KEY, d_day)
    return True


def _eligible_unused_entries(week: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    eligible: list[tuple[int, dict[str, Any]]] = []
    for entry in week.get("intentionally_unused_days") or []:
        if not isinstance(entry, dict):
            continue
        day = str(entry.get("day") or "").strip()
        role = str(entry.get("role") or "").strip()
        d_day = _calendar_d_day(week, day)
        if (
            not day
            or role not in {"off_day", "recovery_only_day"}
            or entry.get("low_aerobic_cap_skipped")
            or d_day is None
            or d_day <= 0
        ):
            continue
        eligible.append((d_day, entry))
    return sorted(eligible, key=lambda item: (item[0] == 1, -item[0]))


def _remove_unused_entry(week: dict[str, Any], selected: dict[str, Any]) -> None:
    week["intentionally_unused_days"] = [
        entry
        for entry in week.get("intentionally_unused_days") or []
        if entry is not selected
    ]


def _shared_day_candidates(
    week: dict[str, Any], session_roles: list[dict[str, Any]]
) -> list[str]:
    grouped = _roles_by_day(session_roles)
    candidates: list[tuple[int, int, str]] = []

    for day in clean_list(week.get("declared_training_days")):
        canonical = _canonical_day(day)
        roles = grouped.get(canonical, [])
        d_day = _calendar_d_day(week, day)
        if len(roles) != 1 or d_day is None or d_day <= 0:
            continue
        role = roles[0]
        role_key = str(role.get("role_key") or "")
        category = str(role.get("category") or "").lower()
        if category in {"technical", "recovery", "support_insert"}:
            priority = 0
        elif role_key == "hard_sparring_day" or category == "sparring":
            priority = 1
        else:
            priority = 2
        candidates.append((priority, 1 if d_day == 1 else 0, str(day)))

    return [day for _, _, day in sorted(candidates)]


def _least_loaded_valid_day_candidates(
    week: dict[str, Any], session_roles: list[dict[str, Any]]
) -> list[str]:
    grouped = _roles_by_day(session_roles)
    candidates: list[tuple[int, int, int, int, int, str]] = []
    for entry in week.get("calendar_days") or []:
        if not isinstance(entry, dict):
            continue
        day = str(entry.get("weekday") or "").strip()
        canonical = _canonical_day(day)
        try:
            d_day = int(entry.get("d_day"))
        except (TypeError, ValueError):
            continue
        if not canonical or d_day <= 0:
            continue
        roles = grouped.get(canonical, [])
        meaningful = sum(
            1
            for role in roles
            if role.get("stress_class") == "meaningful_stress"
            or str(role.get("category") or "").lower() in {"strength", "conditioning"}
        )
        hard_contact = sum(
            1
            for role in roles
            if str(role.get("role_key") or "") == "hard_sparring_day"
            or str(role.get("category") or "").lower() == "sparring"
        )
        candidates.append(
            (len(roles), meaningful, hard_contact, 1 if d_day == 1 else 0, -d_day, day)
        )
    return [day for *_, day in sorted(candidates)]


def _is_optional_support(role: dict[str, Any]) -> bool:
    return bool(
        not role.get("coach_owned")
        and not role.get("mandatory_tactical_watch")
        and str(role.get("role_key") or "") != _TACTICAL_WATCH_ROLE_KEY
        and (
            role.get("camp_week_filler")
            or str(role.get("category") or "") == "support_insert"
        )
    )


def _optional_removal_priority(role: dict[str, Any], index: int) -> tuple[int, int, int]:
    cost = str(role.get("support_insert_cost_category") or "")
    cost_priority = {
        "physical": 0,
        "low_cost_aerobic": 1,
        "low_cost_recovery": 2,
        "zero_cost": 3,
    }.get(cost, 2)
    return (0 if role.get("camp_week_filler") else 1, cost_priority, -index)


def _suppress_role(
    week: dict[str, Any],
    session_roles: list[dict[str, Any]],
    role: dict[str, Any],
    *,
    reason: str,
    reason_code: str,
) -> None:
    if role in session_roles:
        session_roles.remove(role)
    suppressed = dict(role)
    reasons = clean_list(suppressed.get("reasons"))
    reason_codes = clean_list(suppressed.get("reason_codes"))
    suppressed["reasons"] = list(dict.fromkeys([*reasons, reason]))
    suppressed["reason_codes"] = list(dict.fromkeys([*reason_codes, reason_code]))
    week.setdefault("suppressed_roles", []).append(suppressed)


def _remove_lowest_priority_optional_support(
    week: dict[str, Any], session_roles: list[dict[str, Any]]
) -> bool:
    candidates = [
        (index, role)
        for index, role in enumerate(session_roles)
        if isinstance(role, dict) and _is_optional_support(role)
    ]
    if not candidates:
        return False
    index, selected = min(
        candidates,
        key=lambda item: _optional_removal_priority(item[1], item[0]),
    )
    del index
    _suppress_role(
        week,
        session_roles,
        selected,
        reason="Reserved this phase's support slot for the mandatory weekly Tactical Watch.",
        reason_code="mandatory_tactical_watch_reserved_slot",
    )
    return True


def _reserve_tactical_watch_slot(
    week: dict[str, Any], session_roles: list[dict[str, Any]], cap: int
) -> None:
    while _week_filler_count(session_roles) >= cap:
        if not _remove_lowest_priority_optional_support(week, session_roles):
            raise RuntimeError(
                "Unable to reserve the mandatory Tactical Watch slot without exceeding "
                f"the {str(week.get('phase') or '').upper()} support cap of {cap}."
            )


def _enforce_phase_cap(
    week: dict[str, Any], session_roles: list[dict[str, Any]], cap: int
) -> None:
    while _week_filler_count(session_roles) > cap:
        if not _remove_lowest_priority_optional_support(week, session_roles):
            raise RuntimeError(
                "Mandatory Tactical Watch was placed, but the phase support cap cannot "
                "be restored because no optional support role is replaceable."
            )


def _ensure_weekly_tactical_watch(
    week: dict[str, Any],
    athlete_model: dict[str, Any],
    usage_ledger: dict[str, Any],
    cap: int,
) -> bool:
    session_roles = week.get("session_roles")
    if not isinstance(session_roles, list):
        raise RuntimeError("Fight-dated week has no mutable session_roles list.")

    phase = str(week.get("phase") or "").strip().upper()
    promoted: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for role in list(_tactical_watch_roles(session_roles)):
        if _promote_existing_tactical_watch(
            week,
            role,
            athlete_model,
            phase=phase,
            usage_ledger=usage_ledger,
        ):
            promoted.append(role)
        else:
            invalid.append(role)

    for role in invalid:
        _suppress_role(
            week,
            session_roles,
            role,
            reason="Tactical Watch cannot be scheduled on fight day or outside the week's calendar.",
            reason_code="invalid_tactical_watch_day",
        )

    if promoted:
        for duplicate in promoted[1:]:
            _suppress_role(
                week,
                session_roles,
                duplicate,
                reason="Only one mandatory Tactical Watch is required in this fight week.",
                reason_code="duplicate_tactical_watch",
            )
        _enforce_phase_cap(week, session_roles, cap)
        return True

    _reserve_tactical_watch_slot(week, session_roles, cap)

    for _, entry in _eligible_unused_entries(week):
        day = str(entry.get("day") or "").strip()
        insert = _place_tactical_watch(
            week,
            session_roles,
            athlete_model,
            day,
            phase=phase,
            usage_ledger=usage_ledger,
        )
        if insert is None:
            continue
        insert["converted_from_unused_day"] = True
        insert["original_unused_day_role"] = str(entry.get("role") or "")
        _remove_unused_entry(week, entry)
        _enforce_phase_cap(week, session_roles, cap)
        return True

    for day in _shared_day_candidates(week, session_roles):
        if _place_tactical_watch(
            week,
            session_roles,
            athlete_model,
            day,
            phase=phase,
            usage_ledger=usage_ledger,
        ) is not None:
            _enforce_phase_cap(week, session_roles, cap)
            return True

    for day in _least_loaded_valid_day_candidates(week, session_roles):
        if _place_tactical_watch(
            week,
            session_roles,
            athlete_model,
            day,
            phase=phase,
            usage_ledger=usage_ledger,
        ) is not None:
            _enforce_phase_cap(week, session_roles, cap)
            return True

    raise RuntimeError(
        "Unable to place mandatory weekly Tactical Watch: no valid non-fight-day "
        "calendar slot exists."
    )


def _fill_adaptive_slots(
    week: dict[str, Any],
    athlete_model: dict[str, Any],
    cap: int,
    usage_ledger: dict[str, Any],
) -> None:
    session_roles = week.get("session_roles")
    if not isinstance(session_roles, list):
        return

    hard_days = _week_hard_sparring_days(week, athlete_model)

    for _, entry in list(_eligible_unused_entries(week)):
        if _week_filler_count(session_roles) >= cap:
            break
        day = str(entry.get("day") or "").strip()
        insert = _place_adaptive_filler(
            week,
            session_roles,
            athlete_model,
            day,
            hard_days=hard_days,
            usage_ledger=usage_ledger,
            allow_physical=_week_physical_filler_count(session_roles) < 1,
        )
        if insert is None:
            continue
        insert["converted_from_unused_day"] = True
        insert["original_unused_day_role"] = str(entry.get("role") or "")
        _remove_unused_entry(week, entry)

    if _week_filler_count(session_roles) >= cap:
        return

    shared_added = 0
    day_counts = _role_day_counts(session_roles)
    for day in _shared_day_candidates(week, session_roles):
        if (
            _week_filler_count(session_roles) >= cap
            or shared_added >= _MAX_SHARED_DAY_FILLERS
        ):
            break
        canonical = _canonical_day(day)
        if day_counts.get(canonical, 0) != 1:
            continue
        insert = _place_adaptive_filler(
            week,
            session_roles,
            athlete_model,
            day,
            hard_days=hard_days,
            usage_ledger=usage_ledger,
            allow_physical=_week_physical_filler_count(session_roles) < 1,
        )
        if insert is None:
            continue
        shared_added += 1
        day_counts[canonical] = day_counts.get(canonical, 0) + 1


def apply_camp_week_fillers(
    weekly_role_map: dict[str, Any],
    athlete_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply weekly Tactical Watch and adaptive support slots in place."""
    if not isinstance(weekly_role_map, dict):
        return weekly_role_map

    athlete_model = athlete_model or {}
    has_future_fight = _has_future_fight(athlete_model)
    usage_ledger = _new_usage_ledger()

    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue

        phase = str(week.get("phase") or "").strip().upper()
        if has_future_fight:
            cap = _PHASE_FILLER_CAPS.get(phase)
            if not cap:
                continue
            _ensure_weekly_tactical_watch(week, athlete_model, usage_ledger, cap)
            if _week_is_compressed(week):
                continue
            _fill_adaptive_slots(week, athlete_model, cap, usage_ledger)
            _enforce_phase_cap(week, week.get("session_roles") or [], cap)
            continue

        cap = _LEGACY_PHASE_FILLER_CAPS.get(phase)
        if not cap or _week_is_compressed(week):
            continue
        _fill_adaptive_slots(week, athlete_model, cap, usage_ledger)

    return weekly_role_map
'''


GAP_TAIL = r'''def _segment_watch_roles(
    sequence: list[dict[str, Any]], segment: int
) -> list[dict[str, Any]]:
    return [
        role
        for role in sequence
        if str(role.get("role_key") or "") == "tactical_watch"
        and (offset := _role_offset(role)) is not None
        and _segment_for_offset(offset) == segment
    ]


def _segment_watch_offset(
    sequence: list[dict[str, Any]],
    *,
    segment: int,
    days_until_fight: int,
) -> int | None:
    lower, upper = _watch_segment_bounds(segment, days_until_fight)
    if lower > upper:
        return None

    target = _watch_target_offset(segment, days_until_fight)
    role_counts = _offset_role_counts(sequence)
    offsets = list(range(lower, upper + 1))
    fully_spaced = [
        offset
        for offset in offsets
        if role_counts.get(offset, 0) == 0
        and all(abs(existing - offset) > 1 for existing in role_counts)
    ]
    if fully_spaced:
        return min(fully_spaced, key=lambda offset: (abs(offset - target), -offset))

    offsets.sort(
        key=lambda offset: (
            1 if role_counts.get(offset, 0) else 0,
            sum(count for existing, count in role_counts.items() if abs(existing - offset) == 1),
            sum(count for existing, count in role_counts.items() if abs(existing - offset) == 2),
            abs(offset - target),
            role_counts.get(offset, 0),
            -offset,
        )
    )
    return offsets[0] if offsets else None


def _mandatory_watch_guidance(offset: int) -> str:
    if offset <= 7:
        return (
            "Fight-week focus: review familiar opponent footage and confirmed cues "
            "only. Do not add a new tactical theory this week."
        )
    return (
        "Camp focus: study the confirmed opponent. If footage is limited, use the "
        "closest style match and connect each cue to this week's technical work."
    )


def _build_mandatory_tactical_watch(
    athlete_model: dict[str, Any],
    offset: int,
    weekday: str | None,
) -> dict[str, Any]:
    watch = _build_insert_role("tactical_watch", athlete_model, offset, weekday)
    watch["display_text"] = (
        f"{build_tactical_watch_template(athlete_model)}\n\n"
        f"{_mandatory_watch_guidance(offset)}"
    )
    watch["mandatory_tactical_watch"] = True
    watch["weekly_requirement"] = "fight_tactical_watch"
    watch["tactical_watch_segment"] = _segment_for_offset(offset)
    watch["governance"] = {
        **dict(watch.get("governance") or {}),
        "authority": "gap_fill_support_insert",
        "mandatory": True,
        "meaningful_stress": False,
    }
    return watch


def _promote_mandatory_tactical_watch(
    role: dict[str, Any],
    athlete_model: dict[str, Any],
    countdown_map: dict[str, str],
) -> dict[str, Any]:
    offset = _role_offset(role)
    if offset is None or offset <= 0:
        raise RuntimeError("Existing Tactical Watch is not on a valid countdown day.")
    weekday = str(
        role.get("scheduled_day_hint")
        or role.get("real_weekday")
        or countdown_map.get(f"D-{offset}")
        or ""
    ).strip() or None
    template = _build_mandatory_tactical_watch(athlete_model, offset, weekday)
    preserved = {
        key: value
        for key, value in role.items()
        if key not in {
            "display_text",
            "mandatory_tactical_watch",
            "weekly_requirement",
            "tactical_watch_segment",
            "governance",
        }
    }
    role.clear()
    role.update(template)
    for key, value in preserved.items():
        role.setdefault(key, value)
    return role


def _replace_with_mandatory_tactical_watch(
    role: dict[str, Any],
    athlete_model: dict[str, Any],
    countdown_map: dict[str, str],
) -> dict[str, Any]:
    offset = _role_offset(role)
    if offset is None or offset <= 0:
        raise RuntimeError("Tactical support replacement has no valid countdown day.")
    weekday = str(
        role.get("scheduled_day_hint")
        or role.get("real_weekday")
        or countdown_map.get(f"D-{offset}")
        or ""
    ).strip() or None
    replaced_role_key = str(role.get("role_key") or "")
    replacement = _build_mandatory_tactical_watch(athlete_model, offset, weekday)
    replacement["replaced_role_key"] = replaced_role_key
    role.clear()
    role.update(replacement)
    return role


def _ensure_weekly_tactical_watches(
    ordered: list[dict[str, Any]],
    athlete_model: dict[str, Any],
    *,
    days_until_fight: int,
    countdown_map: dict[str, str],
) -> list[dict[str, Any]]:
    if not _has_future_fight(athlete_model, days_until_fight):
        return []

    required_segments = range(_segment_for_offset(days_until_fight) + 1)
    inserts: list[dict[str, Any]] = []
    combined = ordered + inserts
    for segment in reversed(list(required_segments)):
        existing_watches = _segment_watch_roles(combined, segment)
        if existing_watches:
            _promote_mandatory_tactical_watch(
                existing_watches[0], athlete_model, countdown_map
            )
            continue

        replaceable_tactical = next(
            (
                role
                for role in combined
                if str(role.get("role_key") or "") in (TACTICAL_INSERTS - {"tactical_watch"})
                and (offset := _role_offset(role)) is not None
                and _segment_for_offset(offset) == segment
            ),
            None,
        )
        if replaceable_tactical is not None:
            _replace_with_mandatory_tactical_watch(
                replaceable_tactical, athlete_model, countdown_map
            )
            continue

        offset = _segment_watch_offset(
            combined,
            segment=segment,
            days_until_fight=days_until_fight,
        )
        if offset is None or offset <= 0:
            raise RuntimeError(
                f"Unable to place mandatory Tactical Watch in countdown segment {segment}."
            )
        weekday = countdown_map.get(f"D-{offset}")
        watch = _build_mandatory_tactical_watch(athlete_model, offset, weekday)
        inserts.append(watch)
        combined = ordered + inserts
    return inserts


def apply_gap_fill_inserts(
    session_sequence: list[dict[str, Any]],
    athlete_model: dict[str, Any],
) -> list[dict[str, Any]]:
    ordered = sorted(
        [dict(role) for role in session_sequence],
        key=lambda role: int(_role_offset(role) or 0),
        reverse=True,
    )

    raw_days = athlete_model.get("days_until_fight")
    positive_offsets = [
        offset
        for role in ordered
        if (offset := _role_offset(role)) is not None and offset > 0
    ]
    if raw_days is not None and str(raw_days).strip() != "":
        try:
            days_until_fight = int(raw_days)
        except (TypeError, ValueError):
            days_until_fight = max(positive_offsets, default=0)
    else:
        days_until_fight = max(positive_offsets, default=0)

    if days_until_fight <= 0:
        return ordered

    creation_weekday = _resolve_plan_creation_weekday(days_until_fight, athlete_model)
    countdown_map = _countdown_weekday_map(creation_weekday, days_until_fight)
    hard_sparring_days = {
        day.strip().lower()
        for day in ordered_weekdays(clean_list(athlete_model.get("hard_sparring_days", [])))
    }

    existing_exclusive_offsets = {
        offset
        for role in ordered
        if str(role.get("role_key") or "") != "hard_sparring_day"
        and not is_low_cost_coexistable_filler(role)
        and (offset := _role_offset(role)) is not None
    }
    candidate_offsets = (
        _candidate_offsets_from_sequence(positive_offsets, days_until_fight)
        if positive_offsets
        else []
    )

    watch_horizon = min(days_until_fight, 21)
    inserts = _ensure_weekly_tactical_watches(
        ordered,
        athlete_model,
        days_until_fight=watch_horizon,
        countdown_map=countdown_map,
    )
    mandatory_watch_offsets = {
        int(offset)
        for role in ordered + inserts
        if str(role.get("role_key") or "") == "tactical_watch"
        and role.get("mandatory_tactical_watch")
        and (offset := _role_offset(role)) is not None
    }

    if days_until_fight <= 7:
        final_sequence = sorted(
            ordered + inserts,
            key=lambda role: int(_role_offset(role) or 0),
            reverse=True,
        )
        for index, role in enumerate(final_sequence, start=1):
            role["session_index"] = index
        return final_sequence

    physical_segment_counts: dict[int, int] = {}
    for role in ordered:
        role_key = str(role.get("role_key") or "")
        offset = _role_offset(role)
        if role_key in PHYSICAL_INSERTS and offset is not None:
            segment = _segment_for_offset(offset)
            physical_segment_counts[segment] = (
                physical_segment_counts.get(segment, 0) + 1
            )

    usage_ledger = _usage_ledger_from_sequence(ordered + inserts)
    conditioning_present = any(
        str(role.get("role_key") or "") in LOW_COST_AEROBIC_INSERTS
        for role in ordered + inserts
    )
    conditioning_required = _has_conditioning_goal(athlete_model)
    injury_state = classify_injury_state(athlete_model)
    coach_day_candidates = [
        (offset, 0)
        for offset in _declared_hard_sparring_offsets(
            countdown_map, hard_sparring_days
        )
        if offset not in existing_exclusive_offsets
        and offset not in mandatory_watch_offsets
    ]
    candidate_offsets = candidate_offsets + coach_day_candidates

    for target_offset, gap_span in candidate_offsets:
        if (
            target_offset <= 0
            or target_offset in existing_exclusive_offsets
            or target_offset in mandatory_watch_offsets
        ):
            continue
        weekday = countdown_map.get(f"D-{target_offset}")
        on_hard_sparring_day = bool(
            weekday and weekday.strip().lower() in hard_sparring_days
        )
        force_conditioning = (
            conditioning_required
            and not conditioning_present
            and bool(
                _safe_conditioning_maintenance_inserts(
                    athlete_model,
                    target_offset,
                    injury_state,
                    on_hard_sparring_day=on_hard_sparring_day,
                )
            )
        )
        if (
            len(inserts) >= MAX_INSERTS_TOTAL_D21_TO_D0
            and not force_conditioning
        ):
            break

        insert = select_gap_fill_insert(
            athlete_model,
            target_offset,
            on_hard_sparring_day=on_hard_sparring_day,
            usage_ledger=usage_ledger,
            gap_span=gap_span,
            force_tactical=False,
            force_conditioning=force_conditioning,
        )
        if insert is None:
            continue

        if insert["role_key"] in PHYSICAL_INSERTS:
            segment = _segment_for_offset(target_offset)
            if (
                physical_segment_counts.get(segment, 0)
                >= MAX_PHYSICAL_INSERTS_PER_7_DAY_SEGMENT
            ):
                insert = _select_non_physical_insert(
                    athlete_model,
                    target_offset,
                    on_hard_sparring_day=on_hard_sparring_day,
                    usage_ledger=usage_ledger,
                    gap_span=gap_span,
                    force_tactical=False,
                )
                if insert is None:
                    continue
            else:
                physical_segment_counts[segment] = (
                    physical_segment_counts.get(segment, 0) + 1
                )

        insert["scheduled_day_hint"] = weekday
        if weekday:
            insert["real_weekday"] = weekday
            insert["countdown_display_label"] = (
                f"D-{target_offset} ({weekday.title()})"
            )
        inserts.append(insert)
        _record_insert_usage(
            usage_ledger, str(insert.get("role_key") or ""), target_offset
        )
        if insert.get("role_key") in LOW_COST_AEROBIC_INSERTS:
            conditioning_present = True
        if not is_low_cost_coexistable_filler(insert):
            existing_exclusive_offsets.add(target_offset)

    final_sequence = sorted(
        ordered + inserts,
        key=lambda role: int(_role_offset(role) or 0),
        reverse=True,
    )
    for index, role in enumerate(final_sequence, start=1):
        role["session_index"] = index
    return final_sequence
'''


MANDATORY_TESTS = r'''from __future__ import annotations

from fightcamp.camp_week_fillers import apply_camp_week_fillers
from fightcamp.gap_fill_inserts import apply_gap_fill_inserts


def _athlete(**overrides):
    athlete = {
        "sport": "boxing",
        "days_until_fight": 21,
        "plan_creation_weekday": "monday",
        "hard_sparring_days": [],
        "fatigue": "low",
        "fatigue_level": "low",
        "readiness_flags": [],
        "weight_cut_risk": False,
        "weight_cut_pct": 0.0,
        "weaknesses": [],
        "key_goals": [],
        "injuries": [],
        "parsed_injuries": [],
        "guided_injury": None,
        "injury_restrictions": [],
    }
    athlete.update(overrides)
    return athlete


def _session(offset: int, role_key: str = "strength_touch_day") -> dict:
    return {
        "session_index": 1,
        "category": "strength",
        "role_key": role_key,
        "scheduled_day_hint": "monday",
        "countdown_offset": offset,
        "countdown_label": f"D-{offset}",
        "scheduled_countdown_label": f"D-{offset}",
    }


def _week(phase: str, d_day: int, *, compressed: bool = False) -> dict:
    return {
        "phase": phase,
        "session_roles": [
            {
                "role_key": "primary_strength_day",
                "category": "strength",
                "scheduled_day_hint": "Monday",
            }
        ],
        "calendar_days": [
            {"weekday": "monday", "d_day": d_day},
            {"weekday": "wednesday", "d_day": d_day - 2},
            {"weekday": "friday", "d_day": d_day - 4},
        ],
        "intentionally_unused_days": [
            {"day": "Wednesday", "role": "recovery_only_day"},
            {"day": "Friday", "role": "off_day"},
        ],
        "declared_training_days": ["Monday", "Wednesday", "Friday"],
        "intentional_compression": {"active": compressed},
    }


def _watches(roles: list[dict]) -> list[dict]:
    return [role for role in roles if role.get("role_key") == "tactical_watch"]


def _supports(roles: list[dict]) -> list[dict]:
    return [
        role
        for role in roles
        if role.get("camp_week_filler") or role.get("category") == "support_insert"
    ]


def test_fight_dated_normal_camp_reserves_one_watch_in_every_phase():
    role_map = {"weeks": [_week("GPP", 42), _week("SPP", 28), _week("TAPER", 7)]}
    apply_camp_week_fillers(role_map, _athlete(days_until_fight=42))

    support_counts = []
    for week in role_map["weeks"]:
        watches = _watches(week["session_roles"])
        assert len(watches) == 1
        assert watches[0]["mandatory_tactical_watch"] is True
        assert watches[0]["weekly_requirement"] == "fight_tactical_watch"
        assert watches[0]["governance"]["authority"] == "gap_fill_support_insert"
        assert watches[0]["governance"]["meaningful_stress"] is False
        support_counts.append(len(_supports(week["session_roles"])))

    assert support_counts == [1, 2, 1]


def test_compressed_week_keeps_watch_but_blocks_optional_fillers():
    week = _week("SPP", 28, compressed=True)
    apply_camp_week_fillers(
        {"weeks": [week]},
        _athlete(days_until_fight=28, fatigue="high", fatigue_level="high"),
    )
    supports = _supports(week["session_roles"])
    assert len(supports) == 1
    assert supports[0]["role_key"] == "tactical_watch"


def test_non_fight_dated_gpp_retains_legacy_no_filler_behaviour():
    week = _week("GPP", 42)
    apply_camp_week_fillers({"weeks": [week]}, _athlete(days_until_fight=None))
    assert _watches(week["session_roles"]) == []
    assert week["intentionally_unused_days"]


def test_full_normal_camp_week_uses_least_loaded_calendar_fallback():
    week = {
        "phase": "SPP",
        "session_roles": [
            {"role_key": "strength_a", "category": "strength", "scheduled_day_hint": "Monday"},
            {"role_key": "conditioning_a", "category": "conditioning", "scheduled_day_hint": "Monday"},
            {"role_key": "strength_b", "category": "strength", "scheduled_day_hint": "Wednesday"},
            {"role_key": "technical_b", "category": "technical", "scheduled_day_hint": "Wednesday"},
            {"role_key": "strength_c", "category": "strength", "scheduled_day_hint": "Friday"},
            {"role_key": "recovery_c", "category": "recovery", "scheduled_day_hint": "Friday"},
        ],
        "calendar_days": [
            {"weekday": "monday", "d_day": 28},
            {"weekday": "wednesday", "d_day": 26},
            {"weekday": "friday", "d_day": 24},
        ],
        "intentionally_unused_days": [],
        "declared_training_days": ["Monday", "Wednesday", "Friday"],
    }
    apply_camp_week_fillers({"weeks": [week]}, _athlete(days_until_fight=28))
    watches = _watches(week["session_roles"])
    assert len(watches) == 1
    assert watches[0]["scheduled_day_hint"] in {"Monday", "Wednesday", "Friday"}


def test_phase_cap_replaces_lowest_priority_optional_support():
    week = _week("SPP", 28)
    week["intentionally_unused_days"] = []
    week["session_roles"].extend(
        [
            {
                "role_key": "mobility_rehab",
                "category": "support_insert",
                "scheduled_day_hint": "Wednesday",
                "camp_week_filler": True,
                "support_insert_cost_category": "physical",
            },
            {
                "role_key": "breathing_reset",
                "category": "support_insert",
                "scheduled_day_hint": "Friday",
                "camp_week_filler": True,
                "support_insert_cost_category": "low_cost_recovery",
            },
        ]
    )
    apply_camp_week_fillers({"weeks": [week]}, _athlete(days_until_fight=28))
    assert len(_supports(week["session_roles"])) == 2
    assert len(_watches(week["session_roles"])) == 1
    assert any(
        "mandatory_tactical_watch_reserved_slot" in role.get("reason_codes", [])
        for role in week.get("suppressed_roles", [])
    )


def test_existing_normal_camp_watch_is_promoted_in_place():
    week = _week("SPP", 28)
    week["session_roles"].append(
        {
            "role_key": "tactical_watch",
            "category": "support_insert",
            "scheduled_day_hint": "Wednesday",
            "display_text": "old text",
        }
    )
    apply_camp_week_fillers({"weeks": [week]}, _athlete(days_until_fight=28))
    watches = _watches(week["session_roles"])
    assert len(watches) == 1
    watch = watches[0]
    assert watch["mandatory_tactical_watch"] is True
    assert watch["weekly_requirement"] == "fight_tactical_watch"
    assert watch["governance"]["authority"] == "gap_fill_support_insert"
    assert "confirmed opponent" in watch["display_text"].lower()


def test_late_fight_sequence_has_one_watch_per_seven_day_segment():
    sequence = apply_gap_fill_inserts(
        [_session(21), _session(16), _session(11), _session(6)],
        _athlete(days_until_fight=21),
    )
    watches = _watches(sequence)
    assert len(watches) == 3
    assert {watch["tactical_watch_segment"] for watch in watches} == {0, 1, 2}
    assert all(watch["mandatory_tactical_watch"] is True for watch in watches)
    assert all(watch["countdown_offset"] > 0 for watch in watches)


def test_late_fight_horizon_uses_fight_date_not_last_main_session():
    sequence = apply_gap_fill_inserts(
        [_session(11), _session(4)],
        _athlete(days_until_fight=21),
    )
    assert {watch["tactical_watch_segment"] for watch in _watches(sequence)} == {0, 1, 2}
    assert any(watch["countdown_offset"] >= 15 for watch in _watches(sequence))


def test_existing_late_fight_watch_is_promoted_without_duplicate():
    existing = {
        **_session(1, "tactical_watch"),
        "category": "support_insert",
        "stress_class": "support",
        "cost_class": "low",
        "governance": {"meaningful_stress": False},
    }
    sequence = apply_gap_fill_inserts(
        [existing],
        _athlete(days_until_fight=1, hard_sparring_days=["tuesday"]),
    )
    watches = _watches(sequence)
    assert len(watches) == 1
    assert watches[0]["mandatory_tactical_watch"] is True
    assert watches[0]["weekly_requirement"] == "fight_tactical_watch"
    assert watches[0]["governance"]["authority"] == "gap_fill_support_insert"
    assert "familiar opponent footage" in watches[0]["display_text"].lower()


def test_fight_day_never_receives_tactical_watch():
    sequence = apply_gap_fill_inserts(
        [_session(0, "fight_week_freshness_day")],
        _athlete(days_until_fight=0),
    )
    assert _watches(sequence) == []
'''


def patch_camp_fillers() -> None:
    replace_tail("fightcamp/camp_week_fillers.py", "def _week_has_tactical_watch(", CAMP_TAIL)


def patch_gap_fillers() -> None:
    replace_tail("fightcamp/gap_fill_inserts.py", "def _segment_has_tactical_watch(", GAP_TAIL)


def patch_finalizer_packet() -> None:
    path = "fightcamp/stage2_finalizer_packet.py"
    replace_once(
        path,
        '        "athlete_facing_label",\n        "countdown_label",',
        '        "athlete_facing_label",\n        "camp_week_filler",\n        "mandatory_tactical_watch",\n        "weekly_requirement",\n        "camp_phase",\n        "tactical_watch_segment",\n        "stress_class",\n        "cost_class",\n        "support_insert_category",\n        "support_insert_cost_category",\n        "governance",\n        "countdown_label",',
    )
    replace_once(
        path,
        '            "Do not omit selected support, recovery, freshness, mobility, reset, or technical roles because they are low stress or short duration.",',
        '            "Do not omit selected support, recovery, freshness, mobility, reset, or technical roles because they are low stress or short duration.",\n            "Any role marked mandatory_tactical_watch or weekly_requirement=fight_tactical_watch is authoritative, must render, and must never be moved to suppressed_roles.",',
    )


def patch_existing_contract_tests() -> None:
    modes = "tests/test_stage2_payload_modes.py"
    replace_once(
        modes,
        '''        assert [entry["role_key"] for entry in app_sequence] == [\n            "fight_week_freshness_day",\n            "tactical_cue_card",\n        ]''',
        '''        assert [entry["role_key"] for entry in app_sequence] == [\n            "fight_week_freshness_day",\n            "tactical_watch",\n        ]''',
    )
    replace_once(
        modes,
        '        assert [entry["role_key"] for entry in app_sequence] == ["tactical_cue_card"]',
        '        assert [entry["role_key"] for entry in app_sequence] == ["tactical_watch"]',
    )
    replace_once(
        modes,
        '''        assert [entry["role_key"] for entry in payload["late_fight_session_sequence"]] == [\n            "fight_week_freshness_day",\n            "neural_primer_day",\n        ]''',
        '''        assert [entry["role_key"] for entry in payload["late_fight_session_sequence"]] == [\n            "fight_week_freshness_day",\n            "tactical_watch",\n            "neural_primer_day",\n        ]''',
    )
    replace_once(
        modes,
        '''        assert [entry["role_key"] for entry in payload["late_fight_session_sequence"]] == [\n            "neural_primer_day",\n        ]''',
        '''        assert [entry["role_key"] for entry in payload["late_fight_session_sequence"]] == [\n            "neural_primer_day",\n            "tactical_watch",\n        ]''',
    )

    brief = "tests/test_stage2_planning_brief.py"
    replace_once(
        brief,
        '''        assert roles_from_seq == [\n            "tactical_cue_card",\n            "fight_week_freshness_day",\n            "neural_primer_day",\n        ]''',
        '''        assert roles_from_seq == [\n            "tactical_watch",\n            "fight_week_freshness_day",\n            "neural_primer_day",\n        ]''',
    )
    replace_once(
        brief,
        '''        assert [entry["role_key"] for entry in brief["late_fight_session_sequence"]] == [\n            "fight_week_freshness_day",\n            "neural_primer_day",\n        ]''',
        '''        assert [entry["role_key"] for entry in brief["late_fight_session_sequence"]] == [\n            "fight_week_freshness_day",\n            "tactical_watch",\n            "neural_primer_day",\n        ]''',
    )


def write_mandatory_tests() -> None:
    write("tests/test_mandatory_weekly_tactical_watch.py", MANDATORY_TESTS.rstrip() + "\n")


def main() -> None:
    patch_camp_fillers()
    patch_gap_fillers()
    patch_finalizer_packet()
    patch_existing_contract_tests()
    write_mandatory_tests()


if __name__ == "__main__":
    main()
