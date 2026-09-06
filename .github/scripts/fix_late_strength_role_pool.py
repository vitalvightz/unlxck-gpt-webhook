from pathlib import Path

path = Path("fightcamp/stage2_payload.py")
text = path.read_text()
old = '''    if slot_group == "conditioning_slots":
        if role_key in {"strength_touch_day", "neural_primer_day", "alactic_sharpness_day"}:
            if _slot_is_style_taper_neural_primer(slot, role, source_phase=source_phase):
                return True
            if role_key in {"strength_touch_day", "neural_primer_day"}:
                return False
            return slot_role == "alactic" and _slot_selected_option(slot).get("source") != "style_taper"
'''
new = '''    if slot_group == "conditioning_slots":
        # A late strength touch must stay inside strength candidate authority.
        # Do not let style-taper technical rhythm drills satisfy a meaningful
        # strength role merely because they are legal in the same countdown window.
        if role_key == "strength_touch_day":
            return False
        if role_key in {"neural_primer_day", "alactic_sharpness_day"}:
            if _slot_is_style_taper_neural_primer(slot, role, source_phase=source_phase):
                return True
            if role_key == "neural_primer_day":
                return False
            return slot_role == "alactic" and _slot_selected_option(slot).get("source") != "style_taper"
'''
if old not in text:
    raise SystemExit("target role-match block not found")
text = text.replace(old, new, 1)
old2 = '''        if not selected_matches and str(role.get("role_key") or "") in {
            "strength_touch_day", "neural_primer_day", "alactic_sharpness_day"
        }:
'''
new2 = '''        if not selected_matches and str(role.get("role_key") or "") in {
            "neural_primer_day", "alactic_sharpness_day"
        }:
'''
if old2 not in text:
    raise SystemExit("target fallback-role set not found")
path.write_text(text.replace(old2, new2, 1))
