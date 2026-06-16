"""Faithfulness gate: prove a structured_plan is a projection of the Stage 2 text.

The structured card the athlete actually sees is a *second* LLM conversion of the
validated Stage 2 ``final_plan_text``. Schema validity alone does not prove the
card reflects that text — the model can introduce exercises that were never
prescribed, invent countdown (D-day) markers, or move work into the wrong day.
This module compares the generated structured plan against the source markdown
and reports any content the card *introduced* or *misplaced*, so a card that can
not be proven faithful is rejected in favour of the validated text / raw-markdown
fallback. ``final_plan_text`` stays the single source of truth; the structured
plan is allowed through only as a verified projection of it.

Design rules (mirrors ``structured_plan_safety`` conventions):

* Fail-closed but low false-positive. Only CLEAR drift is flagged:
  - INTRODUCED: a training-block exercise whose name shares *no* meaningful token
    with the source text (a fabricated exercise), or a countdown marker absent
    from the source.
  - MISPLACED: an exercise the source assigns to exactly one D-day, placed by the
    card under a *different* D-day (e.g. Pallof moved out of its session).
  A reworded exercise that keeps any meaningful token (``Back Squat`` ->
  ``Barbell Back Squat``) passes. Generic/contextual blocks (mindset, nutrition,
  recovery, mobility, preparation, cooldown) are wording the conversion owns, not
  exercise selection, so they are never exercise-name checked.
* The whole check only runs when the source looks like a real countdown plan
  (it carries at least one ``D-N`` day marker). Stubs / degenerate text are not
  evaluated, so the gate can never reject a card it has no basis to judge.
* Read-only: never mutates the plan. Returns prefixed violation strings.
* Fail-closed: the public entry point never propagates an exception, but an
  internal crash is reported as an INTERNAL violation so an unverifiable card is
  rejected (the raw-markdown fallback ships) rather than passed through.
"""
from __future__ import annotations

import re
from typing import Any

# Violation prefixes so findings are greppable in debug metadata / logs.
INTRODUCED = "INTRODUCED"
MISPLACED = "MISPLACED"
COUNTDOWN = "COUNTDOWN"
# Raised internally by the checker -> treated as a violation so a crash rejects
# the card (fail-closed) rather than letting an unverified card through.
INTERNAL = "INTERNAL"

# ``block_type`` values that name a specific, app-owned exercise we can hold to
# the source text. Generic/contextual block types are deliberately excluded.
_EXERCISE_BLOCK_TYPES = {
    "strength",
    "strength_speed",
    "plyometric_power",
    "speed",
    "accessory",
    "conditioning",
    "rehab",
}

# Tokens too generic to identify a specific exercise or prove day placement.
_GENERIC_TOKENS = {
    "strength", "power", "speed", "session", "sessions", "training", "block",
    "blocks", "work", "warm", "cool", "down", "mobility", "recovery", "rest",
    "conditioning", "circuit", "drill", "drills", "primer", "accessory",
    "exercise", "exercises", "heavy", "light", "tempo", "effort", "rounds",
    "round", "reps", "sets", "left", "right", "front", "back", "upper", "lower",
    "main", "optional", "superset", "isometric", "dynamic", "static", "hold",
    "holds", "with", "from", "this", "that", "each", "side", "both", "core",
}

_TOKEN_RE = re.compile(r"[a-z]+")
_DDAY_RE = re.compile(r"D-(\d+)", re.I)
_ANY_DDAY_RE = re.compile(r"D-\s*\d+", re.I)
# A day header that leads with the countdown, optionally behind markdown hashes
# and/or a weekday, e.g. "D-32 (Wednesday) — Aerobic support" or "### D-30 ...".
_LEADING_DDAY_RE = re.compile(r"^\s*(?:#{1,6}\s*)?(?:[A-Za-z]{3,9}\s+)?D-\d+\b", re.I)
# A "(D-N)" marker anywhere, e.g. "### Mon (D-30) — Strength".
_PAREN_DDAY_RE = re.compile(r"\(D-\d+\)", re.I)


def _day_header_dday(line: str) -> int | None:
    """Return the single D-day a line declares as a training-day header, else None.

    Supports both generated formats — countdown-leading
    (``D-32 (Wednesday) — Aerobic support``) and markdown headings carrying a
    parenthetical marker (``### Mon (D-30) — Strength``). A line with two or more
    D-day numbers is a week/range header (``GPP — Week 1 (D-33 to D-27)``) and is
    never a day section; lines naming "week" are excluded for the same reason.
    """
    nums = _DDAY_RE.findall(line)
    if len(nums) != 1 or "week" in line.lower():
        return None
    is_header = (
        line.lstrip().startswith("#")
        or "—" in line
        or "–" in line
        or bool(_PAREN_DDAY_RE.search(line))
        or bool(_LEADING_DDAY_RE.match(line))
    )
    return int(nums[0]) if is_header else None


def _tokens(text: str) -> set[str]:
    return {tok for tok in _TOKEN_RE.findall(text.lower()) if len(tok) >= 4}


def _meaningful(tokens: set[str]) -> set[str]:
    return {tok for tok in tokens if tok not in _GENERIC_TOKENS}


def _present_in_source(tok: str, source_tokens: set[str]) -> bool:
    """True when a card token matches a source token.

    Exact match, or a shared 5-char prefix so simple inflections (``squat`` vs
    ``squats``, ``lunge`` vs ``lunges``) are not mistaken for fabrication. Short
    tokens (< 5 chars) require an exact match to stay specific.
    """
    if tok in source_tokens:
        return True
    if len(tok) < 5:
        return False
    head = tok[:5]
    return any(
        len(src) >= 5 and (src.startswith(head) or tok.startswith(src[:5]))
        for src in source_tokens
    )


def _dday_num(label: Any) -> int | None:
    """Parse the integer countdown distance from a label like ``D-15`` / ``D0``."""
    match = re.search(r"D\s*-?\s*(\d+)", str(label or ""), re.I)
    return int(match.group(1)) if match else None


def _source_day_sections(markdown: str) -> dict[int, str]:
    """Map each D-day number to the lowercased source text under its day header."""
    sections: dict[int, list[str]] = {}
    current: int | None = None
def _source_day_sections(markdown: str) -> dict[int, str]:
    """Map each D-day number to the lowercased source text under its day header."""
    sections: dict[int, list[str]] = {}
    current: int | None = None
    for line in markdown.splitlines():
        header = _DAY_HEADER_RE.search(line)
        is_range = "→" in line or "->" in line
        if line.lstrip().startswith("#") and header and not is_range:
            current = _dday_num(header.group(0))
            if current is not None:
                sections.setdefault(current, [])
        if current is not None:
            sections[current].append(line)
    return {day: "\n".join(lines).lower() for day, lines in sections.items()}


def _source_token_days(sections: dict[int, str]) -> dict[str, set[int]]:
    """Index: meaningful token -> the set of D-day sections it appears in."""
    index: dict[str, set[int]] = {}
    for day, text in sections.items():
        for tok in _meaningful(_tokens(text)):
            index.setdefault(tok, set()).add(day)
    return index


def check_structured_faithfulness(structured_plan: Any, source_markdown: str) -> list[str]:
    """Return violation strings proving the card drifted from the source text.

    Empty list means the card is a faithful projection (or there is no basis to
    judge — no countdown markers in the source — in which case the schema gate is
    the only authority). Fail-closed: if the check itself crashes it returns a
    violation so the card is rejected rather than shipped unverified.
    """
    try:
        return _check(structured_plan, source_markdown)
    except Exception:  # fail-closed: an unverifiable card must not ship
        return [f"{INTERNAL}: faithfulness check raised; rejecting card"]


def _check(structured_plan: Any, source_markdown: str) -> list[str]:
    plan = structured_plan if isinstance(structured_plan, dict) else {}
    source = str(source_markdown or "")
    # Only evaluate real countdown plans. Stubs / degenerate text without any
    # D-day marker are not judged, so the gate can never reject without a basis.
    if not plan or not _ANY_DDAY_RE.search(source):
        return []

    source_tokens = _meaningful(_tokens(source))
    if not source_tokens:
        return []

    sections = _source_day_sections(source)
    token_days = _source_token_days(sections)

    # Every D-day the source actually mentions (day headers + any inline D-N).
    source_ddays: set[int] = set(sections)
    for match in re.finditer(r"D-\s*(\d+)", source, re.I):
        source_ddays.add(int(match.group(1)))

    violations: list[str] = []

    weeks = plan.get("weeks") if isinstance(plan.get("weeks"), list) else []
    for week in weeks:
        if not isinstance(week, dict):
            continue
        for label in (week.get("countdown_start"), week.get("countdown_end")):
            num = _dday_num(label)
            if num is not None and num not in source_ddays:
                violations.append(f"{COUNTDOWN}: week countdown {label!r} absent from source text")

        for day in week.get("days") or []:
            if not isinstance(day, dict):
                continue
            day_num = _dday_num(day.get("countdown_label"))
            if day_num is not None and day_num not in source_ddays:
                violations.append(
                    f"{COUNTDOWN}: day countdown {day.get('countdown_label')!r} absent from source text"
                )

            for session in day.get("sessions") or []:
                if not isinstance(session, dict):
                    continue
                for block in session.get("blocks") or []:
                    if not isinstance(block, dict):
                        continue
                    if str(block.get("block_type")) not in _EXERCISE_BLOCK_TYPES:
                        continue
                    name = str(block.get("display_name") or "")
                    name_tokens = _meaningful(_tokens(name))
                    if not name_tokens:
                        continue

                    # 1) INTRODUCED: shares no meaningful token with the source.
                    if not any(_present_in_source(tok, source_tokens) for tok in name_tokens):
                        violations.append(
                            f"{INTRODUCED}: exercise {name!r} not present in source text"
                        )
                        continue

                    # 2) MISPLACED: a token the source assigns to exactly one
                    #    D-day, placed by the card under a different D-day.
                    if day_num is None:
                        continue
                    for tok in sorted(name_tokens):
                        days = token_days.get(tok)
                        if days and len(days) == 1 and day_num not in days:
                            (src_day,) = tuple(days)
                            violations.append(
                                f"{MISPLACED}: {name!r} (token {tok!r}) is in source D-{src_day} "
                                f"but card placed it in D-{day_num}"
                            )
                            break

    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for item in violations:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique
