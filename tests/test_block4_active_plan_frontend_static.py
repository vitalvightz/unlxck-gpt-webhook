from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_plans_imports_active_plan_helpers_and_calls_set_active_endpoint():
    source = _read("web/app/plans/page.tsx")
    assert "getActivePlan" in source
    assert "setActivePlan" in source
    api = _read("web/lib/api.ts")
    assert "/api/plans/${encodeURIComponent(planId)}/set-active" in api


def test_plan_manager_renders_active_and_set_active_states():
    source = _read("web/app/plans/page.tsx")
    dashboard = _read("web/components/plans/plan-dashboard.tsx")
    helper = _read("web/lib/plan-active.ts")
    assert "PlanManageSheet" in source
    assert 'return "Active"' in dashboard
    assert '"Make active"' in dashboard
    assert "isCompletedFightCamp(plan.activation_state)" in dashboard
    assert "Camp complete" in dashboard
    assert "Can't be active" in dashboard
    assert "function canSetActivePlan" in helper
    assert 'activationState === "eligible"' in helper
    assert "return canSetActivePlan(plan.activation_state)" in dashboard
    assert "const canActivate = !archived && !active && canSetActive(plan)" in dashboard


def test_plan_manager_never_promotes_latest_saved_plan_to_active():
    source = _read("web/app/plans/page.tsx")
    assert "latestEligiblePlan" not in source
    assert "explicitActivePlan && canSetActive(explicitActivePlan) ? explicitActivePlan : null" in source
    assert "CurrentCampCard" in source
    dashboard = _read("web/components/plans/plan-dashboard.tsx")
    assert "No active plan</h2>" in dashboard
    assert "Make one of your saved plans active." in dashboard


def test_successful_activation_refreshes_progress_and_streak_views():
    for path in ("web/app/plans/page.tsx", "web/components/plan-viewer.tsx"):
        source = _read(path)
        activation_success = source.index("const active = await setActivePlan")
        refresh = source.index("requestXpRefresh();", activation_success)
        assert refresh > activation_success


def test_plan_detail_uses_server_activation_state_for_completed_history():
    source = _read("web/components/plan-viewer.tsx")
    assert "isCompletedFightCamp(plan.activation_state)" in source
    assert "This fight camp has ended." in source
    assert "canSetActivePlan(plan.activation_state)" in source


def test_today_view_full_plan_uses_active_plan_detail_route():
    source = _read("web/components/today-screen.tsx")
    assert 'href={`/plans/${activePlan.id}`}' in source
    assert 'href="/plan"' not in source


def test_overview_view_active_plan_uses_active_plan_detail_route_and_is_read_only():
    source = _read("web/app/page.tsx")
    # The authenticated command area now leads with the decision in the
    # "overview-decision-lead" card (was the "Camp command centre" hero before
    # the P0-2 hierarchy redesign); it still links to the active plan detail
    # route and stays read-only.
    assert "overview-decision-lead" in source
    assert 'href={`/plans/${activePlan.id}`}' in source
    assert "today-checkin-form" not in source
    assert "today-completion-form" not in source
    assert "submitTodayCheckin" not in source
    assert "submitTodaySessionCompletion" not in source


def test_plan_alias_falls_back_to_plans_when_active_plan_missing():
    source = _read("web/app/plan/page.tsx")
    assert 'router.replace("/plans")' in source
    assert "if (active) router.replace(`/plans/${plan.plan_id}`)" in source
    assert "let active = true" in source


def test_archived_plan_action_does_not_claim_to_duplicate():
    plans_page = _read("web/app/plans/page.tsx")
    dashboard = _read("web/components/plans/plan-dashboard.tsx")
    plan_viewer = _read("web/components/plan-viewer.tsx")

    assert "Duplicate as New Plan" not in plans_page
    assert "Duplicate as New Plan" not in dashboard
    assert "Duplicate as New Plan" not in plan_viewer
    assert "PlanManageSheet" in plans_page
    # #2988 unified the CTA wording.
    assert "Create a plan" in dashboard
    assert "Create a plan" in plan_viewer
