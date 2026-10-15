"""Small, lossless coaching projection for exercise cards, not a dose authority."""
import re
from copy import deepcopy


def _text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _unique(values):
    seen = set()
    result = []
    for value in values or []:
        text = _text(value)
        key = re.sub(r"[\W_]+", " ", text.casefold()).strip()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def short_cue(text):
    """Prefer a complete authored clause; never truncate a warning at word seven.

    The full original is retained as coaching detail. If a safe short clause
    cannot be extracted, keep the longer cue rather than cut technical meaning.
    """
    text = re.sub(r"^Cue:\s*", "", _text(text), flags=re.I)
    if len(text.split()) <= 7:
        return text
    # Do not split a negated or conditional instruction into an unsafe fragment.
    if re.search(r"\b(?:unless|until|without|only if|do not|don't|never)\b", text, re.I):
        return text
    clauses = []
    for clause in re.split(r"[;.!?]|,\s+|\s+and\s+", text):
        clause = clause.strip(" ,;:")
        if 2 <= len(clause.split()) <= 7 and not re.match(r"^(?:if|when|or|but)\b", clause, re.I):
            clauses.append(clause)
    if clauses:
        if len(clauses) > 1 and re.match(r"^(?:set up|get in)\b", clauses[0], re.I):
            clauses = clauses[1:]
        selected = [clauses[0]]
        for clause in clauses[1:]:
            if len((" ".join([*selected, clause])).split()) <= 7:
                selected.append(clause)
        lead = "; ".join(selected)
        return lead[0].upper() + lead[1:]
    return text


def readable_stop(rules):
    rules = _unique(rules)
    if len(rules) <= 1:
        return rules
    conditions = []
    for rule in rules:
        # Keep exceptional instructions (e.g. seek medical help) verbatim.
        if re.search(r"\b(?:seek|call|medical|emergency)\b", rule, re.I):
            return [" ".join(re.sub(r"^(if|when)\b", lambda m: "Stop " + m[1].lower(), r,
                                    flags=re.I).rstrip(". ") + "." for r in rules)]
        condition = re.sub(r"^(?:stop(?:\s+(?:the\s+)?(?:set|effort|hold|swim|work))?\s+)?"
                           r"(?:if|when|for|on)\s+", "", rule, flags=re.I).rstrip(". ")
        if re.match(r"^(?:stop|end|seek|call|do not|never)\b", condition, re.I):
            return [" ".join(r.rstrip(". ") + "." for r in rules)]
        conditions.append(condition if condition.split()[0].isupper() else condition[0].lower() + condition[1:])
    conditions = _unique(conditions)
    conditions = [c for c in conditions if not any(
        c != other and re.search(r"(?:^|, | or )" + re.escape(c) + r"(?:$|,| or )", other, re.I)
        for other in conditions)]
    joined = " or ".join(conditions) if len(conditions) <= 2 else ", ".join(conditions[:-1]) + ", or " + conditions[-1]
    return ["Stop if " + joined + "."]



def compact_instruction(text: str) -> str:
    """One ≤9-word cue without chopping conditional or negated instructions."""
    value = re.sub(r"^(?:Cue|Easier|Progress|Stop):\s*", "", _text(text), flags=re.I)
    if len(value.split()) <= 9:
        return value
    if re.search(r"\b(?:unless|only if|do not|never|without)\b", value, re.I):
        return value  # A qualifier is safer than a misleading clipped command.
    clauses = [part.strip(" .;,") for part in re.split(r";|(?<=[.!?])\s+|,\s+| and ", value)]
    return next((part for part in clauses if 2 <= len(part.split()) <= 9), value)


def compact_stop(text: str) -> str:
    """Shorten standard stop criteria, never removing a medical escalation."""
    value = _text(text)
    if len(value.split()) <= 9:
        return value
    if re.search(r"\b(?:medical|emergency|clinician|seek|call|faint|chest pain)\b", value, re.I):
        return value
    value = re.sub(r"^(?:End|Stop) (?:the |this )?(?:set|effort|work|hold|drill|session)\s+", "Stop ", value, flags=re.I)
    value = re.sub(r"\b(?:appears|develops|occurs|is present)\b", "starts", value, flags=re.I)
    value = re.sub(r"\b(?:you cannot|you can no longer)\b", "you can't", value, flags=re.I)
    value = re.sub(r"\b(?:or if|or when)\b", "or", value, flags=re.I)
    if len(value.split()) <= 9:
        return value
    return value  # Preserve all stop triggers rather than hide a hazard.


def compact_progress(text: str) -> str:
    """Show an authorised one-variable numerical advance without prose."""
    value = _text(text)
    # numerical_guidance generated this form from exact next-exposure doses.
    match = re.search(r"\badd\s+(\d+(?:\.\d+)?)\s*(kg|lb|reps?|sets?|rounds?|m|min|sec)\b", value, re.I)
    if match and "Next D-" in value:
        unit = match[2].lower()
        suffix = "" if unit in {"kg", "lb", "m"} else " "
        return f"Add +{match[1]}{suffix}{unit}"
    if len(value.split()) <= 9:
        return value
    return compact_instruction(value)

def concise_coaching(fields):
    """One Easier, one readable Stop, short lead cue plus intact source detail.

    Idempotent by construction: recovery selects, it never appends an alternative
    to an already actionable regression. Different wording of the same numeric
    reduction therefore cannot multiply on subsequent reads.
    """
    result = deepcopy(fields)
    cues = _unique([re.sub(r"^Cue:\s*", "", _text(cue), flags=re.I)
                    for cue in result.get("coaching_cues") or []])
    if cues:
        # One athlete-visible instruction. The old [short, original] projection
        # produced two near-identical cues, plus a "Coaching cues" accordion.
        result["coaching_cues"] = [compact_instruction(short_cue(cues[0]))]
    else:
        result["coaching_cues"] = []
    options = _unique(result.get("regression_options"))
    result["regression_options"] = [compact_instruction(options[0])] if options else []
    stops = readable_stop(result.get("stop_rules"))
    result["stop_rules"] = [compact_stop(stops[0])] if stops else []
    if result.get("progression_rule"):
        result["progression_rule"] = compact_progress(result["progression_rule"])
    return result
