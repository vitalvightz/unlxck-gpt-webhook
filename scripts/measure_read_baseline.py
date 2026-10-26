"""Local synthetic baseline. Run from repo root; never connects to a database.

Fresh fixture per repetition; endpoint sequences are probes, not browser user
journeys. In-memory store calls MUST NOT be reported as database operations.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime, date
from unittest.mock import patch
from collections import Counter
import functools
import json
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from support import FakeStore, seed_default_profiles, _build_client  # noqa: E402
from test_today_read_amplification import (  # noqa: E402
    ATHLETE, PLAN, NOW, _add_camp, _store_with_intake_injury,
)
from test_today_service import TestOpenPlanRestDayResolution  # noqa: E402
from api.services.today_readiness_boundary import build_today_command_view  # noqa: E402

HEADERS = {"Authorization": "Bearer athlete-token"}


def fixture(persona, client=None):
    if client is None:
        client, store, _ = _build_client(enable_in_process_generation=False)
    else:
        store = FakeStore()
        seed_default_profiles(store)
        client.app.state.store = store
    if persona == "injury_history":
        injured = _store_with_intake_injury()
        injured.profiles.update(store.profiles)
        store = injured
        client.app.state.store = store
    elif persona != "tracking_without_plan":
        _add_camp(store, athlete_id=ATHLETE, plan_id=PLAN)
        if persona == "renewable":
            store.plans[PLAN].update(TestOpenPlanRestDayResolution()._store().plans[PLAN])
        if persona == "historical_plans":
            for index in range(5):
                plan_id = f"22222222-2222-2222-2222-{index:012d}"
                _add_camp(store, athlete_id=ATHLETE, plan_id=plan_id, weeks=2)
                store.upsert_session_completion(ATHLETE, {
                    "plan_id": plan_id, "session_id": f"history-{index}",
                    "training_day": f"2026-05-{index+1:02d}", "status": "done",
                    "prescription_snapshot": {"session": {"title": "Saved title"}},
                })
            store.set_active_plan_id(ATHLETE, PLAN)
    counts = Counter()
    # Logical method entries, including nested calls, not inferred DB counts.
    for name in dir(type(store)):
        original = getattr(store, name)
        if callable(original) and name.startswith(("get_", "list_", "count_", "ensure_")):
            def wrap(fn, method):
                @functools.wraps(fn)
                def counted(*args, **kwargs):
                    counts[method] += 1
                    return fn(*args, **kwargs)
                return counted
            setattr(store, name, wrap(original, name))
    return client, store, counts


def percentile(values, fraction):
    return sorted(values)[max(0, __import__("math").ceil(len(values) * fraction) - 1)]


def run(repetitions):
    output = []
    for persona in ("active_camp", "renewable", "tracking_without_plan", "injury_history", "historical_plans"):
        for workflow, paths in {
            "startup_home_probe": ["/api/me"],
            "today_load_refresh_probe": ["/api/today", "/api/today"],
            "plans_list_probe": ["/api/plans"],
            "plan_detail_probe": [f"/api/plans/{PLAN}"],
            "history_page_probe": ["/api/training/history?limit=2"],
            "history_pagination_probe": ["/api/training/history?limit=2&before_day=2026-05-04"],
            "xp_refresh_probe": ["/api/xp/progress"],
            "today_fixed_clock_service": [],
        }.items():
            runs = []
            client = None
            for _ in range(repetitions):
                client, store, counts = fixture(persona, client)
                requests = []
                started = time.perf_counter()
                if paths:
                    for path in paths:
                        t = time.perf_counter()
                        response = client.get(path, headers=HEADERS)
                        requests.append({"status": response.status_code, "roundtrip_ms": (time.perf_counter()-t)*1000,
                                         "decoded_body_bytes": len(response.content)})
                else:
                    build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="UTC", now=NOW)
                runs.append({"workflow_ms": (time.perf_counter()-started)*1000,
                             "store_method_calls": dict(sorted(counts.items())), "requests": requests})
            client.close()
            values = [r["workflow_ms"] for r in runs]
            output.append({"persona": persona, "workflow": workflow, "runs": runs,
                           "p50_ms": statistics.median(values), "p95_ms": percentile(values, .95),
                           "database_operations": None, "database_execution_ms": None,
                           "frontend_latency_ms": None})
    return {"schema_version": 1, "source": "synthetic-local-in-memory-store",
            "base_commit": "f59427a20de5960e1e247586d1e54f3bb80c01be", "python": platform.python_version(),
            "repetitions": repetitions, "clock": "fixed 2026-06-03T15:00:00Z",
            "scenarios": output}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/performance/local-baseline.json")
    args = parser.parse_args()
    if args.runs < 2:
        parser.error("--runs must be at least 2")
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)
    class FixedDate(date):
        @classmethod
        def today(cls):
            return NOW.date()
    # Freeze only application/test clocks; timing uses perf_counter throughout.
    with ExitStack() as stack:
        for name, module in list(sys.modules.items()):
            if module and (name.startswith("api.services.") or name == "support"):
                if getattr(module, "datetime", None) is datetime:
                    stack.enter_context(patch.object(module, "datetime", FixedDatetime))
                if getattr(module, "date", None) is date:
                    stack.enter_context(patch.object(module, "date", FixedDate))
        stack.enter_context(patch("logging.Logger.handle"))
        args.output.write_text(json.dumps(run(args.runs), indent=2) + "\n")
