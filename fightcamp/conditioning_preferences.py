"""Shared conditioning preferences; eligibility and dose owners remain authoritative."""
from .sports import normalize_sport

STRIKING_SPORTS = frozenset({"boxing", "kickboxing", "muay_thai", "mma"})
_BAG_IMPACT_SENSITIVITY = {"shoulder", "pec", "chest", "rib", "elbow", "wrist", "hand"}


def striking_heavy_bag_preference(
    drill: dict, *, phase: str, system: str, fatigue: str,
    days_until_fight: int | None, equipment_access_set: set[str],
    injuries: list[str], hard_sparring_days: list[str], sport: str = "boxing",
) -> float:
    """Rank already eligible bag work for each striking sport's own candidates.

    Sport identity, injury filtering, energy system, dose and contact scheduling
    stay with their existing owners. This never permits another sport's drills
    or adds a hard session. Grappling-only sports receive no striking preference.
    """
    if normalize_sport(sport) not in STRIKING_SPORTS:
        return 0.0
    if "heavy_bag" not in equipment_access_set or "heavy_bag" not in drill.get("equipment", []):
        return 0.0
    if phase.upper() == "TAPER" or (isinstance(days_until_fight, int) and days_until_fight <= 13):
        return 0.0
    if fatigue == "high" or len(set(hard_sparring_days)) >= 3:
        return 0.0
    # Hard sparring supplies the demanding boxing exposure; aerobic touches remain legal.
    if len(set(hard_sparring_days)) >= 2 and (
        system != "aerobic" or (drill.get("rpe") or drill.get("rpe_max") or 0) > 6
    ):
        return 0.0
    if any(area in " ".join(str(item).lower() for item in injuries) for area in _BAG_IMPACT_SENSITIVITY):
        return 0.0
    if system == "aerobic":
        return 1.0 if phase.upper() == "SPP" and fatigue == "low" else 0.35
    if system == "alactic":
        return 2.5 if fatigue == "low" else 1.0
    if system == "glycolytic":
        return (3.0 if phase.upper() == "SPP" else 2.0) * (0.5 if fatigue == "moderate" else 1.0)
    return 0.0
