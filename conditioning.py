from pathlib import Path
import json
from injury_subs import injury_subs
from training_context import normalize_equipment_list, known_equipment

# 🔁 Equipment match with fallback penalty logic
def get_equipment_penalty(entry_equip, user_equipment):
    """
    Unified equipment penalty logic:
    - Consistent with strength module
    - Handles bodyweight/empty cases
    - Only excludes when known equipment is missing
    - Penalizes unknown equipment but includes
    """
    if not entry_equip:
        return 0
        
    entry_equip_list = [e.strip().lower() for e in entry_equip.replace("/", ",").split(",") if e.strip()]
    user_equipment = [e.lower() for e in user_equipment]
    
    if "bodyweight" in entry_equip_list:
        return 0

    # Check for known equipment that's not selected
    for eq in entry_equip_list:
        if eq in known_equipment and eq not in user_equipment:
            return -999
            
    # Apply penalty for unlisted equipment
    if any(eq not in known_equipment for eq in entry_equip_list):
        return -1
        
    return 0

# Load bank
conditioning_bank = json.loads(Path("conditioning_bank.json").read_text())

def generate_conditioning_block(flags: dict):
    phase = flags.get("phase", "GPP")
    injuries = flags.get("injuries", [])
    fatigue = flags.get("fatigue", "low")
    equipment = normalize_equipment_list(flags.get("equipment", []))
    style = [flags.get("style_tactical", ""), flags.get("style_technical", "")]
    goals = flags.get("key_goals", [])
    weaknesses = flags.get("weaknesses", [])

    weight_map = {"weakness": 2.5, "goal": 2, "style": 1}

    style_tag_map = {
        "brawler": ["posterior_chain", "explosive", "rate_of_force", "mental_toughness"],
        "pressure fighter": ["aerobic", "work_capacity", "glycolytic", "mental_toughness"],
        "clinch fighter": ["grip", "core", "eccentric", "shoulders"],
        "distance striker": ["footwork", "reactive", "rate_of_force", "visual_processing"],
        "counter striker": ["reactive", "balance", "cognitive", "core"],
        "submission hunter": ["core", "top_control", "parasympathetic"],
        "kicker": ["hip_dominant", "balance", "posterior_chain"],
        "scrambler": ["reactive", "agility", "endurance"],
        "boxer": ["rate_of_force", "footwork", "shoulders"],
        "muay thai": ["shoulders", "balance", "eccentric"],
        "bjj": ["grip", "core", "parasympathetic"]
    }

    goal_tag_map = {
        "power": ["rate_of_force", "explosive", "triple_extension"],
        "endurance": ["aerobic", "work_capacity", "glycolytic", "mental_toughness"],
        "speed": ["acceleration", "footwork", "reactive"],
        "mobility": ["mobility", "balance", "unilateral"],
        "grappling": ["wrestling", "top_control", "grip"],
        "striking": ["striking", "footwork", "rate_of_force"],
        "recovery": ["recovery", "parasympathetic", "low_impact"],
        "injury prevention": ["zero_impact", "rehab_friendly", "parasympathetic"],
        "mental": ["cognitive", "mental_toughness", "visual_processing"]
    }

    tag_counter = {}
    for w in weaknesses:
        for tag in goal_tag_map.get(w, []):
            tag_counter[tag] = tag_counter.get(tag, 0) + weight_map["weakness"]
    for g in goals:
        for tag in goal_tag_map.get(g, []):
            tag_counter[tag] = tag_counter.get(tag, 0) + weight_map["goal"]
    for s in style:
        for tag in style_tag_map.get(s.lower(), []):
            tag_counter[tag] = tag_counter.get(tag, 0) + weight_map["style"]

    scored = []
    for entry in conditioning_bank:
        if phase not in entry["phases"]:
            continue

        entry_equip_str = ",".join(entry.get("equipment", []))
        penalty = get_equipment_penalty(entry_equip_str, equipment)
        score = sum(tag_counter.get(tag, 0) for tag in entry.get("tags", [])) + penalty

        if score > 0:
            scored.append((entry, score))

    days = flags.get("days_available", [])
if isinstance(days, int):
    days_count = days
else:
    days_count = len(days)

max_exercises = min(6 + max(days_count - 2, 0) * 2, 12)

    conditioning_block = ["🏃‍♂️ **Conditioning Module**", f"**Phase:** {phase}", "**Top Drills:**"]
    for ex in selected:
        conditioning_block.append(f"- {ex['name']}")

    if fatigue == "high":
        conditioning_block.append("⚠️ High fatigue → swap 1 drill for recovery work or reduce total time by 25%.")
    elif fatigue == "moderate":
        conditioning_block.append("⚠️ Moderate fatigue → remove 1 set or reduce tempo.")

    return "\n".join(conditioning_block)
