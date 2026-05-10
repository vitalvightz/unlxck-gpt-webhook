from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

PRIMARY_GOAL_WEIGHT = 0.8
SECONDARY_GOAL_WEIGHT = 0.4

PRIMARY_WEAKNESS_WEIGHT = 0.9
SECONDARY_WEAKNESS_WEIGHT = 0.45

MAX_GOAL_PRIORITY_BONUS = 1.2
MAX_WEAKNESS_PRIORITY_BONUS = 1.35


@dataclass(frozen=True)
class PriorityProfile:
    primary_goal: str
    secondary_goals: list[str]
    primary_weak_area: str
    secondary_weak_areas: list[str]
    all_goals: list[str]
    all_weak_areas: list[str]


def normalize_priority_values(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []

    raw_values: list[str]
    if isinstance(value, str):
        raw_values = value.split(",")
    else:
        raw_values = [str(item) for item in value]

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
    all_goals = normalize_priority_values(getattr(plan_input, "key_goals", None))
    all_weak_areas = normalize_priority_values(getattr(plan_input, "weak_areas", None))

    primary_goal = str(getattr(plan_input, "primary_goal", "") or "").strip()
    if not primary_goal or primary_goal not in all_goals:
        primary_goal = all_goals[0] if all_goals else ""

    primary_weak_area = str(getattr(plan_input, "primary_weak_area", "") or "").strip()
    if not primary_weak_area or primary_weak_area not in all_weak_areas:
        primary_weak_area = all_weak_areas[0] if all_weak_areas else ""

    return PriorityProfile(
        primary_goal=primary_goal,
        secondary_goals=[goal for goal in all_goals if goal != primary_goal],
        primary_weak_area=primary_weak_area,
        secondary_weak_areas=[weakness for weakness in all_weak_areas if weakness != primary_weak_area],
        all_goals=all_goals,
        all_weak_areas=all_weak_areas,
    )


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


def total_goal_priority_bonus(tags: Iterable[str], profile: PriorityProfile) -> float:
    unique_tags = list(dict.fromkeys(tags))
    total = sum(goal_priority_weight(tag, profile) for tag in unique_tags)
    return min(total, MAX_GOAL_PRIORITY_BONUS)


def total_weakness_priority_bonus(tags: Iterable[str], profile: PriorityProfile) -> float:
    unique_tags = list(dict.fromkeys(tags))
    total = sum(weakness_priority_weight(tag, profile) for tag in unique_tags)
    return min(total, MAX_WEAKNESS_PRIORITY_BONUS)


def describe_priority_focus(profile: PriorityProfile) -> dict[str, str | list[str]]:
    if profile.primary_goal and profile.primary_weak_area:
        main_focus = f"Build {profile.primary_goal} while managing {profile.primary_weak_area}."
    elif profile.primary_goal:
        main_focus = f"Build {profile.primary_goal}."
    elif profile.primary_weak_area:
        main_focus = f"Manage {profile.primary_weak_area}."
    else:
        main_focus = ""

    return {
        "main_focus": main_focus,
        "primary_goal": profile.primary_goal,
        "primary_weak_area": profile.primary_weak_area,
        "secondary_goals": profile.secondary_goals,
        "secondary_weak_areas": profile.secondary_weak_areas,
    }
