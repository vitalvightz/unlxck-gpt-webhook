"""One frequency policy for every scheduled mental-training task.

Fight Visualisation, Tactical Watch, the tactical cue card, self review and the
generic neural visualisation are all zero-load mental work, but each used to be
scheduled by its own placer: camp visualisations up to three times a week, a
mandatory Tactical Watch every week, a five-day countdown protocol, plus gap
fillers that could add more of each. Individually defensible; together they put
a mental card on most days of the camp.

This module groups them into three athlete-facing categories and owns how often
each may appear. It never selects content -- the banks and their selectors stay
authoritative -- and it never adds a task. It only decides which of the tasks the
placers proposed are kept, and runs last in every pipeline that schedules them,
so no independent placer can restore what it removed.

* **Visualise** (``fight_visualization``, ``neural_visualization``): rehearse a
  specific performance scenario.
* **Analyse** (``tactical_watch``, ``tactical_cue_card``): study one tactical
  problem.
* **Reflect** (``self_review``): review a completed sparring session.

Removing a zero-load mental task cannot change physical programming: the
placers run unchanged and these roles never occupy a physical-session slot
(see :mod:`fightcamp.physical_session_frequency`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

VISUALISE = "visualise"
ANALYSE = "analyse"
REFLECT = "reflect"

VISUALISE_KEYS = frozenset({"fight_visualization", "neural_visualization"})
ANALYSE_KEYS = frozenset({"tactical_watch", "tactical_cue_card"})
REFLECT_KEYS = frozenset({"self_review"})
MENTAL_ROLE_KEYS = VISUALISE_KEYS | ANALYSE_KEYS | REFLECT_KEYS

CATEGORY_LABELS = {
    VISUALISE: "Visualise",
    ANALYSE: "Analyse",
    REFLECT: "Reflect",
}

# Fight week is D-6..D-0. Only brief rehearsal of familiar cues happens here:
# no tactical study and no new decision-making.
FIGHT_WEEK_LAST_OFFSET = 6

# Countdown rehearsal. D-7 (Tactical Picture) is the last full scenario
# rehearsal before fight week; D-1 (Familiar & Ready) and D-0 (Trust ->
# Compete, pre-bout) are the genuine fight-day preparation. D-5 Read -> React
# and D-3 Pressure -> Reset are the same style-owned scenarios the camp block
# already rotates through, so in fight week they only return when mental
# preparation is prioritised (D-3, the composure rehearsal).
COUNTDOWN_VISUALIZATION_DAYS = (7, 1, 0)
PRIORITISED_COUNTDOWN_VISUALIZATION_DAYS = (7, 3, 1, 0)

# Visualise: 1 a week by default, 2 when mental preparation is prioritised.
VISUALISATIONS_PER_WEEK = 1
PRIORITISED_VISUALISATIONS_PER_WEEK = 2
VISUALISATION_MAX_DURATION_MIN = 8

# Analyse: one focused assignment every two weeks, weekly when prioritised.
ANALYSE_SPACING_DAYS = 14
PRIORITISED_ANALYSE_SPACING_DAYS = 7
ANALYSE_MAX_DURATION_MIN = 10

# Reflect: a short post-sparring reflection, at most once a week, only where
# the week actually holds contact.
REFLECTIONS_PER_WEEK = 1
REFLECTION_DURATION_MIN = 2

# Explicit prioritisation only. A mindset note on its own (almost every intake
# has one) is context for the bank's coaching, not a request for more sessions.
_MENTAL_PRIORITY_TOKENS = (
    "mental",
    "mindset",
    "composure",
    "confidence",
    "visualis",
    "visualiz",
    "focus",
    "nerves",
    "psych",
)


@dataclass(frozen=True)
class MentalTrainingPolicy:
    prioritised: bool
    visualisations_per_week: int
    countdown_visualization_days: tuple[int, ...]
    analyse_spacing_days: int
    reflections_per_week: int = REFLECTIONS_PER_WEEK


def _tokens(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return [str(item or "").strip().lower() for item in values if str(item or "").strip()]


def mental_prep_prioritised(athlete_model: dict[str, Any] | None) -> bool:
    """True only when the athlete explicitly asked for mental preparation."""
    model = athlete_model if isinstance(athlete_model, dict) else {}
    if model.get("mental_prep_priority") is True:
        return True
    selected = [
        *_tokens(model.get("key_goals")),
        *_tokens(model.get("primary_goal")),
        *_tokens(model.get("weaknesses")),
        *_tokens(model.get("weak_areas")),
    ]
    return any(token in value for value in selected for token in _MENTAL_PRIORITY_TOKENS)


def mental_training_policy(athlete_model: dict[str, Any] | None) -> MentalTrainingPolicy:
    if mental_prep_prioritised(athlete_model):
        return MentalTrainingPolicy(
            prioritised=True,
            visualisations_per_week=PRIORITISED_VISUALISATIONS_PER_WEEK,
            countdown_visualization_days=PRIORITISED_COUNTDOWN_VISUALIZATION_DAYS,
            analyse_spacing_days=PRIORITISED_ANALYSE_SPACING_DAYS,
        )
    return MentalTrainingPolicy(
        prioritised=False,
        visualisations_per_week=VISUALISATIONS_PER_WEEK,
        countdown_visualization_days=COUNTDOWN_VISUALIZATION_DAYS,
        analyse_spacing_days=ANALYSE_SPACING_DAYS,
    )


def mental_category(role: dict[str, Any] | str | None) -> str | None:
    key = role if isinstance(role, str) else str((role or {}).get("role_key") or "")
    if key in VISUALISE_KEYS:
        return VISUALISE
    if key in ANALYSE_KEYS:
        return ANALYSE
    if key in REFLECT_KEYS:
        return REFLECT
    return None


def is_countdown_visualization(role: dict[str, Any]) -> bool:
    return (
        str(role.get("role_key") or "") == "fight_visualization"
        and not role.get("optional_fight_visualization")
    )


@dataclass
class _Entry:
    role: dict[str, Any]
    offset: int
    bucket: Any
    category: str
    fixed: bool = False


def _visualise_rank(entry: _Entry) -> tuple[int, int]:
    role = entry.role
    if is_countdown_visualization(role):
        rank = 0
    elif str(role.get("role_key") or "") == "fight_visualization":
        rank = 1
    else:
        # The generic neural visualisation duplicates the bank's scenario
        # rehearsal; it only survives where no bank session exists.
        rank = 2
    return rank, -entry.offset


def _spread_pick(entries: list[_Entry], limit: int, taken: Iterable[int] = ()) -> list[_Entry]:
    """Up to ``limit`` entries in rank order, preferring non-adjacent days."""
    ordered = sorted(entries, key=_visualise_rank)
    chosen: list[_Entry] = []
    taken_offsets = list(taken)
    for allow_adjacent in (False, True):
        for entry in ordered:
            if len(chosen) >= limit:
                break
            spaced = [*(other.offset for other in chosen), *taken_offsets]
            if entry in chosen or entry.offset in spaced:
                continue
            if not allow_adjacent and any(abs(entry.offset - other) <= 1 for other in spaced):
                continue
            chosen.append(entry)
    return chosen


def _analyse_rank(entry: _Entry, contact_offsets: set[int]) -> tuple[int, int, int]:
    is_bank_watch = str(entry.role.get("role_key") or "") == "tactical_watch"
    # Prefer a day the athlete actually sparred or trained contact: that is
    # where real observations and coach feedback come from.
    return (
        0 if is_bank_watch else 1,
        0 if entry.offset in contact_offsets else 1,
        -entry.offset,
    )


def _pick_analyse(
    entries: list[_Entry],
    spacing: int,
    contact_offsets: set[int],
    fixed_offsets: Iterable[int] = (),
) -> list[_Entry]:
    """Furthest-out first: one per ``spacing``-day window, best candidate wins."""
    anchors = list(fixed_offsets)

    def clear(entry: _Entry) -> bool:
        return all(abs(entry.offset - other) >= spacing for other in anchors)

    remaining = sorted((entry for entry in entries if clear(entry)), key=lambda entry: -entry.offset)
    kept: list[_Entry] = []
    while remaining:
        anchor = remaining[0].offset
        window = [entry for entry in remaining if anchor - entry.offset < spacing]
        best = min(window, key=lambda entry: _analyse_rank(entry, contact_offsets))
        kept.append(best)
        anchors.append(best.offset)
        remaining = [entry for entry in remaining if clear(entry)]
    return kept


def _clamp_duration(role: dict[str, Any], maximum: int) -> None:
    prescribed = role.get("prescribed_duration_min")
    if isinstance(prescribed, int) and prescribed > maximum:
        role["prescribed_duration_min"] = maximum
        nested = role.get("fight_visualization")
        if isinstance(nested, dict):
            nested["prescribed_duration_min"] = maximum
    duration = role.get("duration_min")
    if isinstance(duration, list) and duration and all(isinstance(v, int) for v in duration):
        role["duration_min"] = [min(value, maximum) for value in duration]


def _stamp(role: dict[str, Any], category: str, policy: MentalTrainingPolicy) -> None:
    role["mental_category"] = category
    role["mental_category_label"] = CATEGORY_LABELS[category]
    role["mental_task_optional"] = True
    role["mental_frequency_policy"] = "prioritised" if policy.prioritised else "default"
    if category == VISUALISE:
        _clamp_duration(role, VISUALISATION_MAX_DURATION_MIN)
    elif category == ANALYSE:
        _clamp_duration(role, ANALYSE_MAX_DURATION_MIN)


def govern_mental_roles(
    roles: Iterable[dict[str, Any]],
    athlete_model: dict[str, Any] | None,
    *,
    offset_of: Callable[[dict[str, Any]], int | None],
    bucket_of: Callable[[dict[str, Any], int], Any],
    contact_offsets: Iterable[int] = (),
    relocate: Callable[[dict[str, Any], int], None] | None = None,
    is_fixed: Callable[[dict[str, Any]], bool] | None = None,
) -> set[int]:
    """Decide which proposed mental tasks survive. Returns ``id()`` of removals.

    ``roles`` may include non-mental roles; they only mark which days hold real
    training. ``bucket_of`` groups offsets into the calendar weeks the athlete
    sees. ``relocate``, when given, moves a kept reflection onto a contact day of
    the same week (a reflection belongs after the sparring it reviews); without
    it, a reflection off a contact day is dropped. ``is_fixed`` marks roles an
    upstream owner already governed (the finished late-fight tail): they are
    always kept and count toward every allowance and spacing rule.
    """
    policy = mental_training_policy(athlete_model)
    contacts = {int(offset) for offset in contact_offsets if int(offset) > 0}
    roles = [role for role in roles if isinstance(role, dict)]
    fixed_check = is_fixed or (lambda _role: False)

    # Days that hold real training. Mental work attaches to these; it never
    # turns an otherwise empty day into a "session" day.
    training_offsets = set(contacts)
    entries: list[_Entry] = []
    for role in roles:
        offset = offset_of(role)
        if offset is None:
            continue
        category = mental_category(role)
        if category is None:
            training_offsets.add(int(offset))
            continue
        entries.append(
            _Entry(role, int(offset), bucket_of(role, int(offset)), category, bool(fixed_check(role)))
        )

    keep: list[_Entry] = [entry for entry in entries if entry.fixed]
    free = [entry for entry in entries if not entry.fixed]
    countdown_days = set(policy.countdown_visualization_days)

    def is_protocol(entry: _Entry) -> bool:
        return is_countdown_visualization(entry.role) and entry.offset in countdown_days

    # Visualise. Fight week: the countdown protocol only, on its policy days.
    keep.extend(
        entry
        for entry in free
        if entry.category == VISUALISE
        and entry.offset <= FIGHT_WEEK_LAST_OFFSET
        and is_protocol(entry)
    )
    by_bucket: dict[Any, list[_Entry]] = {}
    for entry in entries:
        if entry.category == VISUALISE and entry.offset > FIGHT_WEEK_LAST_OFFSET:
            by_bucket.setdefault(entry.bucket, []).append(entry)
    for bucket_entries in by_bucket.values():
        # The D-7 countdown rehearsal is protocol: always kept, and it uses
        # that week's allowance, as do already-governed fixed sessions.
        held = [entry for entry in bucket_entries if entry.fixed or is_protocol(entry)]
        keep.extend(entry for entry in held if not entry.fixed)
        candidates = [
            entry
            for entry in bucket_entries
            if entry not in held and entry.offset in training_offsets
        ]
        room = max(0, policy.visualisations_per_week - len(held))
        keep.extend(_spread_pick(candidates, room, (entry.offset for entry in held)))

    # Analyse: never in fight week, never on a day with no real training, and
    # one assignment every ``analyse_spacing_days``.
    fixed_analyse = [entry.offset for entry in entries if entry.fixed and entry.category == ANALYSE]
    analyse = [
        entry
        for entry in free
        if entry.category == ANALYSE
        and entry.offset > FIGHT_WEEK_LAST_OFFSET
        and entry.offset in training_offsets
    ]
    keep.extend(_pick_analyse(analyse, policy.analyse_spacing_days, contacts, fixed_analyse))

    # Reflect: attached to sparring, at most once a week, never in fight week.
    reflect_by_bucket: dict[Any, list[_Entry]] = {}
    for entry in entries:
        if entry.category == REFLECT and entry.offset > FIGHT_WEEK_LAST_OFFSET:
            reflect_by_bucket.setdefault(entry.bucket, []).append(entry)
    for bucket, bucket_entries in reflect_by_bucket.items():
        room = policy.reflections_per_week - sum(1 for entry in bucket_entries if entry.fixed)
        bucket_contacts = [
            offset
            for offset in contacts
            if offset > FIGHT_WEEK_LAST_OFFSET and bucket_of({}, offset) == bucket
        ]
        if room <= 0 or not bucket_contacts:
            continue
        for entry in sorted(
            (entry for entry in bucket_entries if not entry.fixed), key=lambda item: -item.offset
        )[:room]:
            if entry.offset not in bucket_contacts:
                if relocate is None:
                    continue
                target = min(bucket_contacts, key=lambda offset: (abs(offset - entry.offset), -offset))
                relocate(entry.role, target)
                entry.offset = target
            keep.append(entry)

    # One clear mental task per day: fixed and protocol work first, then the
    # rarer categories (a fortnightly tactical task beats a weekly rehearsal).
    precedence = {ANALYSE: 1, REFLECT: 2, VISUALISE: 3}

    def day_rank(entry: _Entry) -> tuple[int, int, int]:
        if entry.fixed:
            return (0, 0, 0)
        if is_countdown_visualization(entry.role):
            return (0, 1, 0)
        return (precedence[entry.category], _visualise_rank(entry)[0], 0)

    by_day: dict[int, list[_Entry]] = {}
    for entry in keep:
        by_day.setdefault(entry.offset, []).append(entry)
    final: list[_Entry] = []
    for day_entries in by_day.values():
        ranked = sorted(day_entries, key=day_rank)
        final.append(ranked[0])
        # Fixed roles belong to another owner and are never removed here.
        final.extend(entry for entry in ranked[1:] if entry.fixed)

    kept_ids = {id(entry.role) for entry in final}
    for entry in final:
        if not entry.fixed:
            _stamp(entry.role, entry.category, policy)
    return {id(entry.role) for entry in entries if id(entry.role) not in kept_ids}


def calendar_week_bucket(offset: int, fight_weekday_index: int | None) -> int:
    """Monday-based calendar week of D-``offset`` relative to fight week (0).

    Falls back to seven-day countdown segments when the fight weekday is
    unknown.
    """
    if fight_weekday_index is None:
        return -((offset + 6) // 7)
    return (fight_weekday_index - offset) // 7
