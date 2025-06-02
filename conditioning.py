# conditioning.py

from typing import List, Dict
import re

def adjust_for_fatigue(fatigue: str) -> str:
    if fatigue == "high":
        return "⚠️ High fatigue → cut glycolytic sessions by 30%, extend rest intervals by 20%"
    elif fatigue == "moderate":
        return "⚠️ Moderate fatigue → reduce one interval from highest-load session"
    return ""

def adjust_for_injury(injuries: List[str]) -> List[str]:
    notes = []
    for injury in injuries:
        i = injury.lower()
        if "hamstring" in i:
            notes.append("⚠️ Hamstring → avoid max sprints, use sled drag or bike sprints")
        elif "ankle" in i:
            notes.append("⚠️ Ankle → remove lateral hops or bounding")
        elif "knee" in i:
            notes.append("⚠️ Knee → avoid deep squats, use bike instead of runs")
    return notes

def fight_format_notes(fight_format: str) -> str:
    rounds = 3
    if fight_format:
        match = re.search(r"(\d+)[xX]", fight_format)
        if match:
            rounds = int(match.group(1))
    if rounds >= 5:
        return "• Fight format: 5 rounds → increased aerobic + glycolytic load"
    elif rounds == 3:
        return "• Fight format: 3 rounds → alactic + power emphasis"
    return "• Unknown format → defaulting to mixed load"

def build_energy_targets(phase: str) -> str:
    if phase == "GPP":
        return """• Energy Targets:
  - Aerobic base (60–70% HR): 2x 30min steady-state (nasal) + 1x zone 2 circuit
  - ATP-PCr: 2x10s sprints, 1:5 rest
• Anchor: “Earn your base”
• HR cap: 150 bpm"""
    elif phase == "SPP":
        return """• Energy Targets:
  - ATP-PCr: 10s x10 sprints, 1:6 rest
  - Glycolytic: 2x/wk 20–45s bursts (EMOM pads)
• Anchor: “Fight while tired”
• Notes: Pair skill with fatigue (e.g., pads + sprawls)"""
    elif phase == "TAPER":
        return """• Energy Targets:
  - Sharpness: 1x short anaerobic (<15min)
  - Aerobic flush: 1x 20min nasal session
• Anchor: “Nothing left to prove”
• Notes: Limit HR spikes, use eye-tracking/flywheel"""
    return "• Unknown phase → use light aerobic and low CNS drills"

def assign_conditioning_days(all_days: List[str], strength_days: List[str], required: int) -> List[str]:
    return [d for d in all_days if d not in strength_days][:required]

def generate_conditioning_block(training_context: Dict, strength_tags_by_day: Dict[str, List[str]]) -> Dict:
    phase = training_context["phase"]
    fatigue = training_context["fatigue"]
    injuries = training_context["injuries"]
    fight_format = training_context.get("fight_format", "")
    weight_cut_risk = training_context.get("weight_cut_risk", False)
    weight_cut_pct = training_context.get("weight_cut_pct", 0.0)
    all_training_days = training_context["training_days"]
    required_sessions = training_context["training_split"]["conditioning"]

    strength_days = list(strength_tags_by_day.keys())
    conditioning_days = assign_conditioning_days(all_training_days, strength_days, required_sessions)

    output = [
        "\n🏃‍♂️ **CONDITIONING MODULE**",
        f"**Phase:** {phase}",
        f"**Assigned Days:** {', '.join(conditioning_days)}",
        fight_format_notes(fight_format),
        build_energy_targets(phase)
    ]

    if weight_cut_risk:
        output.append(f"⚠️ Weight Cut: {weight_cut_pct}% over → use low-impact methods")

    fatigue_note = adjust_for_fatigue(fatigue)
    if fatigue_note:
        output.append(fatigue_note)

    injury_notes = adjust_for_injury(injuries)
    output.extend(injury_notes)

    return {
        "block": "\n".join(output),
        "days_used": conditioning_days
    }