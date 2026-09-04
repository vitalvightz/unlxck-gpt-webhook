from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .priority_clarification_tags import derive_clarification_tags
from .tagging import normalize_tag

PRIMARY_GOAL_WEIGHT = 0.8
SECONDARY_GOAL_WEIGHT = 0.4

PRIMARY_WEAKNESS_WEIGHT = 0.9
SECONDARY_WEAKNESS_WEIGHT = 0.45

MAX_GOAL_PRIORITY_BONUS = 1.2
MAX_WEAKNESS_PRIORITY_BONUS = 1.35
COLLISION_INTENT_BONUS = 0.2

# Runtime intake normalization intentionally uses selection-oriented vocabulary
# such as ``reactive`` and ``explosive``. Coverage-aware low-cost support reasons
# about broader adaptation families instead. Keep that bridge inside this
# read-only projection so global tag semantics and canonical priority weights are
# left unchanged.
_SELECTED_PRIORITY_TARGET_ALIASES = {
    "reactive": "speed",
    "explosive": "power",
}


@dataclass(frozen=True)
class PriorityProfile:
    primary_goal: str
    secondary_goals: list[str]
    primary_weak_area: str
    secondary_weak_areas: list[str]
    all_goals: list[str]
    all_weak_areas: list[str]
    goal_weakness_collisions: list[str] = field(default_factory=list)
    primary_goal_weakness_collision: bool = False
    primary_collision_tag: str = ""


@dataclass(frozen=True)
class SelectedPriority:
    """One canonical athlete-selected target and its existing profile weight."""

    target: str
    label: str
    weight: float
    sources: tuple[str, ...]


def normalize_priority_values(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []

    raw_values: list[str]
    if isinstance(value, str):
        raw_values = value.split(",")
    else:
        raw_values = []
        for item in value:
            if item is not None:
                raw_values.extend(str(item).split(","))

    normalized: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        clean = raw.strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        normalized.append(clean)

    return normalized


def build_priority_profile(plan_input: Any) -> PriorityProfile:
    read = plan_input.get if isinstance(plan_input, dict) else lambda key, default=None: getattr(plan_input, key, default)
    all_goals = normalize_priority_values(read("key_goals"))
    all_weak_areas = normalize_priority_values(read("weak_areas", read("weaknesses")))

    primary_goal = str(read("primary_goal", "") or "").strip()
    if not primary_goal or primary_goal not in all_goals:
        primary_goal = all_goals[0] if all_goals else ""

    primary_weak_area = str(read("primary_weak_area", "") or "").strip()
    if not primary_weak_area or primary_weak_area not in all_weak_areas:
        primary_weak_area = all_weak_areas[0] if all_weak_areas else ""

    normalized_weak_area_set = {
        normalized
        for weak_area in all_weak_areas
        if (normalized := _normalized_priority_tag(weak_area))
    }
    goal_weakness_collisions = [
        goal
        for goal in all_goals
        if _normalized_priority_tag(goal) in normalized_weak_area_set
    ]
    primary_goal_weakness_collision = bool(
        primary_goal
        and primary_weak_area
        and _normalized_priority_tag(primary_goal) == _normalized_priority_tag(primary_weak_area)
    )

    return PriorityProfile(
        primary_goal=primary_goal,
        secondary_goals=[goal for goal in all_goals if goal != primary_goal],
        primary_weak_area=primary_weak_area,
        secondary_weak_areas=[weakness for weakness in all_weak_areas if weakness != primary_weak_area],
        all_goals=all_goals,
        all_weak_areas=all_weak_areas,
        goal_weakness_collisions=goal_weakness_collisions,
        primary_goal_weakness_collision=primary_goal_weakness_collision,
        primary_collision_tag=primary_goal if primary_goal_weakness_collision else "",
    )


def _normalized_priority_tag(tag: str) -> str:
    return normalize_tag(str(tag or "")) or ""


def goal_priority_weight(goal: str, profile: PriorityProfile) -> float:
    if goal == profile.primary_goal:
        return PRIMARY_GOAL_WEIGHT
    if goal in profile.secondary_goals:
        return SECONDARY_GOAL_WEIGHT
    return 0.0


def weakness_priority_weight(weakness: str, profile: PriorityProfile) -> float:
    if weakness == profile.primary_weak_area:
        return PRIMARY_WEAKNESS_WEIGHT
    if weakness in profile.secondary_weak_areas:
        return SECONDARY_WEAKNESS_WEIGHT
    return 0.0


def selected_priority_targets(plan_input: Any) -> list[SelectedPriority]:
    """Return selected targets ordered by the canonical profile weights.

    Normalized duplicates (for example a target selected as both a goal and a
    weakness) are represented once at their highest existing canonical weight.
    Runtime selection vocabulary is projected onto broader adaptation families
    only here; the canonical priority profile itself remains unchanged. Consumers
    must not recreate the primary/secondary weighting doctrine locally.
    """

    profile = plan_input if isinstance(plan_input, PriorityProfile) else build_priority_profile(plan_input)
    selections: list[tuple[str, str, float]] = []
    if profile.primary_weak_area:
        selections.append(
            (
                "primary_weakness",
                profile.primary_weak_area,
                weakness_priority_weight(profile.primary_weak_area, profile),
            )
        )
    if profile.primary_goal:
        selections.append(
            (
                "primary_goal",
                profile.primary_goal,
                goal_priority_weight(profile.primary_goal, profile),
            )
        )
    selections.extend(
        ("secondary_weakness", weakness, weakness_priority_weight(weakness, profile))
        for weakness in profile.secondary_weak_areas
    )
    selections.extend(
        ("secondary_goal", goal, goal_priority_weight(goal, profile))
        for goal in profile.secondary_goals
    )

    merged: dict[str, SelectedPriority] = {}
    order: list[str] = []
    for source, label, weight in selections:
        normalized_target = _normalized_priority_tag(label)
        target = _SELECTED_PRIORITY_TARGET_ALIASES.get(
            normalized_target,
            normalized_target,
        )
        if not target or weight <= 0:
            continue
        current = merged.get(target)
        if current is None:
            order.append(target)
            merged[target] = SelectedPriority(
                target=target,
                label=label,
                weight=weight,
                sources=(source,),
            )
            continue
        merged[target] = SelectedPriority(
            target=target,
            label=current.label,
            weight=max(current.weight, weight),
            sources=(*current.sources, source),
        )

    order_index = {target: index for index, target in enumerate(order)}
    return sorted(
        merged.values(),
        key=lambda item: (-item.weight, order_index[item.target]),
    )


def is_priority_collision_tag(tag: str, profile: PriorityProfile) -> bool:
    normalized = _normalized_priority_tag(tag)
    return bool(
        normalized
        and normalized
        in {
            _normalized_priority_tag(collision)
            for collision in profile.goal_weakness_collisions
        }
    )


def collision_safe_priority_bonus_for_tag(tag: str, profile: PriorityProfile) -> float:
    goal_weight = goal_priority_weight(tag, profile)
    weakness_weight = weakness_priority_weight(tag, profile)
    if not is_priority_collision_tag(tag, profile):
        return goal_weight + weakness_weight

    return max(goal_weight, weakness_weight) + COLLISION_INTENT_BONUS


def total_collision_safe_priority_bonus(
    goal_tags: Iterable[str],
    weakness_tags: Iterable[str],
    profile: PriorityProfile,
    *,
    max_bonus: float | None = None,
) -> float:
    unique_tags = list(dict.fromkeys([*goal_tags, *weakness_tags]))
    total = sum(collision_safe_priority_bonus_for_tag(tag, profile) for tag in unique_tags)
    if max_bonus is not None:
        return min(total, max_bonus)
    return total


def total_strength_collision_safe_priority_bonus(
    goal_tags: Iterable[str],
    weakness_tags: Iterable[str],
    profile: PriorityProfile,
) -> float:
    unique_tags = list(dict.fromkeys([*goal_tags, *weakness_tags]))
    if not any(is_priority_collision_tag(tag, profile) for tag in unique_tags):
        return total_goal_priority_bonus(goal_tags, profile) + total_weakness_priority_bonus(
            weakness_tags,
            profile,
        )

    return total_collision_safe_priority_bonus(
        goal_tags,
        weakness_tags,
        profile,
        max_bonus=MAX_GOAL_PRIORITY_BONUS + MAX_WEAKNESS_PRIORITY_BONUS,
    )


def total_goal_priority_bonus(tags: Iterable[str], profile: PriorityProfile) -> float:
    unique_tags = list(dict.fromkeys(tags))
    total = sum(goal_priority_weight(tag, profile) for tag in unique_tags)
    return min(total, MAX_GOAL_PRIORITY_BONUS)


def total_weakness_priority_bonus(tags: Iterable[str], profile: PriorityProfile) -> float:
    unique_tags = list(dict.fromkeys(tags))
    total = sum(weakness_priority_weight(tag, profile) for tag in unique_tags)
    return min(total, MAX_WEAKNESS_PRIORITY_BONUS)


def describe_priority_focus(
    profile: PriorityProfile,
    *,
    collision_detail: str = "",
    collision_tags: list[str] | None = None,
    collision_details: list[dict[str, str]] | None = None,
) -> dict[str, str | list[str] | list[dict[str, str]]]:
    resolved_collisions = list(profile.goal_weakness_collisions)
    if collision_tags:
        normalized_profile_collisions = {
            _normalized_priority_tag(tag)
            for tag in profile.goal_weakness_collisions
            if _normalized_priority_tag(tag)
        }
        for tag in collision_tags:
            clean_tag = str(tag or "").strip()
            if not clean_tag:
                continue
            normalized = _normalized_priority_tag(clean_tag)
            if normalized and normalized in normalized_profile_collisions and clean_tag not in resolved_collisions:
                resolved_collisions.append(clean_tag)

    sanitized_collision_details: list[dict[str, str]] = []
    if isinstance(collision_details, list):
        for entry in collision_details:
            if not isinstance(entry, dict):
                continue
            tag = str(entry.get("tag", "")).strip()
            label = str(entry.get("label", "")).strip()
            detail = str(entry.get("detail", "")).strip()
            if tag or detail:
                sanitized_collision_details.append({"tag": tag, "label": label, "detail": detail})

    collision_detail = str(collision_detail or "").strip()
    if not collision_detail:
        for entry in sanitized_collision_details:
            candidate_detail = str(entry.get("detail", "")).strip()
            if candidate_detail:
                collision_detail = candidate_detail
                break
    has_primary_collision = bool(
        profile.primary_goal
        and profile.primary_weak_area
        and _normalized_priority_tag(profile.primary_goal) == _normalized_priority_tag(profile.primary_weak_area)
    )

    if has_primary_collision:
        main_focus = f"Build {profile.primary_goal} while clarifying the {profile.primary_weak_area} limiter."
        focus_instruction = (
            f"{profile.primary_goal} is both the goal and weak-area signal. Treat this as a priority collision: "
            "build it without double-loading it blindly."
        )
        if collision_detail:
            focus_instruction += " Use the clarification detail to bias toward repeatable/usable output."
    elif profile.primary_goal and profile.primary_weak_area:
        main_focus = f"Build {profile.primary_goal} while managing {profile.primary_weak_area}."
        focus_instruction = (
            f"Prioritise {profile.primary_goal} as the main adaptation while using "
            f"{profile.primary_weak_area} as the main limiter. Keep secondary goals supportive, not dominant."
        )
    elif profile.primary_goal:
        main_focus = f"Build {profile.primary_goal}."
        focus_instruction = f"Prioritise {profile.primary_goal} as the main adaptation."
    elif profile.primary_weak_area:
        main_focus = f"Manage {profile.primary_weak_area}."
        focus_instruction = f"Prioritise {profile.primary_weak_area} as the main limiter."
    else:
        main_focus = ""
        focus_instruction = ""

    derived_clarification_tags = derive_clarification_tags(sanitized_collision_details)

    return {
        "main_focus": main_focus,
        "primary_goal": profile.primary_goal,
        "primary_weak_area": profile.primary_weak_area,
        "secondary_goals": profile.secondary_goals,
        "secondary_weak_areas": profile.secondary_weak_areas,
        "goal_weakness_collisions": resolved_collisions,
        "collision_detail": collision_detail,
        "collision_details": sanitized_collision_details,
        "derived_clarification_tags": derived_clarification_tags,
        "focus_instruction": focus_instruction,
    }
