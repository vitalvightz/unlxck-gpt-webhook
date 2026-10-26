"""Summarise local raw runs; commit aggregates rather than repeated samples."""
import argparse
import json
import math
from pathlib import Path
import statistics

REPO = Path(__file__).resolve().parents[1]


def quantiles(values):
    values = sorted(values)
    return {"p50": statistics.median(values), "p95": values[math.ceil(len(values)*.95)-1]}


def observed(values):
    """A constant when every run agrees; otherwise preserve the observed range."""
    if all(value == values[0] for value in values):
        return values[0]
    if any(value is None for value in values):
        return {"values": sorted(set(values), key=lambda value: (value is not None, value))}
    return {"min": min(values), "max": max(values)}


def compare(before_dir, after_dir):
    result = {"schema_version": 2, "before_commit": "efa2deceb3304381a78c7aa8418cdcb90319b5b6",
              "after_variant": "PR2 backend-read-reduction",
              "source": "synthetic-local; no production latency claims",
              "aggregation": "Counts/bytes are constants when all runs agree, otherwise observed min/max (or distinct values including null). Logical method counts include nested calls and treat absent methods as zero. Per-run timings and traces are local-only; p50/p95 retain all runs.",
              "data_api": [], "local": [], "mutations": []}
    for filename, key in [("data-api.json", "data_api"), ("local-baseline.json", "local"), ("local-mutation-baseline.json", "mutations")]:
        before = json.loads((before_dir / filename).read_text())
        after = json.loads((after_dir / filename).read_text())
        def identity(s):
            return (s.get("persona"), s.get("workflow", s.get("scenario")))
        old = {identity(s): s for s in before["scenarios"]}
        if set(old) != {identity(s) for s in after["scenarios"]}:
            raise ValueError(f"Before/after scenarios differ in {filename}")
        for new in after["scenarios"]:
            prior = old[identity(new)]
            row = {"persona": new.get("persona"), "scenario": identity(new)[1]}
            for label, source in [("before", prior), ("after", new)]:
                runs = source["runs"]
                stats = {"repetitions": len(runs), "p50_ms": source["p50_ms"], "p95_ms": source["p95_ms"]}
                if key == "data_api":
                    stats.update(read_attempts=observed([r["diagnostics"]["reads"] for r in runs]),
                        repeated_reads=observed([r["diagnostics"]["repeated_reads"] for r in runs]),
                        full_plan_reads=observed([sum(q["table"] == "plans" and q["full_row"] for q in r["queries"]) for r in runs]),
                        compact_plan_reads=observed([sum(q["table"] == "plans" and not q["full_row"] for q in r["queries"]) for r in runs]),
                        retrieved_bytes=observed([sum(q["response_bytes"] for q in r["queries"]) for r in runs]),
                        endpoint_bytes=observed([r["endpoint_bytes"] for r in runs]),
                        endpoint_status=observed([r["endpoint_status"] for r in runs]),
                        data_api_attempt_ms=quantiles([r["diagnostics"]["data_api_attempt_ms"] for r in runs]))
                    backend = [r["backend_ms"] for r in runs if r["backend_ms"] is not None]
                    stats["backend_ms"] = quantiles(backend) if backend else None
                else:
                    methods = sorted({method for r in runs for method in r["store_method_calls"]})
                    stats.update(logical_store_calls={method: observed([r["store_method_calls"].get(method, 0) for r in runs]) for method in methods},
                                 http_requests=observed([len(r["requests"]) for r in runs]),
                                 http_statuses=sorted({r["status"] for run in runs for r in run["requests"]}),
                                 endpoint_bytes=observed([sum(x["decoded_body_bytes"] for x in r["requests"]) for r in runs]),
                                 database_operations=None)
                row[label] = stats
            result[key].append(row)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, default=REPO / ".performance-runs/backend-before")
    parser.add_argument("--after", type=Path, default=REPO / ".performance-runs/backend-after")
    parser.add_argument("--output", type=Path, default=REPO / "docs/performance/backend-comparison.json")
    args = parser.parse_args()
    args.output.write_text(json.dumps(compare(args.before, args.after), indent=2) + "\n")
