from types import SimpleNamespace

from fightcamp.coach_review import run_coach_review
from fightcamp.plan_pipeline_blocks import _build_phase_support_block
from fightcamp.plan_pipeline_rendering import _build_coach_notes, _sparring_adjustment_lines, _sparring_nutrition_lines


class _TrainingStub:
    def __init__(self, prev_exercises=None):
        self.prev_exercises = list(prev_exercises or [])

    def to_flags(self):
        return {
            "fatigue": "low",
            "weight": 70.0,
            "age": 28,
            "injuries": [],
            "weight_cut_risk": False,
            "weight_cut_pct": 0.0,
        }


class _ContextStub:
    def __init__(self, active_phases=None, prev_exercises=None):
        self._active_phases = set(active_phases or [])
        self.training_context = _TrainingStub(prev_exercises=prev_exercises)
        self.apply_muay_thai_filters = False
        self.sanitize_labels = ()
        self.plan_input = SimpleNamespace(
            hard_sparring_days=[],
            support_work_days=[],
        )

    def phase_active(self, phase: str) -> bool:
        return phase in self._active_phases


def test_build_phase_support_block_includes_each_active_phase_section():
    context = _ContextStub(active_phases={"GPP", "SPP"})

    block = _build_phase_support_block(context, lambda phase: f"{phase} guidance")

    assert block == "### GPP\n\nGPP guidance\n\n### SPP\n\nSPP guidance"


def test_build_coach_notes_omits_novelty_summary_without_history():
    context = _ContextStub(prev_exercises=[])
    blocks = SimpleNamespace(
        strength_names={"GPP": ["Trap Bar Deadlift"]},
        conditioning_names={"GPP": ["Tempo Run"]},
        coach_review_notes="### Coach Review & Safety Pass\n- Keep shoulder loading conservative.",
    )

    coach_notes = _build_coach_notes(context, blocks)

    assert "Novelty Summary:" not in coach_notes
    assert "Coach Review & Safety Pass" in coach_notes


def test_coach_review_preserves_conditioning_session_count_when_rerendering():
    conditioning_blocks = {
        "SPP": {
            "grouped_drills": {
                "aerobic": [
                    {
                        "name": "Stationary Bike Tempo",
                        "equipment": [],
                        "timing": "18 min",
                        "load": "Zone 2",
                        "rest": "-",
                        "purpose": "Build repeatable aerobic output",
                        "description": "steady low-impact work",
                    }
                ],
                "alactic": [
                    {
                        "name": "Bike Sprint Primer",
                        "equipment": [],
                        "timing": "8 x 8 sec",
                        "load": "Fast but relaxed",
                        "rest": "75 sec",
                        "purpose": "Sharpen speed without soreness",
                        "description": "short relaxed accelerations",
                    }
                ],
            },
            "phase_color": "#FF9800",
            "missing_systems": [],
            "num_sessions": 2,
            "diagnostic_context": {"phase": "SPP", "days_until_fight": 18},
            "sport": "boxing",
        }
    }

    _, _, updated_conditioning, _ = run_coach_review(
        injury_string="moderate right shoulder impingement",
        phase="SPP",
        training_context={
            "equipment": ["stationary_bike"],
            "fight_format": "boxing",
            "style_tactical": ["counter_striker"],
            "style_technical": ["boxing"],
            "fatigue": "low",
            "injuries": ["moderate right shoulder impingement"],
        },
        exercise_bank=[],
        conditioning_banks=[[]],
        strength_blocks={"SPP": None},
        conditioning_blocks=conditioning_blocks,
    )

    assert updated_conditioning["SPP"]["block"].count("\n#### ") == 2


def test_sparring_adjustment_lines_use_declared_days_when_present():
    context = _ContextStub()
    context.plan_input = SimpleNamespace(
        hard_sparring_days=["Tuesday", "Saturday"],
        support_work_days=["Monday"],
    )

    lines = _sparring_adjustment_lines(context)
    nutrition_lines = _sparring_nutrition_lines(context)

    assert "Tuesday, Saturday" in "\n".join(lines)
    assert "s&c-compatible slots" in "\n".join(lines).lower()
    assert "technical skill days" not in "\n".join(lines).lower()
    assert "Tuesday, Saturday" in "\n".join(nutrition_lines)


def test_sparring_adjustment_lines_fall_back_to_generic_text_when_days_unknown():
    context = _ContextStub()

    lines = _sparring_adjustment_lines(context)

    joined = "\n".join(lines)
    assert "If hard sparring lands today" in joined
    assert "If no sparring is fixed this week" in joined
