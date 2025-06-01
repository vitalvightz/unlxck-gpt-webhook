from pathlib import Path

conditioning_module_code = '''
def generate_conditioning_block(phase, weight_class, fight_format, fatigue_level, injury_flags):
    """
    Generate a conditioning training block based on fight context, weight class, fatigue, and injuries.
    """
    output = f"\\n📦 CONDITIONING MODULE\\nPhase: {phase}\\n"

    # --- Fight format logic (influences energy system bias) ---
    rounds = 3
    if fight_format:
        try:
            rounds = int(fight_format.split('x')[0])
        except:
            pass

    if rounds >= 5:
        output += "\\n• Fight format: 5 rounds → increased aerobic + glycolytic load"
    elif rounds == 3:
        output += "\\n• Fight format: 3 rounds → alactic + power emphasis"

    # --- Weight class logic ---
    if weight_class:
        try:
            weight_val = int(weight_class.split("kg")[0].strip())
            if weight_val >= 90:
                weight_note = "\\n• Heavyweight detected → limit long aerobic sessions, increase rest ratios, emphasize joint care"
            elif weight_val <= 66:
                weight_note = "\\n• Lightweight detected → handle higher glycolytic volumes, more speed-based conditioning"
            else:
                weight_note = "\\n• Mid-weight detected → balanced energy system distribution"
            output += weight_note
        except:
            pass

    # --- Phase-specific conditioning targets ---
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

    else:
        output += "\\n• Phase not recognized — default to aerobic capacity and light intervals."

    # --- Fatigue-aware adjustments ---
    if fatigue_level and "high" in fatigue_level.lower():
        output += "\\n⚠️ High fatigue → cut glycolytic sessions by 30%, extend all rest intervals by 20%"
    elif fatigue_level and "moderate" in fatigue_level.lower():
        output += "\\n⚠️ Moderate fatigue → reduce one interval from highest-load session"

    # --- Injury considerations ---
    if injury_flags:
        flags = injury_flags.lower()
        if "hamstring" in flags:
            output += "\\n⚠️ Hamstring issue → avoid max sprints, use sled drag or bike sprints"
        if "ankle" in flags:
            output += "\\n⚠️ Ankle limitation → remove lateral hops or bounding"
        if "knee" in flags:
            output += "\\n⚠️ Knee injury → no deep squats or bounding; use upright bike or prowler"
        if "back" in flags:
            output += "\\n⚠️ Back strain → avoid axial loading under fatigue (e.g., sprints with vest)"
        if "shoulder" in flags:
            output += "\\n⚠️ Shoulder issue → avoid high-velocity upper body ballistic work (e.g., med ball slams)"

    return output
'''

path = Path("/mnt/data/conditioning.py")
path.write_text(conditioning_module_code.strip())

"✅ Conditioning module upgraded and saved as 'conditioning.py'. Ready for next."