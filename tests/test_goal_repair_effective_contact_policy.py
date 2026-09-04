from __future__ import annotations

from fightcamp.goal_repair_effective_contact_policy import clear_stale_two_hard_spar_authority


def _brief(*, effective_days, compression_codes, suppressed_codes=None, include_effective=True):
    week = {
        "week_index": 2,
        "intentional_compression": {
            "active": True,
            "reason_codes": list(compression_codes),
            "reason": "compressed",
            "summary": "compressed summary",
        },
        "suppressed_roles": [
            {
                "role_key": "primary_strength_day",
                "compression_reason_codes": list(suppressed_codes or compression_codes),
                "governance": {"hard_suppression_reasons": []},
            }
        ],
    }
    if include_effective:
        week["effective_hard_sparring_days"] = list(effective_days)
    return {"weekly_role_map": {"weeks": [week]}}


def test_true_two_effective_hard_days_keep_two_hard_spar_authority():
    brief = _brief(
        effective_days=["Tuesday", "Friday"],
        compression_codes=["two_hard_spar_days"],
    )

    clear_stale_two_hard_spar_authority(brief)

    week = brief["weekly_role_map"]["weeks"][0]
    assert week["intentional_compression"]["active"] is True
    assert week["intentional_compression"]["reason_codes"] == ["two_hard_spar_days"]
    assert week["suppressed_roles"][0]["compression_reason_codes"] == ["two_hard_spar_days"]


def test_one_effective_hard_day_clears_stale_two_hard_spar_authority():
    brief = _brief(
        effective_days=["Friday"],
        compression_codes=["two_hard_spar_days"],
    )

    clear_stale_two_hard_spar_authority(brief)

    week = brief["weekly_role_map"]["weeks"][0]
    assert week["intentional_compression"]["active"] is False
    assert week["intentional_compression"]["reason_codes"] == []
    assert week["intentional_compression"]["reason"] == ""
    assert week["intentional_compression"]["summary"] == ""
    assert week["suppressed_roles"][0]["compression_reason_codes"] == []


def test_zero_effective_hard_days_clears_stale_two_hard_spar_authority():
    brief = _brief(
        effective_days=[],
        compression_codes=["two_hard_spar_days"],
    )

    clear_stale_two_hard_spar_authority(brief)

    week = brief["weekly_role_map"]["weeks"][0]
    assert week["intentional_compression"]["active"] is False
    assert week["intentional_compression"]["reason_codes"] == []
    assert week["suppressed_roles"][0]["compression_reason_codes"] == []


def test_other_live_compression_reasons_remain_authoritative():
    brief = _brief(
        effective_days=["Friday"],
        compression_codes=["high_fatigue", "two_hard_spar_days"],
        suppressed_codes=["high_fatigue", "two_hard_spar_days"],
    )

    clear_stale_two_hard_spar_authority(brief)

    week = brief["weekly_role_map"]["weeks"][0]
    assert week["intentional_compression"]["active"] is True
    assert week["intentional_compression"]["reason_codes"] == ["high_fatigue"]
    assert week["suppressed_roles"][0]["compression_reason_codes"] == ["high_fatigue"]


def test_unresolved_effective_contact_keeps_declared_day_fail_safe_authority():
    brief = _brief(
        effective_days=[],
        compression_codes=["two_hard_spar_days"],
        include_effective=False,
    )

    clear_stale_two_hard_spar_authority(brief)

    week = brief["weekly_role_map"]["weeks"][0]
    assert week["intentional_compression"]["active"] is True
    assert week["intentional_compression"]["reason_codes"] == ["two_hard_spar_days"]
    assert week["suppressed_roles"][0]["compression_reason_codes"] == ["two_hard_spar_days"]
