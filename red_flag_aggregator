def aggregate_flags_and_advice(module_outputs: dict, flags: dict) -> str:
    """
    Combine risk flags and advisory notes from all modules into a unified advisory string.
    Args:
        module_outputs: dict of {module_name: module_output_string}
        flags: dict of all current flags

    Returns:
        str: Cleaned, combined advisory block.
    """

    advisory_lines = []

    # Priority fatigue advice (from fatigue flag)
    fatigue = flags.get("fatigue", "low")
    if fatigue == "high":
        advisory_lines.append("⚠️ High Fatigue Detected: Prioritize rest, reduce volume, and monitor mood closely.")
    elif fatigue == "moderate":
        advisory_lines.append("⚠️ Moderate Fatigue: Slightly reduce load, ensure quality recovery.")

    # Weight cut risk advice
    if flags.get("weight_cut_risk"):
        cut_pct = flags.get("weight_cut_pct", "unknown")
        advisory_lines.append(
            f"⚠️ Weight Cut Risk ({cut_pct}%): Follow strict hydration, refeed, and taper protocols."
        )

    # Age related advice
    if flags.get("age_risk"):
        advisory_lines.append("⚠️ Age-related risk: Emphasize recovery modalities like float tanks and collagen supplementation.")

    # Taper week advice
    if flags.get("taper_week"):
        advisory_lines.append("⚠️ Taper Week: Avoid high intensity or soreness-inducing activities after midweek.")

    # Injuries summary
    injuries = flags.get("injuries", [])
    if injuries:
        injury_summary = f"⚠️ Injuries Detected: {', '.join(injuries)}. Modify training accordingly."
        advisory_lines.append(injury_summary)

    # Optionally include any standout advice from module outputs to unify redundant notes
    # Here you could parse module outputs to extract key lines if needed
    # For now, assume module outputs are detailed training blocks, not just warnings

    # Join all advisories
    return "\n".join(advisory_lines)