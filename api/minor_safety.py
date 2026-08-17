"""Under-18 weight-cut safety guard.

``docs/children-age-appropriate-use-policy.md`` is unconditional: for under-18s,
UNLXCK must "not provide aggressive weight-cut, dehydration or automated
water-cut protocols". ``docs/terms-of-use.md`` repeats it as a user-facing
promise.

This module is the authority for that rule. It does not redesign the nutrition
system — it does three small things at the points where a cut can reach a child:

1. :func:`minor_safe_stage1_payload` strips the cut inputs from the Stage 1
   planner payload, so the deterministic pipeline never computes a cut in the
   first place (``weight_cut_risk`` stays false and every downstream block that
   hangs off it — acute-cut protocol, rehydration, diuretic notes — is simply
   never produced).
2. :func:`scrub_minor_guidance` removes blocked guidance from athlete-facing
   text. Stage 2 is an LLM and the regulatory boundary says AI output is
   "subordinate to UNLXCK's deterministic safety rules", so the deterministic
   layer gets the last word on the way out, not just on the way in.
3. :func:`detect_minor_guidance_leakage` reports the same thing as audit
   findings, letting the structured-plan safety audit block a card rather than
   publish guidance a child must not see.

The patterns target *protocols*, not vocabulary: ordinary hydration advice
("drink water", "hydrate steadily") must survive, because telling a child to
drink less is the harm — telling them to drink is not.
"""
from __future__ import annotations

import re
from typing import Any

MINOR_GUIDANCE_BLOCK_REASON = "under_18_weight_cut_blocked"

# Shown in place of anything removed. Names the rule rather than silently
# deleting a section, so an athlete who expected cut guidance learns why it is
# absent instead of assuming the plan is broken.
MINOR_WEIGHT_CUT_NOTE = (
    "Weight-cut, dehydration and water-cut guidance is not provided to athletes "
    "under 18. Talk to your coach and an appropriately qualified health "
    "professional about making weight safely."
)

# Blocked guidance. Each pattern describes an acute cut / fluid-restriction
# protocol, which is what the policy prohibits for under-18s.
_BLOCKED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("water_cut", re.compile(r"\bwater\s*(?:cut|cutting|load(?:ing)?|manipulat\w*)\b", re.I)),
    ("dehydration", re.compile(r"\bde-?hydrat\w*\b", re.I)),
    ("rehydration_protocol", re.compile(r"\bre-?hydrat\w*\b", re.I)),
    ("sweat_protocol", re.compile(r"\b(?:sauna|sweat\s*suit|sweatsuit|plastic\s*suit|hot\s*bath\s*cut)\b", re.I)),
    ("diuretic", re.compile(r"\bdiuretic\w*\b", re.I)),
    ("weight_cut_protocol", re.compile(r"\b(?:weight[-\s]*cut|acute\s+cut|cut\s+protocol|weigh-?in\s+cut)\w*\b", re.I)),
    ("fluid_restriction", re.compile(r"\b(?:restrict|cut|drop|strip)\w*\s+(?:your\s+)?(?:fluid|water)s?\b", re.I)),
    ("sodium_load", re.compile(r"\b(?:sodium|salt)\s*(?:load(?:ing)?|depletion|cut)\b", re.I)),
    ("refeed_protocol", re.compile(r"\brefeed\b", re.I)),
)


def blocked_guidance_reasons(text: Any) -> list[str]:
    """Names of the blocked-guidance rules a piece of text trips (may be empty).

    The replacement note is removed before matching. It necessarily names the
    things it is refusing to provide, so without this it would trip the very
    patterns it exists to satisfy — and scrubbed text would never read as clean.
    """
    value = str(text or "").replace(MINOR_WEIGHT_CUT_NOTE, " ")
    if not value.strip():
        return []
    return [name for name, pattern in _BLOCKED_PATTERNS if pattern.search(value)]


def contains_blocked_minor_guidance(text: Any) -> bool:
    """Whether text carries guidance an under-18 athlete must not receive."""
    return bool(blocked_guidance_reasons(text))


def scrub_minor_guidance(text: Any, *, note: str = MINOR_WEIGHT_CUT_NOTE) -> str:
    """Remove blocked guidance from markdown-ish athlete-facing text.

    Works line by line so a single offending bullet is dropped without losing
    the surrounding plan. A markdown heading that trips a pattern takes its
    whole indented/bulleted section with it — leaving "**Weight Cut Protocol
    Triggered:**" behind with its body removed would read as a broken plan and
    still signal that a cut protocol exists.

    The replacement note is appended once, only when something was removed.
    """
    original = str(text or "")
    if not original.strip():
        return original

    lines = original.splitlines()
    kept: list[str] = []
    removed = False
    dropping_section = False
    for line in lines:
        stripped = line.strip()
        if dropping_section:
            # A blank line does not end the section on its own: plan sections are
            # separated by a blank line *and* a new heading/paragraph, and a
            # trailing blank inside a bullet list is common.
            if not stripped:
                continue
            if _is_list_item(stripped) or line[:1].isspace():
                removed = True
                continue
            dropping_section = False

        if contains_blocked_minor_guidance(line):
            removed = True
            if _is_section_heading(stripped):
                dropping_section = True
            continue
        kept.append(line)

    if not removed:
        return original

    scrubbed = "\n".join(kept).rstrip()
    if note and note not in scrubbed:
        separator = "\n\n" if scrubbed else ""
        scrubbed = f"{scrubbed}{separator}- {note}"
    return scrubbed


# A markdown list item. `**Bold heading:**` also starts with `*`, so a bare
# startswith check would swallow the section *after* a removed one — the space
# is what separates a bullet from bold.
_LIST_ITEM_RE = re.compile(r"^(?:[-*+•]\s|\d+[.)]\s)")


def _is_list_item(stripped: str) -> bool:
    return bool(_LIST_ITEM_RE.match(stripped))


def _is_section_heading(stripped: str) -> bool:
    """Whether a line opens a section whose body should go with it."""
    if stripped.startswith("#"):
        return True
    # Stage 1 renders sections as bold labels ending in a colon.
    return stripped.startswith("**") and stripped.rstrip().endswith((":**", ":"))


def minor_safe_stage1_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """A Stage 1 planner payload with the weight-cut inputs neutralised.

    Marks the payload ``is_minor`` (the planner's own guard) and blanks the
    target weight so no cut percentage can be computed even if a future caller
    forgets the flag. Current bodyweight is kept: it drives macro and hydration
    personalisation, which under-18 athletes still get.
    """
    if not isinstance(payload, dict):
        return payload
    guarded = dict(payload)
    guarded["is_minor"] = True
    data = guarded.get("data")
    if isinstance(data, dict) and isinstance(data.get("fields"), list):
        guarded["data"] = {
            **data,
            "fields": [
                {**field, "value": ""}
                if isinstance(field, dict)
                and str(field.get("key") or field.get("label") or "").strip().lower()
                == "target weight (kg)"
                else field
                for field in data["fields"]
            ],
        }
    return guarded


def detect_minor_guidance_leakage(structured_plan: Any, *, is_minor: bool) -> list[str]:
    """Audit findings for blocked guidance reaching an under-18 athlete.

    Returned strings use the structured-plan audit's ``LEAKAGE:`` prefix, which
    is publication-blocking: a card that would show a child a water-cut protocol
    must not publish, even if the rest of it is good.
    """
    if not is_minor or not isinstance(structured_plan, dict):
        return []
    # Imported lazily: structured_plan_safety imports nothing from here, and a
    # module-level import would make the dependency circular if that changes.
    from api.structured_plan_safety import LEAKAGE, athlete_facing_strings

    findings: list[str] = []
    seen: set[str] = set()
    for text in athlete_facing_strings(structured_plan):
        for reason in blocked_guidance_reasons(text):
            if reason in seen:
                continue
            seen.add(reason)
            findings.append(
                f"{LEAKAGE}: under-18 athlete — blocked weight-cut/dehydration "
                f"guidance ({reason}) in athlete-facing text"
            )
    return findings


def scrub_minor_guidance_tree(node: Any) -> Any:
    """Recursively scrub blocked guidance from every string leaf of a payload.

    Blocked sentences are replaced by the safe note rather than deleted, so no
    string becomes empty and a structured plan still satisfies its schema after
    the pass.
    """
    if isinstance(node, str):
        if not contains_blocked_minor_guidance(node):
            return node
        kept = [
            sentence
            for sentence in re.split(r"(?<=[.!?])\s+", node)
            if sentence.strip() and not contains_blocked_minor_guidance(sentence)
        ]
        return " ".join(kept) if kept else MINOR_WEIGHT_CUT_NOTE
    if isinstance(node, dict):
        return {key: scrub_minor_guidance_tree(value) for key, value in node.items()}
    if isinstance(node, list):
        return [scrub_minor_guidance_tree(item) for item in node]
    return node
