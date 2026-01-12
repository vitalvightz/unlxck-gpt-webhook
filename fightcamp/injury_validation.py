from __future__ import annotations

from .conditioning import generate_conditioning_block
from .injury_filtering import match_forbidden
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

    if violations:
        raise SystemExit("\n".join(violations))


if __name__ == "__main__":
    run_injury_self_checks()
