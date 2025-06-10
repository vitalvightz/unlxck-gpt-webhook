# UNLXCK GPT Webhook

This repository generates fight camp programs using OpenAI prompts. The main script reads athlete data and calls `camp_phases.calculate_phase_weeks()` to break a camp into GPP, SPP, and taper phases.

Recent updates fixed short-camp handling and ensured style-specific rules adjust the phase weeks correctly. The helper `_apply_style_rules()` is now used so tactical styles like "pressure fighter" can modify the week allocation after the base calculation.
