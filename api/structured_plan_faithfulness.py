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
  - LOCKED_CONTENT: wording from a governed ``selected_drill_locked`` role that
    appears in the approved source has been removed or rewritten in the card.
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

from dataclasses import dataclass, field
import re
from typing import Any

# Violation prefixes so findings are greppable in debug metadata / logs.
INTRODUCED = "INTRODUCED"
MISPLACED = "MISPLACED"
COUNTDOWN = "COUNTDOWN"
# Raised internally by the checker -> treated as a violation so a crash rejects
# the card (fail-closed) rather than letting an unverified card through.
INTERNAL = "INTERNAL"
LOCKED_CONTENT = "LOCKED_CONTENT"
LOCKED_TACTICAL_WATCH_MISSING = "locked_tactical_watch_missing_from_stage2"

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
    "tactical", "watch", "note", "notes", "cue", "cues", "card", "film",
    "review", "visualization", "visualisation",
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
    never a day section. Lines naming "week" are excluded unless their countdown
    marker leads the line: athlete-facing day titles such as ``D-9 — Fight-week
    freshness`` are valid day sections, not week/range headers.
    """
    nums = _DDAY_RE.findall(line)
    if len(nums) != 1:
        return None
    leading_countdown = bool(_LEADING_DDAY_RE.match(line))
    if "week" in line.lower() and not leading_countdown:
        return None
    is_header = (
        line.lstrip().startswith("#")
        or "—" in line
        or "–" in line
        or bool(_PAREN_DDAY_RE.search(line))
        or leading_countdown
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
    """Parse the countdown distance from a label like ``D-15`` (-> ``15``).

    Returns the magnitude after ``D-`` so it lines up with
    :func:`_day_header_dday` (which keys day sections by the same positive value);
    both must agree for the MISPLACED/COUNTDOWN comparisons to hold.
    """
    match = _DDAY_RE.search(str(label or ""))
    if not match:
        return None
    return int(match.group(1))


def _card_claims_countdown(plan: dict[str, Any]) -> bool:
    """True when the card asserts a countdown structure we would need to verify.

    A real athlete-facing card carries week countdown bounds and/or per-day
    countdown labels. When it does, the source text must carry at least one D-day
    marker for the card to be provable; otherwise the card's countdown claims are
    unverifiable. An empty/degenerate card makes no countdown claim, so there is
    nothing to project and the schema gate is the only authority.
    """
    weeks = plan.get("weeks") if isinstance(plan.get("weeks"), list) else []
    for week in weeks:
        if not isinstance(week, dict):
            continue
        if _dday_num(week.get("countdown_start")) is not None:
            return True
        if _dday_num(week.get("countdown_end")) is not None:
            return True
        days = week.get("days") if isinstance(week.get("days"), list) else []
        for day in days:
            if isinstance(day, dict) and _dday_num(day.get("countdown_label")) is not None:
                return True
    return False


def _source_day_sections(markdown: str) -> dict[int, str]:
    """Map each D-day number to the lowercased source text under its day header.

    Uses :func:`_day_header_dday` (which understands both the countdown-leading and
    parenthetical heading formats and excludes week/range headers) to find where
    each day section starts; lines accumulate under the most recent day.
    """
    sections: dict[int, list[str]] = {}
    current: int | None = None
    for line in markdown.splitlines():
        day = _day_header_dday(line)
        if day is not None:
            current = day
            sections.setdefault(current, [])
        if current is not None:
            sections[current].append(line)
    return {day: "\n".join(lines).lower() for day, lines in sections.items()}


def _source_day_section_lines(markdown: str) -> dict[int, list[str]]:
    """Map each D-day number to its raw source lines."""
    sections: dict[int, list[str]] = {}
    current: int | None = None
    for line in markdown.splitlines():
        day = _day_header_dday(line)
        if day is not None:
            current = day
            sections.setdefault(current, [])
        if current is not None:
            sections[current].append(line)
    return sections


def _source_day_header_indices(lines: list[str], day: int) -> list[int]:
    return [
        index
        for index, line in enumerate(lines)
        if _day_header_dday(line) == day
    ]


def _source_day_insert_index(lines: list[str], day: int) -> tuple[int | None, str | None]:
    """Resolve where a same-day support session can be appended.

    Multiple headers for the same D-day are valid when they represent separate
    sessions on one contiguous calendar day. A repeated D-day split by another
    D-day is treated as ambiguous because inserting into one island would guess
    at calendar ownership.
    """
    indices = _source_day_header_indices(lines, day)
    if not indices:
        return None, "authoritative day missing from stage2"

    start = indices[0]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        next_day = _day_header_dday(lines[index])
        if next_day is not None and next_day != day:
            end = index
            break

    if any(index >= end for index in indices):
        return None, "authoritative day split across multiple calendar groups"
    return end, None


def _source_token_days(sections: dict[int, str]) -> dict[str, set[int]]:
    """Index: meaningful token -> the set of D-day sections it appears in."""
    index: dict[str, set[int]] = {}
    for day, text in sections.items():
        for tok in _meaningful(_tokens(text)):
            index.setdefault(tok, set()).add(day)
    return index


def check_structured_faithfulness(
    structured_plan: Any,
    source_markdown: str,
    planning_brief: Any = None,
) -> list[str]:
    """Return violation strings proving the card drifted from the source text.

    Empty list means the card is a faithful projection (or there is no basis to
    judge — no countdown markers in the source — in which case the schema gate is
    the only authority). Fail-closed: if the check itself crashes it returns a
    violation so the card is rejected rather than shipped unverified.
    """
    try:
        return _check(structured_plan, source_markdown, planning_brief)
    except Exception:  # fail-closed: an unverifiable card must not ship
        return [f"{INTERNAL}: faithfulness check raised; rejecting card"]


def _normalise_locked_text(value: Any) -> str:
    """Normalise presentation-only differences without permitting a rewrite."""
    return " ".join(
        str(value or "")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .lower()
        .split()
    )


def _locked_roles(value: Any) -> list[dict[str, Any]]:
    """Find governed roles without depending on a particular brief nesting."""
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        governance = value.get("governance")
        if (
            isinstance(governance, dict)
            and governance.get("selected_drill_locked") is True
            and isinstance(value.get("display_text"), str)
        ):
            found.append(value)
        for child in value.values():
            found.extend(_locked_roles(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_locked_roles(child))
    return found


def _card_strings(value: Any) -> list[str]:
    """Collect strings from a deliberately scoped piece of the card."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [
            text
            for child in value.values()
            for text in _card_strings(child)
        ]
    if isinstance(value, list):
        return [text for child in value for text in _card_strings(child)]
    return []


def _locked_source_day(source: str, role: dict[str, Any], drill_name: str) -> int | None:
    """Resolve the authoritative source day for one locked drill role."""
    sections = _source_day_sections(source)
    role_day = next(
        (
            _dday_num(role.get(key))
            for key in (
                "scheduled_countdown_label",
                "countdown_label",
                "countdown_display_label",
            )
            if _dday_num(role.get(key)) is not None
        ),
        None,
    )
    normalised_name = _normalise_locked_text(drill_name)
    if role_day is not None and normalised_name in _normalise_locked_text(
        sections.get(role_day, "")
    ):
        return role_day
    matching_days = [
        day
        for day, section in sections.items()
        if normalised_name in _normalise_locked_text(section)
    ]
    return matching_days[0] if len(matching_days) == 1 else None


def _authoritative_locked_day(role: dict[str, Any]) -> int | None:
    return next(
        (
            _dday_num(role.get(key))
            for key in (
                "scheduled_countdown_label",
                "countdown_label",
                "countdown_display_label",
            )
            if _dday_num(role.get(key)) is not None
        ),
        None,
    )


def _locked_source_drill_text(
    source: str, role: dict[str, Any], drill_name: str
) -> tuple[int | None, str, str | None]:
    """Return the authoritative source text for one locked drill.

    The check is intentionally scoped to the role's D-day and then to the named
    drill block under that day. Repeated overlay wording elsewhere in the plan is
    not evidence for this drill.
    """
    role_day = _authoritative_locked_day(role)
    if role_day is None:
        fallback_day = _locked_source_day(source, role, drill_name)
        if fallback_day is None:
            return None, "", "missing_authoritative_countdown_label"
        role_day = fallback_day

    sections = _source_day_section_lines(source)
    if role_day not in sections:
        return role_day, "", "authoritative_day_missing_from_stage2"

    normalised_name = _normalise_locked_text(drill_name)
    lines = sections[role_day]
    name_index = next(
        (
            index
            for index, line in enumerate(lines)
            if normalised_name in _normalise_locked_text(line)
        ),
        None,
    )
    if name_index is None:
        return role_day, "", LOCKED_TACTICAL_WATCH_MISSING

    start = name_index
    if name_index > 0 and _normalise_locked_text(lines[name_index - 1]).startswith("why:"):
        start = name_index - 1

    end = len(lines)
    for index in range(name_index + 1, len(lines)):
        stripped = lines[index].strip()
        if not stripped:
            continue
        if _day_header_dday(stripped) is not None:
            end = index
            break
        if stripped.lower().startswith("why:"):
            end = index
            break
        if stripped.startswith("- ") and not lines[index].startswith((" ", "\t")):
            end = index
            break

    return role_day, "\n".join(lines[start:end]), None


def _locked_drill_card_strings(
    plan: dict[str, Any], source: str, role: dict[str, Any], drill_name: str
) -> list[str]:
    """Collect only the matching block and its owning session's mapped fields."""
    source_day = _locked_source_day(source, role, drill_name)
    if source_day is None:
        return []
    normalised_name = _normalise_locked_text(drill_name)
    scoped: list[str] = []
    for week in plan.get("weeks") or []:
        if not isinstance(week, dict):
            continue
        for day in week.get("days") or []:
            if (
                not isinstance(day, dict)
                or _dday_num(day.get("countdown_label")) != source_day
            ):
                continue
            for session in day.get("sessions") or []:
                if not isinstance(session, dict):
                    continue
                matching_blocks = [
                    block
                    for block in session.get("blocks") or []
                    if isinstance(block, dict)
                    and _normalise_locked_text(block.get("display_name"))
                    == normalised_name
                ]
                for block in matching_blocks:
                    scoped.extend(_card_strings(block))
                    # These are the legitimate homes for Why and the session-level
                    # locked mindset. Other blocks and day/plan notes stay excluded.
                    scoped.extend(_card_strings(session.get("objective")))
                    scoped.extend(_card_strings(session.get("mindset_anchor")))
    return scoped


def _locked_content_violations(
    plan: dict[str, Any], source: str, planning_brief: Any
) -> list[str]:
    """Require every authoritative locked-drill line to survive in card fields."""
    violations: list[str] = []
    for role in _locked_roles(planning_brief):
        governance = role.get("governance") or {}
        drill_name = str(
            governance.get("selected_drill_name")
            or (role.get("preferred_exercise_names") or [""])[0]
            or "locked drill"
        )
        source_day, drill_source_text, drill_source_issue = _locked_source_drill_text(
            source, role, drill_name
        )
        if drill_source_issue is not None:
            if governance.get("mandatory") is True or role.get("mandatory_tactical_watch") is True:
                day_label = f"D-{source_day}" if source_day is not None else "unknown day"
                violations.append(
                    f"{LOCKED_CONTENT}: {drill_name!r} {drill_source_issue} on {day_label}"
                )
            continue

        scoped_source_text = _normalise_locked_text(drill_source_text)
        card_texts = [
            _normalise_locked_text(text)
            for text in _locked_drill_card_strings(plan, source, role, drill_name)
        ]
        required: list[tuple[str, str]] = [("selected drill name", drill_name)]
        for raw_line in str(role["display_text"]).splitlines():
            line = raw_line.strip().lstrip("- ").strip()
            if not line:
                continue
            match = re.match(
                r"((?:Step\s+\d+)|Why|Intent|Focus|Reset|Anchor|Purpose|Progress):\s*(.+)",
                line,
                re.I,
            )
            if match:
                required.append((match.group(1), match.group(2)))

        missing: list[str] = []
        for label, expected in required:
            normalised = _normalise_locked_text(expected)
            # The approved plan text is the authority. A stale brief line that
            # did not reach it must not create a new requirement here.
            if not normalised or normalised not in scoped_source_text:
                continue
            if not any(normalised in card_text for card_text in card_texts):
                missing.append(label)
        if missing:
            violations.append(
                f'{LOCKED_CONTENT}: {drill_name!r} lost required source content: '
                + ", ".join(missing)
            )
    return violations


@dataclass(frozen=True)
class LockedSourceRepairIssue:
    countdown_label: str | None
    block_name: str
    reason: str


@dataclass
class LockedSourceRepairResult:
    source_markdown: str
    applied: list[str] = field(default_factory=list)
    unresolved: list[LockedSourceRepairIssue] = field(default_factory=list)


def _is_active_locked_tactical_watch_role(role: dict[str, Any]) -> tuple[bool, str | None]:
    governance = role.get("governance") if isinstance(role.get("governance"), dict) else {}
    if role.get("active") is False or role.get("is_active") is False:
        return False, "locked role is inactive"
    if role.get("skip") is True or role.get("omit") is True:
        return False, "locked role is suppressed"
    if governance.get("selected_drill_locked") is not True:
        return False, "selected drill is not locked"
    if governance.get("render_selected_drill_exactly") is not True:
        return False, "selected drill is not exact-render locked"
    if governance.get("mandatory") is not True and role.get("mandatory_tactical_watch") is not True:
        return False, "locked role is not mandatory"

    role_key = str(role.get("role_key") or "").strip().lower()
    category = str(role.get("category") or "").strip().lower()
    is_tactical_watch = (
        role_key in {"", "tactical_watch"}
        and (
            role.get("mandatory_tactical_watch") is True
            or isinstance(role.get("tactical_watch"), dict)
            or category in {"", "tactical_watch", "mindset", "combat"}
        )
    )
    if not is_tactical_watch:
        return False, "locked role is not tactical_watch"
    return True, None


def repair_locked_tactical_watch_source_text(
    source_markdown: str, planning_brief: Any
) -> LockedSourceRepairResult:
    """Insert missing mandatory locked Tactical Watches into Stage 2 text.

    This keeps the existing source-of-truth model: structured conversion sees
    the repaired Stage 2 text first, then the structured merge projects the same
    governed role into JSON. Repair is intentionally narrow and fail-closed: it
    only appends exact ``display_text`` to a uniquely resolved existing D-day.
    """
    source = str(source_markdown or "")
    if not source.strip():
        return LockedSourceRepairResult(source)
    roles = [
        role
        for role in _locked_roles(planning_brief)
        if (role.get("governance") or {}).get("mandatory") is True
        or role.get("mandatory_tactical_watch") is True
    ]
    if not roles:
        return LockedSourceRepairResult(source)

    result = LockedSourceRepairResult(source)
    for role in roles:
        governance = role.get("governance") or {}
        drill_name = str(
            governance.get("selected_drill_name")
            or (role.get("preferred_exercise_names") or [""])[0]
            or "locked drill"
        )
        role_day = _authoritative_locked_day(role)
        day_label = f"D-{role_day}" if role_day is not None else None
        is_active_tactical_watch, role_issue = _is_active_locked_tactical_watch_role(role)
        if not is_active_tactical_watch:
            result.unresolved.append(LockedSourceRepairIssue(day_label, drill_name, role_issue or "invalid role"))
            continue
        if role_day is None:
            result.unresolved.append(
                LockedSourceRepairIssue(day_label, drill_name, "missing authoritative countdown label")
            )
            continue
        tactical_watch = role.get("tactical_watch") if isinstance(role.get("tactical_watch"), dict) else {}
        watch_name = str(tactical_watch.get("name") or "").strip()
        if watch_name and _normalise_locked_text(watch_name) != _normalise_locked_text(drill_name):
            result.unresolved.append(
                LockedSourceRepairIssue(day_label, drill_name, "tactical_watch name conflicts with locked drill")
            )
            continue
        display_text = str(role.get("display_text") or "").strip()
        if not display_text:
            result.unresolved.append(
                LockedSourceRepairIssue(day_label, drill_name, "missing locked display_text")
            )
            continue
        if _normalise_locked_text(drill_name) not in _normalise_locked_text(display_text):
            result.unresolved.append(
                LockedSourceRepairIssue(day_label, drill_name, "locked display_text does not contain drill name")
            )
            continue
        _source_day, _drill_text, issue = _locked_source_drill_text(
            result.source_markdown, role, drill_name
        )
        if issue is None:
            continue
        if issue != LOCKED_TACTICAL_WATCH_MISSING:
            result.unresolved.append(LockedSourceRepairIssue(day_label, drill_name, issue))
            continue

        lines = result.source_markdown.splitlines()
        insert_index, insert_issue = _source_day_insert_index(lines, role_day)
        if insert_issue is not None or insert_index is None:
            result.unresolved.append(LockedSourceRepairIssue(day_label, drill_name, insert_issue or "invalid day"))
            continue

        header_index = _source_day_header_indices(lines, role_day)[0]
        day_prefix = re.search(r"\bD-\s*\d+\b(?:\s*\([^)]+\))?", lines[header_index], re.I)
        header_prefix = day_prefix.group(0) if day_prefix else day_label
        repair_block = ["", f"{header_prefix} — Fight Tactical Watch", display_text, ""]
        lines[insert_index:insert_index] = repair_block
        result.source_markdown = "\n".join(lines)
        result.applied.append(f"{day_label}: {drill_name}")
    return result


def _check(structured_plan: Any, source_markdown: str, planning_brief: Any = None) -> list[str]:
    plan = structured_plan if isinstance(structured_plan, dict) else {}
    source = str(source_markdown or "")
    if not plan:
        return []
    locked_violations = _locked_content_violations(plan, source, planning_brief)
    if not _ANY_DDAY_RE.search(source):
        # Card-first hard gate: a card that claims a countdown structure cannot be
        # proven faithful against source text carrying no D-day marker at all, so
        # it is unverifiable and must not ship as the athlete-facing artifact
        # (the raw plan_text fallback / review hold takes over). A card that makes
        # no countdown claim has nothing to project, so the schema gate stands.
        if _card_claims_countdown(plan):
            return locked_violations + [
                f"{COUNTDOWN}: source text carries no D-day marker; "
                "card countdown is unverifiable"
            ]
        return locked_violations

    source_tokens = _meaningful(_tokens(source))
    if not source_tokens:
        return []

    sections = _source_day_sections(source)
    token_days = _source_token_days(sections)

    # Every D-day the source actually mentions (day headers + any inline D-N).
    source_ddays: set[int] = set(sections)
    for match in _DDAY_RE.finditer(source):
        num = _dday_num(match.group(0))
        if num is not None:
            source_ddays.add(num)

    violations: list[str] = list(locked_violations)

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
