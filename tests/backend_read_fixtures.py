"""Local fixtures using real Supabase query methods and a deterministic transport.

Auth/bootstrap and unrelated store methods remain in-memory. These are Data API
attempt measurements, not SQL execution or live-network latency observations.
"""
from copy import deepcopy

import httpx
from supabase import ClientOptions, create_client

from api.read_diagnostics import DiagnosticHttpClient
from api.store import SupabaseAppStore
from tests.support import FakeStore, seed_default_profiles, _build_client
from tests.test_today_read_amplification import ATHLETE, PLAN, _add_camp

OTHER_PLAN = "22222222-2222-2222-2222-222222222222"
HEADERS = {"Authorization": "Bearer athlete-token"}


def hybrid_fixture(kind="frozen", client=None):
    if client is None:
        client, store, _ = _build_client(enable_in_process_generation=False)
    else:
        store = FakeStore()
        seed_default_profiles(store)
        client.app.state.store = store
    _add_camp(store, athlete_id=ATHLETE, plan_id=PLAN)
    _add_camp(store, athlete_id=ATHLETE, plan_id=OTHER_PLAN)
    store.set_active_plan_id(ATHLETE, PLAN)
    for plan in store.plans.values():
        plan["planning_brief"] = {"measurement_padding": "x" * (578 * 1024)}
        plan["stage2_payload"] = {"measurement_padding": "y" * (424 * 1024)}
    for index in range(4):
        plan_id = PLAN if index < 2 else OTHER_PLAN
        store.upsert_session_completion(ATHLETE, {
            "plan_id": plan_id, "session_id": "2026-06-04-strength", "training_day": f"2026-06-{4+index:02d}",
            "status": "done", "prescription_snapshot": {"session": {"title": "Saved title"}} if kind == "frozen" else None,
        })
    store.profiles[ATHLETE]["onboarding_draft"] = {"measurement_padding": "z" * (64 * 1024)}
    queries = []

    def respond(request):
        table = request.url.path.rsplit("/", 1)[-1]
        assert request.method == "GET", "Measurement transport never accepts writes"
        if table == "plans":
            rows = list(store.plans.values())
        elif table == "profiles":
            rows = [{**row, "active_plan_id": store.active_plan_ids.get(row["id"])}
                    for row in store.profiles.values()]
        elif table == "session_completions":
            rows = store.session_completions[ATHLETE]
        elif table == "external_training_sessions":
            rows = []
        else:
            raise AssertionError("Unexpected measurement table")
        for field in ("id", "athlete_id"):
            value = request.url.params.get(field)
            if value is not None:
                assert value.startswith("eq.")
                rows = [row for row in rows if str(row.get(field)) == value[3:]]
        rows = deepcopy(rows[:int(request.url.params.get("limit", "200"))])
        selection = request.url.params.get("select", "*")
        if selection != "*":
            columns = selection.split(",")
            rows = [{key.strip(): row.get(key.strip()) for key in columns} for row in rows]
        response = httpx.Response(200, json=rows)
        queries.append({"table": table, "full_row": selection == "*", "response_bytes": len(response.content)})
        return response

    transport_client = DiagnosticHttpClient(transport=httpx.MockTransport(respond))
    real = SupabaseAppStore(create_client("https://synthetic.supabase.co", "synthetic-key", options=ClientOptions(httpx_client=transport_client)), set())
    for name in ("get_plan_for_athlete", "get_training_plan_for_athlete", "get_latest_plan", "get_latest_plan_status",
                 "get_profile", "get_profile_compliance", "get_active_plan_id", "list_session_completions", "list_external_training_sessions"):
        if hasattr(real, name):
            setattr(store, name, getattr(real, name))
    return client, store, queries, transport_client
