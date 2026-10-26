"""Summarise committed before/after measurements without inferring SQL counts."""
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1] / "docs/performance"


def quantiles(values):
    values = sorted(values)
    return {"p50": statistics.median(values), "p95": values[math.ceil(len(values)*.95)-1]}


def compare():
    result = {"before_commit": "efa2deceb3304381a78c7aa8418cdcb90319b5b6", "after_variant": "PR2 backend-read-reduction",
              "source": "synthetic-local; no production latency claims", "data_api": [], "local": [], "mutations": []}
    for filename, key in [("data-api.json", "data_api"), ("local-baseline.json", "local"), ("local-mutation-baseline.json", "mutations")]:
        before = json.loads((ROOT / "backend-before" / filename).read_text())
        after = json.loads((ROOT / "backend-after" / filename).read_text())
        def identity(s):
            return (s.get("persona"), s.get("workflow", s.get("scenario")))
        old = {identity(s): s for s in before["scenarios"]}
        for new in after["scenarios"]:
            prior = old[identity(new)]
            row = {"persona": new.get("persona"), "scenario": identity(new)[1]}
            for label, source in [("before", prior), ("after", new)]:
                runs = source["runs"]
                stats = {"repetitions": len(runs), "p50_ms": source["p50_ms"], "p95_ms": source["p95_ms"]}
                if key == "data_api":
                    stats.update(read_attempts=[r["diagnostics"]["reads"] for r in runs],
                        repeated_reads=[r["diagnostics"]["repeated_reads"] for r in runs],
                        full_plan_reads=[sum(q["table"] == "plans" and q["full_row"] for q in r["queries"]) for r in runs],
                        compact_plan_reads=[sum(q["table"] == "plans" and not q["full_row"] for q in r["queries"]) for r in runs],
                        retrieved_bytes=[sum(q["response_bytes"] for q in r["queries"]) for r in runs],
                        endpoint_bytes=[r["endpoint_bytes"] for r in runs],
                        data_api_attempt_ms=quantiles([r["diagnostics"]["data_api_attempt_ms"] for r in runs]))
                    backend = [r["backend_ms"] for r in runs if r["backend_ms"] is not None]
                    stats["backend_ms"] = quantiles(backend) if backend else None
                else:
                    stats.update(logical_store_calls=[r["store_method_calls"] for r in runs],
                                 http_requests=[len(r["requests"]) for r in runs],
                                 endpoint_bytes=[sum(x["decoded_body_bytes"] for x in r["requests"]) for r in runs],
                                 database_operations=None)
                row[label] = stats
            result[key].append(row)
    return result


if __name__ == "__main__":
    (ROOT / "backend-comparison.json").write_text(json.dumps(compare(), indent=2) + "\n")
