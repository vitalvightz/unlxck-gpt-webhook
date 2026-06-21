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
    assert "ACTIVE" in source
    assert "Set active" in source
    assert "Cannot be active" in source
    assert "function canSetActive" in source
    assert 'status === "ready" || status === "publishable_with_flags"' in source


def test_today_view_full_plan_uses_active_plan_detail_route():
    source = _read("web/components/today-screen.tsx")
    assert 'href={`/plans/${activePlan.id}`}' in source
    assert 'href="/plan"' not in source


def test_overview_view_active_plan_uses_active_plan_detail_route_and_is_read_only():
    source = _read("web/app/page.tsx")
    assert "Camp command centre" in source
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
