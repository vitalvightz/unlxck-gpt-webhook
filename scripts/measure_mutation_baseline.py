"""Repeat existing fixture workflows and aggregate their opt-in recorder output."""
import argparse
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = [
    "tests/test_api_rehab_completion_flow.py::TestPendingPromptRehydration::test_successful_answer_removes_prompt_using_canonical_exposures",
    "tests/test_exercise_customisation.py::test_added_exercise_can_be_edited_and_logged_with_its_updated_dose",
    "tests/test_external_training.py::test_retry_edit_delete_and_delayed_retry",
    "tests/test_plan_free_readiness.py::test_an_injury_reported_after_a_clean_check_in_refreshes_it",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=10)
    args = parser.parse_args()
    if args.runs < 2:
        parser.error("--runs must be at least 2")
    grouped = {}
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "run.json"
        for _ in range(args.runs):
            completed = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "tests.read_audit_recorder",
                                       "--read-audit-output", str(output), *SCENARIOS], cwd=ROOT, capture_output=True)
            if completed.returncode:
                raise SystemExit("Measurement tests failed; run the selected tests directly for details.")
            for scenario in json.loads(output.read_text())["scenarios"]:
                grouped.setdefault(scenario["scenario"], []).append(scenario)
    scenarios = []
    for name, runs in grouped.items():
        times = sorted(r["workflow_ms"] for r in runs)
        scenarios.append({"scenario": name, "runs": runs, "p50_ms": statistics.median(times),
                          "p95_ms": times[math.ceil(.95*len(times))-1]})
    (ROOT / "docs/performance/local-mutation-baseline.json").write_text(json.dumps({
        "source": "synthetic-existing-test-workflows", "repetitions": args.runs,
        "clock": "Fixture-relative training day; uses wall clock, not production observations",
        "boundaries": "Test call, excluding pytest fixture setup/teardown; includes assertions and local fixture construction inside test bodies",
        "scenarios": scenarios}, indent=2) + "\n")


if __name__ == "__main__":
    main()
