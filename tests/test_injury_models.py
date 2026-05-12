from fightcamp.injury_models import Decision


def test_decision_accepts_all_supported_actions():
    for action in ("allow", "modify", "flag", "exclude"):
        decision = Decision(
            action=action,
            risk_score=0.25,
            threshold=0.5,
            matched_tags=[],
            mods=[],
            reason={},
        )
        assert decision.action == action
