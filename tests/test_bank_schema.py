from fightcamp.bank_schema import KNOWN_SYSTEMS, SYSTEM_ALIASES


def test_hypertrophy_alias_maps_to_known_system() -> None:
    mapped = SYSTEM_ALIASES.get("hypertrophy")
    assert mapped is not None
    assert mapped in KNOWN_SYSTEMS
    assert mapped == "glycolytic"
