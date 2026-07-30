"""Voice rules applied to every Stage 2 model response before it is used.

The em dash is the single clearest tell that a block of text was produced by a
language model rather than written by a coach. Athletes read this plan as
coaching, so the tell matters: a plan that reads as machine output is trusted
less than the same plan written plainly, whatever its actual quality.

The prompt asks the model not to use them (RULE 11, OUTPUT DISCIPLINE in
``fightcamp/stage2_payload.py``). This module is what makes that hold. A style
instruction is a preference the model weighs against everything else in a very
long prompt, and it loses that fight often enough to matter; a deterministic
pass over the response does not lose it at all. Keep both: the prompt gets most
of the way there and produces better sentences than a rewrite can, and this
catches the remainder.

Scope is deliberately narrow. This normalises dash PUNCTUATION only. It never
touches hyphens inside words ("coach-led", "reps-in-reserve") or inside numeric
ranges ("3-5 reps", "45-60 sec"), because those are correct and rewriting them
would corrupt real prescriptions. It runs on structured JSON responses as well
as markdown, which is safe: every substitution stays inside a JSON string value
and introduces no JSON syntax characters.
"""

from __future__ import annotations

import re

# Em dash, en dash, horizontal bar, and the "minus sign" a model occasionally
# reaches for. All read as the same punctuation to an athlete.
_UNICODE_DASHES = "—―–−"

# A structured response may carry the same characters as JSON escapes rather than
# literal UTF-8. Matching both means the guarantee does not depend on which
# encoding the model happened to choose. Substituting for an escape is equally
# safe: inside a JSON string the escape IS the character.
_ESCAPED_DASHES = ("\\u2014", "\\u2015", "\\u2013", "\\u2212")
_UNICODE_DASH_CLASS = (
    f"(?:[{_UNICODE_DASHES}]|" + "|".join(re.escape(seq) for seq in _ESCAPED_DASHES) + ")"
)

# A range is the one place a dash between two values is correct. Normalising it
# to a plain hyphen keeps "3-5 reps" and "45-60 sec" readable and, importantly,
# takes it out of reach of the clause rules below.
_NUMERIC_RANGE = re.compile(rf"(?<=\d)[ \t]*(?:{_UNICODE_DASH_CLASS}|-)[ \t]*(?=\d)")

# A dash opening a line is a bullet, not punctuation. The Stage 2 prompt itself
# writes fight-week rules this way, so the model copies the habit.
_LEADING_BULLET = re.compile(rf"(?m)^([ \t]*)(?:{_UNICODE_DASH_CLASS})+[ \t]+")

# Everything left is a clause break. A unicode dash counts with or without
# surrounding spaces; an ASCII hyphen only counts when spaced on BOTH sides,
# which is never true of a compound word or a range.
_CLAUSE_DASH = re.compile(rf"[ \t]*{_UNICODE_DASH_CLASS}+[ \t]*|[ \t]+-+[ \t]+")

# Punctuation that already closes the clause, so the dash was decoration.
_CLOSING_PUNCTUATION = ",;:.!?"

# Tidy-ups for the few cases where a replacement meets punctuation the model
# had already written.
_DOUBLED_PUNCTUATION = re.compile(r"([,.;:])[ \t]*([,.;:])")
_SPACE_BEFORE_PUNCTUATION = re.compile(r"[ \t]+([,.;:!?])")


def _is_heading_line(source: str, position: int) -> bool:
    """True when ``position`` sits on a markdown heading line ("## Week 1 — SPP")."""
    line_start = source.rfind("\n", 0, position) + 1
    return source[line_start:position].lstrip().startswith("#")


def _replace_clause_dash(match: re.Match[str]) -> str:
    """Replace one clause dash with the punctuation a person would have used.

    On a heading the dash introduces a qualifier, so it becomes a colon: a full
    stop inside a heading reads worse than the dash did. In prose, a dash before
    a capital letter is doing the work of a full stop and before anything else
    the work of a comma. Where the sentence is already punctuated, or the dash
    dangles at the edge of the text or a line, it is dropped rather than
    replaced, so no punctuation is invented.
    """
    source = match.string
    before = source[: match.start()].rstrip()
    after = source[match.end() :]

    if not before or not after or after[0] == "\n":
        return ""
    if before[-1] in _CLOSING_PUNCTUATION:
        return " "
    if _is_heading_line(source, match.start()):
        return ": "
    if after[0].isupper():
        return ". "
    return ", "


def strip_model_dashes(text: str) -> str:
    """Rewrite model dash punctuation into plain coach punctuation.

    Returns ``text`` unchanged when it contains no dash punctuation, so the
    common case costs one scan and nothing else.
    """
    if not text:
        return text
    if (
        not any(dash in text for dash in _UNICODE_DASHES)
        and not any(escape in text for escape in _ESCAPED_DASHES)
        and " - " not in text
    ):
        return text

    text = _NUMERIC_RANGE.sub("-", text)
    text = _LEADING_BULLET.sub(r"\1- ", text)
    text = _CLAUSE_DASH.sub(_replace_clause_dash, text)
    text = _DOUBLED_PUNCTUATION.sub(r"\1", text)
    text = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", text)
    return text
