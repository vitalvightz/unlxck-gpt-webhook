def get_value(field_name: str, fields: dict) -> str:
    return fields.get(field_name, "").strip()

def parse_mindcode_form(fields: dict) -> dict:
    # Short text fields
    full_name = get_value("Full name", fields)
    age = get_value("Age", fields)
    sport = get_value("Sport", fields)
    position_style = get_value("Position/Style", fields)

    # 🔒 Robust phase mapping fix
    phase_raw = get_value("Where are you at in your performance cycle?", fields)
    phase_clean = phase_raw.replace("’", "'").replace("‘", "'").lower().strip()

    phase_mapping = {
        "i'm rebuilding, resetting, or in off-season": "GPP",
        "i'm training hard, sharpening up, or deep in prep": "SPP",
        "i've got a match/event coming up or i'm easing down before game day": "TAPER",
    }

    mental_phase = phase_mapping.get(phase_clean)
    if not mental_phase:
        print(f"⚠️ Phase input not recognized: '{phase_raw}' → defaulting to GPP")
        mental_phase = "GPP"

    # Multi-selects
    under_pressure = [x.strip() for x in get_value("What usually happens to you under pressure? (Tick all that apply)", fields).split(",") if x.strip()]
    post_mistake = [x.strip() for x in get_value("What happens right after you make a mistake? (Tick all that apply)", fields).split(",") if x.strip()]
    focus_breakers = [x.strip() for x in get_value("What breaks your focus most during games or competition? (Tick all that apply)", fields).split(",") if x.strip()]
    confidence_profile = [x.strip() for x in get_value("Which of these sounds most like you? (Pick 1–2 only)", fields).split(",") if x.strip()]
    identity_traits = [x.strip() for x in get_value("Tick the 3 that describes you best:", fields).split(",") if x.strip()]
    tool_preferences = [x.strip() for x in get_value("Which of these mental training tools do you prefer or respond well to? (Tick all that apply)", fields).split(",") if x.strip()]
    key_struggles = [x.strip() for x in get_value("Which of these do you personally struggle with the most during training or competition? (Tick all that apply, be honest)", fields).split(",") if x.strip()]
    elite_traits = [x.strip() for x in get_value("Which traits define a mentally elite athlete in your opinion? (Pick up to 3)", fields).split(",") if x.strip()]

    # Single-selects
    pressure_breath = get_value("When under pressure, I tend to:", fields)
    heart_response = get_value("After a mistake, my heart rate usually:", fields)
    reset_duration = get_value("How long do you take to reset after a bad moment during performance?", fields)
    motivator = get_value("What motivates you more?", fields)
    emotional_trigger = get_value("Which one hits harder?", fields)
    decision_making = get_value("How do you usually make decisions during performance? (Pick one)", fields)

    # Long text
    past_mental_struggles = get_value("Is there anything you’ve struggled with mentally in the past that’s still affecting you?", fields)

    return {
        "full_name": full_name,
        "age": age,
        "sport": sport,
        "position_style": position_style,
        "under_pressure": under_pressure,
        "post_mistake": post_mistake,
        "focus_breakers": focus_breakers,
        "confidence_profile": confidence_profile,
        "identity_traits": identity_traits,
        "tool_preferences": tool_preferences,
        "key_struggles": key_struggles,
        "elite_traits": elite_traits,
        "pressure_breath": pressure_breath,
        "heart_response": heart_response,
        "reset_duration": reset_duration,
        "motivator": motivator,
        "emotional_trigger": emotional_trigger,
        "decision_making": decision_making,
        "past_mental_struggles": past_mental_struggles,
        "mental_phase": mental_phase
    }
