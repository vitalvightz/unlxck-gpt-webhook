from pathlib import Path

p = Path('tests/test_canonical_session_composition.py')
s = p.read_text()
old = '''@pytest.mark.parametrize(
    "role_key", ["strength_touch_day", "neural_primer_day", "alactic_sharpness_day"]
)
def test_all_late_sharpness_roles_share_safe_style_taper_authority(role_key):
'''
new = '''@pytest.mark.parametrize(
    "role_key", ["neural_primer_day", "alactic_sharpness_day"]
)
def test_late_sharpness_roles_share_safe_style_taper_authority(role_key):
'''
if old not in s:
    raise SystemExit('old shared-authority test not found')
s = s.replace(old, new, 1)
anchor = '''    assert [item["name"] for item in assignments["D-7"]] == ["Range Gate-Score-Exit"]


def test_late_selector_does_not_masquerade_aerobic_alternate_as_alactic_on_d2():
'''
insert = '''    assert [item["name"] for item in assignments["D-7"]] == ["Range Gate-Score-Exit"]


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
if anchor not in s:
    raise SystemExit('test insertion anchor not found')
p.write_text(s.replace(anchor, insert, 1))
