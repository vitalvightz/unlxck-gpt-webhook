from types import SimpleNamespace

import api.structured_plan_deterministic_fallback as fallback_module


def test_locked_session_is_merged_before_contact_reconcile(monkeypatch):
    """D-11 Tactical Focus must not hide deterministic technical contact."""
    events: list[str] = []
    brief = {"weekly_role_map": {"weeks": [{"session_roles": []}]}}

    def spine(_plan, _brief):
        return {
            "weeks": [
                {
                    "week_index": 1,
                    "days": [
                        {
                            "countdown_label": "D-11",
                            "today_card": {"headline": ""},
                            "sessions": [],
                        }
                    ],
                }
            ]
        }

    def merge(plan, _brief):
        events.append("merge")
        day = plan["weeks"][0]["days"][0]
        day["sessions"].append(
            {
                "session_id": "locked-watch-11",
                "session_type": "skill",
                "title": "Tactical Focus",
                "objective": "Tactical Focus",
                "completion_status": "not_started",
                "mindset_anchor": {"intent": "", "focus_cue": "", "reset_cue": ""},
                "blocks": [],
            }
        )
        return SimpleNamespace(plan=plan)

    def reconcile(plan, _brief):
        events.append("reconcile")
        day = plan["weeks"][0]["days"][0]
        assert day["sessions"], "contact reconcile must see the locked Tactical Focus session"
        day["today_card"]["coach_led_contact"] = "Controlled fight-speed technical rounds"
        return []

    monkeypatch.setattr(fallback_module, "reconcile_calendar_spine", spine)
    monkeypatch.setattr(fallback_module, "merge_locked_structured_content", merge)
    monkeypatch.setattr(fallback_module, "reconcile_coach_led_sparring_days", reconcile)

    plan = fallback_module.build_deterministic_structured_plan(brief)

    assert plan is not None
    day = plan["weeks"][0]["days"][0]
    assert events == ["merge", "reconcile"]
    assert day["sessions"][0]["title"] == "Tactical Focus"
    assert day["today_card"]["coach_led_contact"] == "Controlled fight-speed technical rounds"
