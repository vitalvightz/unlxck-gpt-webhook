from fightcamp.restriction_filtering import evaluate_restriction_impact


def test_evaluate_restriction_impact_excludes_avoid():
    restrictions = [
        {
            "restriction": "heavy_overhead_pressing",
            "region": "shoulder",
            "strength": "avoid",
            "original_phrase": "avoid heavy overhead pressing",
        }
    ]
    exclude, penalty, matched = evaluate_restriction_impact(
        restrictions,
        text="Barbell overhead press",
        tags=["overhead", "press"],
        limit_penalty=-0.75,
    )
    assert exclude is True
    assert penalty == 0.0
    assert matched == ["heavy_overhead_pressing"]


def test_evaluate_restriction_impact_penalizes_limit():
    restrictions = [
        {
            "restriction": "deep_knee_flexion",
            "region": "knee",
            "strength": "limit",
            "original_phrase": "limit deep knee flexion",
        }
    ]
    exclude, penalty, matched = evaluate_restriction_impact(
        restrictions,
        text="Tempo squat with deep knee flexion",
        tags=["squat", "quad_dominant"],
        limit_penalty=-0.75,
    )
    assert exclude is False
    assert penalty == -0.75
    assert matched == ["deep_knee_flexion"]
