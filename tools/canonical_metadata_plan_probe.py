"""Controlled synthetic planner probe, usable against either source snapshot."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime
import asyncio
import io
import json
from pathlib import Path
import sys

# cwd is an explicitly prepared source snapshot, not this script's directory.
sys.path.insert(0, str(Path.cwd()))


def main():
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        from fightcamp import input_parsing, stage2_planning_brief
        from fightcamp.main import generate_plan

        # Pin both existing planner clock bindings, as tests/planner_clock.py does.
        input_parsing._utc_now = lambda: datetime(2026, 10, 11, 9, 0)
        stage2_planning_brief._utc_now = lambda: datetime(2026, 10, 11, 9, 0)
        baseline = json.loads(Path(sys.argv[1]).read_bytes())
        results = []
        cases = baseline["plans"][:1] if "--first" in sys.argv else baseline["plans"]
        for case in cases:
            plan = asyncio.run(generate_plan(deepcopy(case["payload"])))
            results.append({"case": case["case"], "plan_text": plan["plan_text"], "stage2_payload": plan["stage2_payload"]})
    Path(sys.argv[2]).write_text(json.dumps(results, ensure_ascii=True, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
