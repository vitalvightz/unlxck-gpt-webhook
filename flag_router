def flag_router(age: int, fatigue_score: int, phase: str, weight: float, weight_class: str, injuries: str = None):
    """
    Centralized flag aggregator for downstream module use.
    Returns a dictionary of flags.
    """
    flags = {}

    # Fatigue classification
    if fatigue_score >= 8:
        flags["fatigue"] = "high"
    elif 5 <= fatigue_score <= 7:
        flags["fatigue"] = "moderate"
    else:
        flags["fatigue"] = "low"

    # Weight cut logic
    weight_class_limits = {
        "Flyweight": 56.7, "Bantamweight": 61.2, "Featherweight": 65.8,
        "Lightweight": 70.3, "Welterweight": 77.1, "Middleweight": 83.9,
        "Light Heavyweight": 93.0, "Heavyweight": 120.2
    }
    class_limit = weight_class_limits.get(weight_class)
    if class_limit:
        cut_pct = ((weight - class_limit) / weight) * 100
        if cut_pct > 6:
            flags["weight_cut_risk"] = True
            flags["weight_cut_pct"] = round(cut_pct, 1)

    # Age flag
    if age >= 30:
        flags["age_risk"] = True

    # Phase detection
    if phase.strip().upper() == "TAPER":
        flags["taper_week"] = True

    # Injury parsing
    if injuries:
        flags["injuries"] = [i.strip().lower() for i in injuries.split(",")]
    else:
        flags["injuries"] = []

    return flags