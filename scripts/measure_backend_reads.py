"""Measure real Supabase Data API attempts against deterministic local transport."""
import argparse
from contextlib import redirect_stdout
import io
import json
import math
from pathlib import Path
import statistics
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
with redirect_stdout(io.StringIO()):
    from tests.backend_read_fixtures import hybrid_fixture, HEADERS, ATHLETE, OTHER_PLAN
    from api.read_diagnostics import begin, end
    from api.services.active_plan import _active_plan_overlap
    from api.services.today_service import check_in_possible


def run(count, audit_log):
    results = []
    for scenario in ("history_frozen", "history_legacy", "completion_history_frozen", "landing", "overlap", "consent"):
        runs = []
        client = None
        for _ in range(count):
            client, store, queries, transport = hybrid_fixture("legacy" if scenario == "history_legacy" else "frozen", client)
            audit_log.reset_mock()
            diagnostics, token = begin()
            started = time.perf_counter()
            response = None
            try:
                if scenario.startswith("history_"):
                    response = client.get("/api/training/history", headers=HEADERS)
                elif scenario == "completion_history_frozen":
                    response = client.get("/api/today/session-completions", headers=HEADERS)
                elif scenario == "landing":
                    # Isolate the route's existence read from unrelated Today work.
                    with patch("api.routes.today.resolve_today_landing") as resolve:
                        resolve.return_value = type("Decision", (), dict(target="today", cta="Open", row=1, reason="fixture"))()
                        response = client.get("/api/today/landing", headers=HEADERS)
                elif scenario == "overlap":
                    assert _active_plan_overlap(store, ATHLETE, store.plans[OTHER_PLAN], current_training_day="2026-06-03") is not None
                else:
                    assert check_in_possible(store, ATHLETE)
                measured = diagnostics.snapshot()
                if response is not None:
                    records = [json.loads(call.args[1]) for call in audit_log.call_args_list
                               if call.args[0] == "[read-audit] %s"]
                    assert len(records) == 1
                    measured = records[0]
                assert measured["failures"] == 0, "Measurement transport failed"
                runs.append({"duration_ms": (time.perf_counter()-started)*1000,
                             "diagnostics": measured, "queries": queries,
                             "backend_ms": measured.get("backend_ms"),
                             "endpoint_status": response.status_code if response is not None else None,
                             "endpoint_bytes": len(response.content) if response is not None else None})
                if response is not None:
                    assert response.is_success, "Synthetic endpoint must succeed"
            finally:
                end(token)
                transport.close()
        client.close()
        times = sorted(r["duration_ms"] for r in runs)
        results.append({"scenario": scenario, "runs": runs, "p50_ms": statistics.median(times), "p95_ms": times[math.ceil(.95*len(times))-1]})
    return {"source": "synthetic-real-Supabase-query-builder-mock-transport", "scope": "Selected Data API methods; authentication/bootstrap and unrelated reads remain in-memory; no SQL/network timing", "repetitions": count, "scenarios": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=20)
    args = parser.parse_args()
    if args.runs < 2:
        parser.error("--runs must be at least 2")
    with patch("logging.Logger.handle"), patch.dict("os.environ", {"UNLXCK_READ_DIAGNOSTICS": "1"}), patch("api.app.logger.info") as audit_log:
        args.output.write_text(json.dumps(run(args.runs, audit_log), indent=2) + "\n")
