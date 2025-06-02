# conditioning.py
from typing import List
from training_context import build_training_context
import re

def adjust_for_fatigue(fatigue: str) -> str:
    if fatigue == "high":
        return "\n⚠️ High fatigue → cut glycolytic sessions by 30%, extend rest intervals by 20%"
    elif fatigue == "moderate":
        return "\n⚠️ Moderate fatigue → reduce one interval from highest-load session"
    return ""

def adjust_for_injury(injuries: List[str]) -> List[str]:
    adjustments = []
    for injury in injuries:
        if "hamstring" in injury:
            adjustments.append("⚠️ Hamstring → avoid max sprints, use sled drag or bike sprints")
        elif "ankle" in injury:
            adjustments.append("⚠️ Ankle → remove lateral hops or bounding")
        elif "knee" in injury:
            adjustments.append("⚠️ Knee → no deep squatting, use bike over runs")
    return adjustments

def fight_format_notes(fight_format: str) -> str:
    rounds = 3
    if fight_format:
        match = re.search(r"(\d+)[xX]", fight_format)
        if match:
            rounds = int(match.group(1))

    if rounds >= 5:
        return "\n• Fight format: 5 rounds → increased aerobic + glycolytic load"
    elif rounds == 3:
        return "\n• Fight format: 3 rounds → alactic + power emphasis"
    return ""

def build_energy_targets(phase: str) -> str:
    if phase == "GPP":
        return """
• Energy System Targets:
  - Aerobic base (60–70% HR): 2x 30-min steady-state (nasal breathing) + 1x zone 2 circuit
  - ATP-PCr: 2x10s sprints (sled/bike), 1:5 rest ratio

• Psychological Anchor: “Earn your base”
• HR cap: 150 bpm
• Notes: Emphasize nasal breathing and aerobic foundation
"""
    elif phase == "SPP":
        return """
• Energy System Targets:
  - ATP-PCr: Sprint 10s x10, 1:6 rest
  - Glycolytic: 2x/week 20s–45s bursts (EMOM pads, intervals)

• Psychological Anchor: “Fight while tired”
• Notes: Combine skill & fatigue. Pad + sprawl EMOMs encouraged
"""
    elif phase == "TAPER":
        return """
• Energy System Targets:
  - Maintain sharpness: 1x anaerobic reaction (<15min)
  - Aerobic flush: 1x 20–25min nasal session

• Psychological Anchor: “Nothing left to prove”
• Notes: Limit HR spikes post-Wed. Use eye-tracking, flywheel, ball drills
"""
    return "\n• Unknown phase. Default to aerobic + light intervals."

def generate_conditioning_block(training_context: dict) -> str:
    phase = training_context["phase"]
    fatigue = training_context["fatigue"]
    injuries = training_context["injuries"]
    fight_format = training_context.get("fight_format")
    weight_cut_pct = training_context.get("weight_cut_pct", 0.0)
    weight_cut_risk = training_context.get("weight_cut_risk", False)

    output = ["\n📦 **CONDITIONING MODULE**"]
    output.append(f"**Phase:** {phase}")

    # Fight format adjustment
    output.append(fight_format_notes(fight_format))

    # Weight cut caution
    if weight_cut_risk:
        output.append(f"⚠️ Weight Cut Risk: {weight_cut_pct}% above limit → prioritize low-impact conditioning")

    # Phase-driven structure
    output.append(build_energy_targets(phase))

    # Fatigue logic
    output.append(adjust_for_fatigue(fatigue))

    # Injury-specific edits
    injury_notes = adjust_for_injury(injuries)
    if injury_notes:
        output.extend(injury_notes)

    return "\n".join(output)