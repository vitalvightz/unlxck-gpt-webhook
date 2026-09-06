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

test_path = Path("tests/test_canonical_session_composition.py")
tests = test_path.read_text()
old_test = '''@pytest.mark.parametrize(
    "role_key", ["strength_touch_day", "neural_primer_day", "alactic_sharpness_day"]
)
def test_all_late_sharpness_roles_share_safe_style_taper_authority(role_key):
'''
new_test = '''@pytest.mark.parametrize(
    "role_key", ["neural_primer_day", "alactic_sharpness_day"]
)
def test_late_sharpness_roles_share_safe_style_taper_authority(role_key):
'''
if old_test not in tests:
    raise SystemExit("target parametrized regression not found")
tests = tests.replace(old_test, new_test, 1)
anchor = '''    assert [item["name"] for item in assignments["D-7"]] == ["Range Gate-Score-Exit"]


def test_late_selector_does_not_masquerade_aerobic_alternate_as_alactic_on_d2():
'''
replacement = '''    assert [item["name"] for item in assignments["D-7"]] == ["Range Gate-Score-Exit"]


def test_late_strength_touch_rejects_style_taper_conditioning_fallback():
    role = {
        "role_key": "strength_touch_day",
        "category": "strength",
        "preferred_pool": "strength_slots",
        "late_fight_tail_owned": True,
        "scheduled_countdown_label": "D-12",
    }
    primer = _conditioning_slot("Range Gate-Score-Exit", 1, late_windows=["d13_to_d8"])
    primer["selected"].update({
        "source": "style_taper",
        "selection_metadata": {
            "late_windows": ["d13_to_d8"], "support_only": True,
            "meaningful_stress": False, "lactate_load": "low",
        },
    })

    _, assignments = _build_late_fight_allowed_exercises_by_day(
        spec={"visible_session_sequence": [role], "athlete_model": _taper_athlete()},
        candidate_pools={"SPP": {"conditioning_slots": [primer]}},
    )

    assert assignments["D-12"] == []


def test_late_selector_does_not_masquerade_aerobic_alternate_as_alactic_on_d2():
'''
if anchor not in tests:
    raise SystemExit("test insertion anchor not found")
test_path.write_text(tests.replace(anchor, replacement, 1))
