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
#
# The minus sign earns its place here and is also the reason the signed-number
# and range rules below run FIRST. Any of these characters can be a minus or a
# range separator instead of punctuation, and rewriting one of those as a comma
# does not change the plan's typography, it changes its numbers.
_UNICODE_DASHES = "—―–−"

# A structured response may carry the same characters as JSON escapes rather than
# literal UTF-8. Matching both means the guarantee does not depend on which
# encoding the model happened to choose. Substituting for an escape is equally
# safe: inside a JSON string the escape IS the character.
_ESCAPED_DASHES = ("\\u2014", "\\u2015", "\\u2013", "\\u2212")
_UNICODE_DASH_CLASS = (
    f"(?:[{_UNICODE_DASHES}]|" + "|".join(re.escape(seq) for seq in _ESCAPED_DASHES) + ")"
)

# --- Stage 1: every dash that belongs to a VALUE becomes a plain hyphen -------
#
# Run before anything treats a dash as punctuation. Each of these is a position
# where a dash carries meaning, so rewriting one into a comma would change what
# the plan prescribes rather than how it reads. Normalising them to ASCII first
# also means the range rules in stage 2 have a single form to match, instead of
# every rule having to repeat the unicode alternation.

# A label separator between a letter and its number: "D-10", "Week-3". Letter to
# LETTER is deliberately excluded, since "round—remove" is a real clause break.
_LABEL_SEPARATOR = re.compile(rf"(?<=[A-Za-z]){_UNICODE_DASH_CLASS}(?=\d)")

# A sign bound to the digits that follow it: "-5 kg" is a prescription. Requires
# a non-word character before, so "coach-led" and "D-10" can never match.
_SIGNED_NUMBER = re.compile(rf"(?<![\w\d]){_UNICODE_DASH_CLASS}(?=\d)")

# A separator with a number on both sides: "3–5", "45 – 60", "-5 – -1". The
# lookahead allows a sign so a range of negative values is still recognised as
# one range. A digit is required BEFORE, which is what keeps this off ordinary
# prose that happens to be followed by a number ("cut a round — 5 left").
_RANGE_SEPARATOR = re.compile(
    rf"(?<=\d)[ \t]*{_UNICODE_DASH_CLASS}[ \t]*(?=-?\d)"
)

# --- Stage 2: ranges, now uniformly ASCII ------------------------------------

# A signed range renders as "to": "-5 - -1" is unreadable, and "-5--1" worse.
_SIGNED_RANGE = re.compile(r"(?<=\d)[ \t]*-[ \t]*(?=-\d)")

# A plain range tightens to a bare hyphen: "45 - 60 sec" -> "45-60 sec".
_NUMERIC_RANGE = re.compile(r"(?<=\d)[ \t]*-[ \t]*(?=\d)")

# A range between two countdown labels ("D-10 - D-1"). Its separator sits
# between a digit and a LETTER, the one range position no stage-1 rule
# normalises, so it still has to match both dash forms itself. Without it the
# clause rule sees a capital D next and splits the span into two sentences.
# Rendered as "to", which is how the plan prompt already writes countdown spans.
_COUNTDOWN_RANGE = re.compile(
    rf"(D-\d+)[ \t]*(?:{_UNICODE_DASH_CLASS}|-)[ \t]*(?=D-\d)", re.IGNORECASE
)

# A dash opening a line is a bullet, not punctuation. The Stage 2 prompt itself
# writes fight-week rules this way, so the model copies the habit. The trailing
# space is optional so that every line-leading dash is converted here; anything
# left behind would be picked up by the clause rule and flattened into prose.
# The lookahead keeps a bare dash with nothing after it from becoming an empty
# bullet; it falls through to the clause rule, which drops it.
_LEADING_BULLET = re.compile(rf"(?m)^([ \t]*)(?:{_UNICODE_DASH_CLASS})+[ \t]*(?=\S)")

# Everything left is a clause break. A unicode dash counts with or without
# surrounding spaces; an ASCII hyphen only counts when spaced on both sides AND
# preceded by a non-space on the same line. That last guard is what stops this
# rule eating the indented bullets _LEADING_BULLET has just written: "  - bar"
# is spaced-hyphen-spaced too, and without the guard a nested fight-week list
# collapses into one comma-joined line.
_CLAUSE_DASH = re.compile(rf"[ \t]*{_UNICODE_DASH_CLASS}+[ \t]*|(?<=\S)[ \t]+-+[ \t]+")

# Punctuation that already closes the clause, so the dash was decoration.
_CLOSING_PUNCTUATION = ",;:.!?"


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

    Punctuation the model already wrote always wins. Deciding that here, at the
    replacement boundary, is what keeps this from needing a global cleanup pass
    afterwards: one that collapsed adjacent punctuation across the whole
    response would also flatten legitimate ellipses into "..".
    """
    source = match.string
    before = source[: match.start()].rstrip()
    after = source[match.end() :]

    if not before or not after or after[0] == "\n":
        return ""
    if after[0] in _CLOSING_PUNCTUATION:
        # The clause is already closed on the far side; adding to it would double
        # the punctuation.
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

    # Order matters. Every dash belonging to a value is normalised to a plain
    # hyphen first, then the ranges are read off that single form, and only what
    # survives both is treated as punctuation. A label, a sign, or a range can
    # therefore never be rewritten into a comma.
    text = _LABEL_SEPARATOR.sub("-", text)
    text = _SIGNED_NUMBER.sub("-", text)
    text = _RANGE_SEPARATOR.sub("-", text)

    text = _SIGNED_RANGE.sub(" to ", text)
    text = _NUMERIC_RANGE.sub("-", text)
    text = _COUNTDOWN_RANGE.sub(r"\1 to ", text)

    text = _LEADING_BULLET.sub(r"\1- ", text)
    return _CLAUSE_DASH.sub(_replace_clause_dash, text)
