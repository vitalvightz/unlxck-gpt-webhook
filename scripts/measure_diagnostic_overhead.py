"""Mock-transport microbenchmark; no network or SQL execution."""
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import httpx  # noqa: E402
from api.read_diagnostics import DiagnosticHttpClient, begin, end  # noqa: E402


def measure(client_class, enabled, count=2000):
    timings = []
    with client_class(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[]))) as client:
        for _ in range(7):
            token = begin()[1] if enabled else None
            started = time.perf_counter()
            try:
                for _ in range(count):
                    client.get("https://synthetic.test/rest/v1/plans?id=eq.fixture")
                timings.append((time.perf_counter()-started)*1e6/count)
            finally:
                if token is not None:
                    end(token)
    return {"median_us_per_attempt": statistics.median(timings), "round_us_per_attempt": timings}


if __name__ == "__main__":
    result = {"source": "synthetic-mock-transport-microbenchmark", "attempts_per_round": 2000, "rounds": 7,
              "plain_httpx": measure(httpx.Client, False),
              "diagnostics_disabled": measure(DiagnosticHttpClient, False),
              "diagnostics_enabled": measure(DiagnosticHttpClient, True)}
    (ROOT / "docs/performance/diagnostic-overhead.json").write_text(json.dumps(result, indent=2) + "\n")
