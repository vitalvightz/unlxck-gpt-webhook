import argparse
import asyncio
import json
from pathlib import Path

from fightcamp.main import generate_plan
from fightcamp.stage2_pipeline import (
    build_stage2_package,
    build_stage2_retry,
    review_stage2_output,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Stage 1 output, write the Stage 2 handoff, and optionally validate a Stage 2 final plan.",
    )
    parser.add_argument("--input", default="test_data.json", help="Path to Stage 1 input JSON.")
    parser.add_argument("--handoff", default="stage2_handoff.txt", help="Path to write the external AI handoff text.")
    parser.add_argument("--final", default="final_plan.txt", help="Path to the external AI final plan text.")
    parser.add_argument("--retry", default="stage2_retry.txt", help="Path to write the repair prompt when validation needs a retry.")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()

    input_path = Path(args.input)
    handoff_path = Path(args.handoff)
    final_path = Path(args.final)
    retry_path = Path(args.retry)

    if not input_path.exists():
        raise FileNotFoundError(f"Input JSON not found: {input_path}")

    data = json.loads(input_path.read_text(encoding="utf-8"))
    stage1 = await generate_plan(data)

    package = build_stage2_package(stage1_result=stage1)
    handoff_path.write_text(package["handoff_text"], encoding="utf-8")

    print(f"Wrote {handoff_path}")
    print(package["summary"])

    if not final_path.exists():
        print(f"No {final_path} found yet.")
        print("Paste the handoff into your external AI, save its final plan to that file, then rerun this script.")
        return 0

    final_plan = final_path.read_text(encoding="utf-8").strip()
    if not final_plan:
        print(f"{final_path} exists but is empty.")
        print("Paste the external AI final plan into that file, then rerun this script.")
        return 1

    review = review_stage2_output(
        planning_brief=stage1["planning_brief"],
        final_plan_text=final_plan,
    )

    print(review["status"])
    print(review["summary"])
    for line in review["summary_lines"]:
        print(f"- {line}")

    if review["needs_retry"]:
        retry = build_stage2_retry(
            stage1_result=stage1,
            final_plan_text=final_plan,
            validator_report=review["validator_report"],
        )
        retry_path.write_text(retry["repair_prompt"], encoding="utf-8")
        print(f"Wrote {retry_path}")
    else:
        print("No retry prompt needed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))