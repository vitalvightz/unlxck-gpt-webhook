# conditioning.py

def generate_conditioning_block(phase, weight_class, fight_format, fatigue_level, injury_flags):
    """
    Generate a conditioning training block based on fight context.
    """
    output = f"""\n📦 CONDITIONING MODULE\nPhase: {phase}\n"""

    # --- Fight format logic (influences energy system bias) ---
    rounds = 3
    if fight_format:
        try:
            rounds = int(fight_format.split('x')[0])
        except:
            pass

    if rounds >= 5:
        output += "\n• Fight format: 5 rounds → increased aerobic + glycolytic load"
    elif rounds == 3:
        output += "\n• Fight format: 3 rounds → alactic + power emphasis"

    # --- Phase-specific conditioning targets ---
    if phase == "GPP":
        output += """

• Energy System Targets:
  - Aerobic base (60–70% HR): 2–3x 40-min steady-state runs, cycling, or bag work
  - ATP-PCr: Light sprint work, short med ball throws (10s on, 50s off, 8 rounds)

• Conditioning Notes:
  - Focus on building capacity and durability
  - Ensure nasal breathing and HR cap at ~150 bpm
"""

    elif phase == "SPP":
        output += """

• Energy System Targets:
  - ATP-PCr: Sprint repeats, explosive efforts (5–10s on, 1:6 work:rest)
  - Glycolytic: 2x/week intervals (20s–45s bursts, 1:1.5 rest)

• Conditioning Notes:
  - Mimic fight scenarios with pad work/sparring intervals
  - Combine skill + fatigue for mental carryover
"""

    elif phase == "TAPER":
        output += """

• Energy System Targets:
  - Maintain sharpness: 1x short anaerobic circuit (low volume)
  - Aerobic flush: 1x 20-min easy cardio (non-taxing)

• Conditioning Notes:
  - Do not induce fatigue past Wednesday pre-fight
  - Prioritise speed, reaction time, CNS freshness
"""

    else:
        output += "\n• Phase not recognized — default to aerobic capacity and light intervals."

    # --- Fatigue-aware adjustments ---
    if fatigue_level and "high" in fatigue_level.lower():
        output += "\n⚠️ Fatigue is high → reduce glycolytic volume by 30% and extend rest periods"

    # --- Injury considerations (basic logic) ---
    if injury_flags:
        if "hamstring" in injury_flags.lower():
            output += "\n⚠️ Modify sprint sessions → use assault bike or hill walks"
        if "ankle" in injury_flags.lower():
            output += "\n⚠️ Avoid lateral hops → swap for linear movements only"

    return output