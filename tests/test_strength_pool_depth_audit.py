"""The diagnostic uses real eligibility and preserves phase continuity."""
import copy

from fightcamp import strength
from tools import audit_strength_pool_depth as audit


def test_static_audit_filters_ineligible_anchors_without_mutating_bank(monkeypatch):
    common = dict(phases=["GPP", "SPP"], movement="squat", equipment="bodyweight", method="strength", tags=[])
    bank = [
        dict(common, name="Split Squat"),
        dict(common, name="Unavailable Squat", equipment="barbell"),
        dict(common, name="Late Squat", late_windows=["d13_to_d8"]),
        dict(common, name="Isometric Squat Hold (110% 1RM)"),
        dict(common, name="Support Squat", support_only=True),
        dict(common, name="Wrong Phase Squat", phases=["TAPER"]),
    ]
    before = copy.deepcopy(bank)
    monkeypatch.setattr(strength, "get_exercise_bank", lambda: bank)
    report = audit.static_audit()
    assert set(report) == {f"{p}/{t}" for p in audit.PHASES for t in audit.EQUIPMENT_TIERS}
    assert report["SPP/min"] == {
        "anchors": 1, "lower_body_loaded": 1, "upper_body_push_pull": 0, "unilateral": 1,
    }
    assert bank == before


def test_selection_pass_carries_prior_phase_names_movements_and_seed(monkeypatch):
    calls = []

    def generate(*, flags, weaknesses):
        calls.append(copy.deepcopy(flags))
        return {"exercises": [{"name": "Split Squat", "movement": "squat", "tags": []}]}

    monkeypatch.setattr(strength, "generate_strength_block", generate)
    audit._camp(["strength"], [], ["wrestler"], "min", "low", 3, seed=4)
    assert [f["phase"] for f in calls] == ["GPP", "SPP"]
    assert all(f["random_seed"] == 4 for f in calls)
    assert calls[1]["prev_exercises"] == ["Split Squat"]
    assert calls[1]["recent_exercises"] == ["squat"]
