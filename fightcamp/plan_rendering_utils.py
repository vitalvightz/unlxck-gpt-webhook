from __future__ import annotations

import re


def sanitize_phase_text(text: str, labels: list[str] | tuple[str, ...]) -> str:
    if not text:
        return text
    heading_pattern = "|".join(re.escape(label) for label in labels)
    if heading_pattern:
        text = re.sub(rf"([A-Za-z0-9])(?=({heading_pattern}))", r"\1\n", text)
        text = re.sub(rf"({heading_pattern})(?=\1)", r"\1\n", text)
    labels_lower = {label.lower() for label in labels}
    lines: list[str] = []
    last_label = ""
    for line in text.splitlines():
        stripped = line.strip()
        label = stripped.lower()
        if stripped and label in labels_lower and label == last_label:
            continue
        lines.append(line)
        if stripped and label in labels_lower:
            last_label = label
    return "\n".join(lines)


# Re-exported from main for existing tests.
def _sanitize_phase_text(text: str, labels: list[str] | tuple[str, ...]) -> str:
    return sanitize_phase_text(text, labels)


def normalize_time_labels(text: str) -> str:
    if not text:
        return text
    return re.sub(r"(?<!\*\*)\b(Week|Day)\s+(\d+)\b(?!\*\*)", r"**\1 \2**", text)


# Re-exported from main for existing tests.
def _normalize_time_labels(text: str) -> str:
    return normalize_time_labels(text)


def sanitize_stage_output(text: str) -> str:
    if not text:
        return text
    text = normalize_time_labels(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.strip()


# Re-exported from main for existing tests.
def _sanitize_stage_output(text: str) -> str:
    return sanitize_stage_output(text)