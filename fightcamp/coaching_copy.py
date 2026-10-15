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



def compact_coaching_line(value):
    """Make an actionable coaching line short without changing prescribed work."""
    text = _text(value).rstrip(".")
    text = re.sub(r";\s*keep (?:effort|rest|rests).*$", "", text, flags=re.I)
    text = re.sub(
        r"\s+instead of\s+[\d.]+\s*(?:min|sec|m|reps?|sets?|rounds?)\b.*$",
        "", text, flags=re.I,
    )
    if len(text.split()) <= 9:
        return text
    # Prefer complete clauses over clipping a sentence mid-instruction.
    for clause in re.split(r"\s*;\s*|(?<=\.)\s+", text):
        if 2 <= len(clause.split()) <= 9:
            return clause.rstrip(".")
    return text  # Preserve any unbreakable dose or safety instruction.


def compact_stop(value):
    """Compress known stop triggers, never drop an unrecognised safety signal."""
    text = _text(value).rstrip(".")
    text = re.sub(
        r"^(?:End|Stop) (?:the|this) (?:set|effort|work|hold|swim)\s+",
        "Stop ", text, flags=re.I,
    )
    if len(text.split()) <= 9:
        return text
    trigger_patterns = (
        ("chest discomfort", r"chest (?:discomfort|pain)"),
        ("dizziness", r"dizz(?:y|iness)"),
        ("breathlessness", r"(?:breathlessness|breathing difficulty|unusual breath)"),
        ("pain", r"\bpain\b"),
        ("balance loss", r"(?:balance|unstable|instability|landings?)"),
        ("speed loss", r"(?:speed drops?|slows?|slower|speed deteriorates)"),
        ("form loss", r"(?:form|control|technique|quality|posture|trunk|guard return|shape)"),
    )
    triggered = [label for label, pattern in trigger_patterns if re.search(pattern, text, re.I)]
    if 0 < len(triggered) <= 3:
        short = "Stop for " + ", ".join(triggered)
        if len(short.split()) <= 9:
            return short
    return text  # Medical safety criteria take priority over a word count.

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
        lead = short_cue(cues[0])
        result["coaching_cues"] = [lead]  # Exactly one actionable cue; original stays in bank.
    options = _unique(result.get("regression_options"))
    result["regression_options"] = options[:1]
    result["stop_rules"] = readable_stop(result.get("stop_rules"))
    return result
