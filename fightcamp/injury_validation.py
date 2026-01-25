from __future__ import annotations

from .conditioning import generate_conditioning_block
from .injury_filtering import injury_match_details, match_forbidden
from .injury_formatting import parse_injury_entry
from .strength import generate_strength_block


def _find_keyword_violations(names: list[str], keywords: list[str]) -> list[str]:
    violations: list[str] = []
    for name in names:
        if match_forbidden(name, keywords):
            violations.append(name)
    return violations


def run_injury_self_checks() -> None:
    violations: list[str] = []

    base_flags = {
        "phase": "GPP",
        "fatigue": "low",
        "equipment": ["bodyweight", "bands", "medicine_ball"],
        "fight_format": "mma",
        "style_tactical": ["brawler"],
        "style_technical": ["mma"],
        "training_days": ["Mon", "Wed", "Fri"],
        "training_frequency": 3,
        "prev_exercises": [],
        "recent_exercises": [],
        "key_goals": ["strength"],
        "weaknesses": [],
        "status": "amateur",
    }

    shoulder_flags = {**base_flags, "injuries": ["shoulder"]}
    shoulder_strength = generate_strength_block(flags=shoulder_flags)
    shoulder_strength_names = [ex.get("name", "") for ex in shoulder_strength.get("exercises", [])]
    shoulder_violations = _find_keyword_violations(
        shoulder_strength_names,
        [
            "bench press",
            "overhead press",
            "push press",
            "strict press",
            "military press",
            "ring dip",
            "bench dip",
            "parallel bar dip",
            "bar dip",
        ],
    )
    if shoulder_violations:
        violations.append(
            "Shoulder injury violations in strength: " + ", ".join(shoulder_violations)
        )

    achilles_flags = {**base_flags, "injuries": ["achilles"]}
    _, achilles_conditioning_names, _, _, _ = generate_conditioning_block(achilles_flags)
    achilles_violations = _find_keyword_violations(
        achilles_conditioning_names, ["depth jump", "drop jump", "max sprint"]
    )
    if achilles_violations:
        violations.append(
            "Achilles injury violations in conditioning: "
            + ", ".join(achilles_violations)
        )

    head_entry = parse_injury_entry("left head concussion")
    head_location = head_entry.get("canonical_location") if head_entry else None
    if not head_location:
        violations.append("Head injury parsing failed to return canonical_location.")
    else:
        head_flags = {**base_flags, "injuries": [head_location]}
        head_strength = generate_strength_block(flags=head_flags)
        head_strength_names = [ex.get("name", "") for ex in head_strength.get("exercises", [])]
        head_violations = _find_keyword_violations(
            head_strength_names,
            ["hard sparring", "gnp"],
        )
        if head_violations:
            violations.append(
                "Head injury violations in strength: " + ", ".join(head_violations)
            )

        head_filter_checks = [
            {"name": "hard sparring rounds"},
            {"name": "gnp bag work"},
        ]
        for item in head_filter_checks:
            reasons = injury_match_details(item, [head_location], risk_levels=("exclude",))
            if not reasons:
                violations.append(
                    f"Head injury rules failed to flag: {item['name']}"
                )

    if violations:
        raise SystemExit("\n".join(violations))


if __name__ == "__main__":
    run_injury_self_checks()
