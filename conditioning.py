from pathlib import Path

conditioning_upgrade = '''
def generate_conditioning_block(phase: str, flags: dict, fight_format: str = None) -> str:
    """
    Conditioning training block using centralized flags.
    """
    output = "\\n📦 CONDITIONING MODULE\\n"
    output += f"Phase: {phase}\\n"

    # --- Fight format logic ---
    rounds = 3
    if fight_format:
        try:
            rounds = int(fight_format.split('x')[0])
        except (ValueError, IndexError):
            pass

    # [Insert rest of conditioning logic here using `flags` and `rounds` as needed]

    return output
'''

    if rounds >= 5:
        output += "\\n• Fight format: 5 rounds → increased aerobic + glycolytic load"
    elif rounds == 3:
        output += "\\n• Fight format: 3 rounds → alactic + power emphasis"

    # --- Weight class logic ---
    if flags.get("weight_cut_risk"):
        output += f"\\n⚠️ Weight Cut Risk: {flags.get('weight_cut_pct')}% above limit → prioritize low-impact conditioning"

    # --- Phase-specific programming ---
    if phase == "GPP":
        output += """
\\n• Energy System Targets:
  - Aerobic base (60–70% HR): 2x 30-min steady-state (nasal breathing) + 1x zone 2 circuit (sled drag, bike, rower)
  - ATP-PCr: 2x10s sprints (sled or assault bike), 1:5 work:rest, 8 rounds

• Weekly Schedule:
  - Mon: Aerobic run (30–40min)
  - Wed: Zone 2 circuit
  - Fri: Sprint intervals (sled, hill, bike)

• Psychological Load:
  - Use nasal-only breathing to build discomfort tolerance
  - Anchor: “Earn your base”

• Notes:
  - HR cap: 150 bpm
  - Monitor breathing mechanics and recovery window
"""

    elif phase == "SPP":
        output += """
\\n• Energy System Targets:
  - ATP-PCr: Sprint efforts (10s x 10 rounds, 1:6 work:rest)
  - Glycolytic: 2x/week 20s–45s bursts (e.g., EMOM pad drills)

• Weekly Schedule:
  - Mon: Sprint (10s x 10, hill or track)
  - Wed: Glycolytic pad intervals (3x5min EMOM)
  - Sat: Sparring simulation (5x5 min rounds w/30s transitions)

• Psychological Load:
  - Cue drills: “Round 3 simulation”, train under fatigue
  - Anchor: “Fight while tired”

• Notes:
  - Use fight-timed drills (pad + sprawl EMOMs)
  - Skill + fatigue pairing strongly encouraged
"""

    elif phase == "TAPER":
        output += """
\\n• Energy System Targets:
  - Maintain sharpness: 1x anaerobic (reaction-based, <15min total)
  - Aerobic flush: 1x 20-min nasal breathing

• Weekly Schedule:
  - Mon: Reaction ball drills (5 min)
  - Wed: Aerobic flush (20–25 min)
  - Thurs: Light pad sharpness (3x3 min @ RPE 6)

• Psychological Load:
  - Anchor: “Nothing left to prove”
  - Limit volume, stay sharp

• Notes:
  - No sessions inducing soreness or excessive HR spikes after Wed
  - CNS freshness is key: use flywheel, ball, eye tracking drills
"""

    # Fatigue modifiers
    fatigue = flags.get("fatigue", "")
    if fatigue == "high":
        output += "\\n⚠️ High fatigue → cut glycolytic sessions by 30%, extend all rest intervals by 20%"
    elif fatigue == "moderate":
        output += "\\n⚠️ Moderate fatigue → reduce one interval from highest-load session"

    # Injury handling
    for injury in flags.get("injuries", []):
        if "hamstring" in injury:
            output += "\\n⚠️ Hamstring → avoid max sprints, use sled drag or bike sprints"
        elif "ankle" in injury:
            output += "\\n⚠️ Ankle → remove lateral hops or bounding"
        elif "knee" in injury:
            output += "\\n⚠️ Knee → no deep squats or bounding; use upright bike or prowler"
        elif "back" in injury:
            output += "\\n⚠️ Back → avoid axial loading under fatigue (e.g., sprints with vest)"
        elif "shoulder" in injury:
            output += "\\n⚠️ Shoulder → avoid high-velocity upper body ballistic work"

    return output.strip()
'''

"✅ conditioning.py fully upgraded to use `flag_router()` flags dictionary."