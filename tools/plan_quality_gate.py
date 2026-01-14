#!/usr/bin/env python
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import sys
import tempfile
import unicodedata
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from fightcamp.main import generate_plan

PHASE_HEADERS = [
    "## PHASE 1:",
    "## PHASE 2:",
    "## PHASE 3:",
]
SUBSECTION_HEADERS = [
    "### Mindset Focus",
    "### Strength & Power",
    "### Conditioning",
    "### Recovery",
    "### Nutrition",
    "### Rehab",
    "### Injury Rehab",
    "### Injury Guardrails",
]
SYSTEM_HEADER_PATTERN = re.compile(r"^📌 \*\*System: (.+?)\*\*")


def _load_payload() -> dict:
    data_file = Path("test_data.json").resolve()
    if not data_file.exists():
        raise FileNotFoundError(f"Test data file not found: {data_file}")
    with open(data_file, "r") as handle:
        return json.load(handle)


def _phase_ranges(lines: list[str]) -> dict[str, tuple[int, int]]:
    indices: list[tuple[str, int]] = []
    for idx, line in enumerate(lines):
        for header in PHASE_HEADERS:
            if line.startswith(header):
                indices.append((header, idx))
                break
    indices.sort(key=lambda x: x[1])
    ranges: dict[str, tuple[int, int]] = {}
    for i, (header, start_idx) in enumerate(indices):
        end_idx = indices[i + 1][1] if i + 1 < len(indices) else len(lines)
        ranges[header] = (start_idx, end_idx)
    return ranges


def _first_char_is_broken(line: str) -> bool:
    if not line:
        return False
    ch = line[0]
    if ch in {"\ufeff", "\ufffd"}:
        return True
    return unicodedata.category(ch).startswith("C")


def _bullet_stub(line: str) -> bool:
    stripped = line.lstrip()
    if not stripped:
        return False
    if stripped.startswith(("-", "*", "•")):
        content = stripped[1:].strip()
        return len(content) <= 1
    return False


def _check_conditioning_groups(lines: list[str]) -> list[str]:
    failures: list[str] = []
    idx = 0
    while idx < len(lines):
        match = SYSTEM_HEADER_PATTERN.match(lines[idx].strip())
        if not match:
            idx += 1
            continue
        system_name = match.group(1)
        idx += 1
        drills: list[str] = []
        while idx < len(lines):
            line = lines[idx]
            if SYSTEM_HEADER_PATTERN.match(line.strip()):
                break
            if line.startswith("#"):
                break
            stripped = line.strip()
            if stripped.startswith("#### "):
                break
            if stripped:
                drills.append(line)
            idx += 1
        drill_lines = [l for l in drills if l.lstrip().startswith(("- ", "* ", "•", "1.", "2.", "3."))]
        if not drill_lines:
            failures.append(f"E2 empty conditioning group for system {system_name}")
            continue
        prefix_types = set()
        for line in drill_lines:
            stripped = line.lstrip()
            if re.match(r"^\d+\.\s+", stripped):
                prefix_types.add("numbered")
            elif stripped.startswith(("- ", "* ", "•")):
                prefix_types.add("bullet")
        if len(prefix_types) > 1:
            failures.append(
                f"E1 inconsistent drill prefixes in {system_name} group: {sorted(prefix_types)}"
            )
    return failures


def evaluate_markdown(markdown: str) -> list[str]:
    failures: list[str] = []
    lines = markdown.splitlines()

    heading_count = sum(1 for line in lines if re.match(r"^# FIGHT CAMP PLAN\b", line))
    if heading_count != 1:
        failures.append(f"B1 expected 1 '# FIGHT CAMP PLAN' heading, found {heading_count}")

    for header in PHASE_HEADERS:
        count = sum(1 for line in lines if line.startswith(header))
        if count != 1:
            failures.append(f"B2 expected 1 '{header}' heading, found {count}")

    phase_ranges = _phase_ranges(lines)
    for header, (start, end) in phase_ranges.items():
        phase_lines = lines[start:end]
        for subsection in SUBSECTION_HEADERS:
            count = sum(1 for line in phase_lines if line.strip() == subsection)
            if count > 1:
                failures.append(f"B3 duplicated '{subsection}' in {header}")

        module_lines = [line for line in phase_lines if "Module" in line]
        module_counts: dict[str, int] = {}
        for line in module_lines:
            module_counts[line] = module_counts.get(line, 0) + 1
        for line, count in module_counts.items():
            if count > 1:
                failures.append(f"C2 duplicated module banner in {header}: '{line.strip()}'")

    subsection_blocks: dict[str, int] = {}
    for idx, line in enumerate(lines):
        if line.startswith("### "):
            block = "\n".join(lines[idx:idx + 6])
            subsection_blocks[block] = subsection_blocks.get(block, 0) + 1
    for block, count in subsection_blocks.items():
        if count > 1:
            snippet = block.splitlines()[0]
            failures.append(f"C1 duplicated subsection block starting '{snippet}'")

    if re.search(r"\n{3,}", markdown):
        failures.append("D1 found run of 3+ blank lines")

    for idx, line in enumerate(lines, start=1):
        if _bullet_stub(line):
            failures.append(f"D2 truncated bullet at line {idx}: '{line.strip()}'")
        if _first_char_is_broken(line):
            failures.append(f"D3 broken unicode/control character at line {idx}: '{line[:10]}'")

    failures.extend(_check_conditioning_groups(lines))

    return failures


def evaluate_html(html: str) -> list[str]:
    failures: list[str] = []
    for header in PHASE_HEADERS:
        label = header.replace("## ", "")
        count = len(re.findall(re.escape(label), html))
        if count != 1:
            failures.append(f"F1 expected HTML heading '{label}' once, found {count}")
    return failures


def main() -> int:
    os.environ["FIGHTCAMP_SKIP_UPLOAD"] = "1"
    random.seed(0)

    payload = _load_payload()
    result = asyncio.run(generate_plan(payload))
    markdown = result.get("markdown", "")
    html = result.get("html", "")
    pdf_path = result.get("pdf_path")

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".md") as temp_file:
        temp_file.write(markdown)

    failures: list[str] = []
    if not markdown:
        failures.append("Missing markdown output")
    else:
        failures.extend(evaluate_markdown(markdown))

    if html:
        failures.extend(evaluate_html(html))

    if pdf_path:
        pdf_file = Path(pdf_path)
        if not pdf_file.exists() or pdf_file.stat().st_size == 0:
            failures.append(f"F2 PDF missing or empty at {pdf_path}")

    if failures:
        print("FAIL")
        print("Failed rules:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
