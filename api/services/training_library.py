"""Deterministic source-backed search, separate from all prescription engines."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path
import re
import threading
import unicodedata

from fightcamp.training_catalogue import (
    ALIASES_FILE, DATA_DIR, MANIFEST_FILE, PHYSICAL_CLASSES, SOURCE_CLASSES,
    build_catalogue, content_hash, source_hash, strings,
)
from fightcamp.training_metadata import CONTRACT_FILES, canonical_filter, filter_label, load_projection, project_entry
from api.services.training_library_vocabulary import CONCEPTS, supports

CLASS_LABELS = {
    "strength_power": "Strength & power", "conditioning": "Conditioning",
    "technical_coordination": "Technical drills", "rehabilitation": "Rehabilitation",
    "care_instruction": "Care", "tactical_educational": "Tactical study",
    "visualisation": "Visualisation",
}
SOURCE_LABELS = {
    "exercise_bank.json": "Strength", "conditioning_bank.json": "Conditioning",
    "style_conditioning_bank.json": "Style conditioning", "style_taper_conditioning.json": "Taper conditioning",
    "technical_footwork_bank.json": "Footwork", "rehab_bank.json": "Rehab",
    "tactical_watch_bank.json": "Tactical study", "fight_visualization_bank.json": "Visualisation",
}
BODY_LABELS = {"lower_body": "Legs", "upper_body": "Upper body", "core": "Core", "full_body": "Full body"}
GUIDANCE_FIELDS = {
    "Instructions": ("instructions", "description", "notes"), "Cues": ("cue", "pro_tip"),
    "Why": ("why", "combat_carryover"), "Progress": ("progress", "progression", "progress_when"),
    "Regress": ("regress", "regression", "regress_when"), "Stop": ("stop", "stop_rules", "stop_when", "quality_stop_rule"),
}
FILTERS = ("type", "goal", "sport", "equipment", "body_focus")


def text_key(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def label(value: str) -> str:
    return {"mma": "MMA", "bjj": "BJJ", "muay_thai": "Muay Thai"}.get(value, value.replace("_", " ").replace("-", " ").capitalize())


def category_of(content_type: str) -> str:
    return "training" if content_type in PHYSICAL_CLASSES else "rehab" if content_type == "rehabilitation" else "learn"


def _known(entry: dict, field: str) -> list[str]:
    return strings(entry["raw"].get(field)) if entry["metadata"].get(field, {}).get("state") == "known" else []


def _prepare(entry: dict, *, projection: dict | None = None) -> dict:
    goals = {alias["label"] for alias in entry["aliases"]}
    goals.update(label(value) for value in _known(entry, "goals"))
    body = set(_known(entry, "body_region") + _known(entry, "target_regions"))
    body.update(v for v in _known(entry, "category") if v in BODY_LABELS)
    # Reviewed context conjunction: lower-body explosive work. Neither generic
    # power nor an anatomical label alone earns this discovery alias.
    if "lower_body" in body and "explosive" in _known(entry, "tags"):
        goals.add("Explosive legs")
    # Explicit defensive technical function, never all footwork.
    if {"defensive_exit", "takedown_defense"}.intersection(_known(entry, "tactical_function")):
        goals.add("Defensive movement")
    equipment = _known(entry, "equipment")
    equipment_known = entry["metadata"]["equipment"]["state"] == "known"
    equipment_values = set(equipment)
    projected = project_entry(entry, projection) if projection else []
    if projection and equipment_known:
        equipment_values = {value["canonical_id"] for value in projected if value["source_field"] == "equipment" and value["filter_eligible"]}
    body.update(value["canonical_id"] for value in projected if value["dimension"] == "anatomical_focus" and value["filter_eligible"])
    if equipment_known and (not equipment or set(equipment) <= {"none", "bodyweight"}):
        equipment_values = {"no_equipment"}
    facets = {
        "type": {entry["content_class"]}, "goal": goals,
        "sport": {e["value"] for e in entry["sport_evidence"]},
        "equipment": equipment_values if equipment_known else set(), "body_focus": body,
    }
    groups = entry["raw_group"] or {}
    context = " · ".join([SOURCE_LABELS.get(entry["source"], "Coordination"),
                           *[label(str(groups[f])) for f in ("location", "type") if groups.get(f)],
                           *[label(v) for f in ("sports", "styles") for v in _known(entry, f)]])
    focus = sorted(goals) or [label(v) for f in ("movement", "category", "qualities", "function") for v in _known(entry, f)][:2]
    aliases = " ".join(sorted(goals))
    metadata = " ".join(piece["text"] for piece in entry["search_evidence"] if piece["field"] not in {"name", "description", "cue", "notes", "instructions", "why"})
    descriptions = " ".join(piece["text"] for piece in entry["search_evidence"] if piece["field"] in {"description", "cue", "notes", "instructions", "why"})
    name = text_key(entry["name"])
    alias_text, metadata_text, description_text = map(text_key, (aliases, metadata, descriptions))
    discovery = [rule for rule in CONCEPTS if entry["content_class"] in PHYSICAL_CLASSES and supports(entry, rule)]
    # A reviewed display term for the explicit lower_body category lets a fighter
    # type 'legs' without inventing a training quality.
    body_text = " ".join(BODY_LABELS.get(value, label(value)) for value in body)
    gear_text = "no equipment bodyweight" if equipment_values == {"no_equipment"} else ""
    # Keep expanded discovery phrases out of the lexical word bag: otherwise a
    # hand-timing phrase plus an unrelated speed tag could manufacture a match.
    corpus = text_key(" ".join((name, alias_text, metadata_text, description_text, body_text, gear_text)))
    return {
        "entry": entry, "facets": facets, "name": name, "aliases": alias_text, "projection": projected,
        "metadata": metadata_text, "description": description_text,
        "discovery": discovery,
        "words": frozenset(corpus.split()),
        "summary": {
            "catalogue_id": entry["catalogue_id"], "name": entry["name"],
            "content_type": entry["content_class"], "category": category_of(entry["content_class"]),
            "context": context, "focus": focus, "equipment": equipment if equipment_known else None,
            "equipment_state": entry["metadata"]["equipment"]["state"],
            "exercise_key": entry["exercise_key"], "media": None,
            "selection_boundary": entry["eligibility"]["boundary"], "prescription_allowed": False,
        },
    }


@dataclass(frozen=True)
class LibraryIndex:
    signature: tuple
    revision: str
    records: tuple[dict, ...]
    by_id: dict[str, dict]
    projection: dict | None = None


class LibraryCache:
    """Cheap source stats per request; content-based public pagination revision.

    Invalid revisions fail closed: never fall back to a previously valid index.
    The lock prevents concurrent requests rebuilding the same 2,855 records.
    """
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self._lock = threading.Lock()
        self._index: LibraryIndex | None = None

    def _signature(self) -> tuple:
        sources = tuple((source, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
                     for source in (*SOURCE_CLASSES, MANIFEST_FILE, ALIASES_FILE)
                     for stat in [(self.data_dir / source).stat()])
        # Stats only invalidate this process's cache, never the public revision.
        # The reviewed vocabulary is also a cache input.
        contracts = tuple((path.name, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
                          for path in CONTRACT_FILES for stat in [path.stat()])
        return (*sources, *contracts, ("discovery_vocabulary", repr(CONCEPTS)))

    def _revision(self) -> str:
        # Include every source and review input, including files with no entries.
        # Normalise checkout line endings just like the catalogue's source hashes.
        sources = [(source, source_hash((self.data_dir / source).read_bytes()))
                   for source in (*SOURCE_CLASSES, MANIFEST_FILE, ALIASES_FILE)]
        contracts = [(path.name, source_hash(path.read_bytes())) for path in CONTRACT_FILES]
        return content_hash({"sources": sources, "projection_contracts": contracts, "discovery_vocabulary": [asdict(rule) for rule in CONCEPTS]})

    def get(self) -> LibraryIndex:
        with self._lock:
            signature = self._signature()
            if self._index is not None and self._index.signature == signature:
                return self._index
            revision = self._revision()
            entries = build_catalogue(self.data_dir)
            projection = load_projection()
            if self._signature() != signature:
                raise ValueError("Catalogue changed while loading")
            records = tuple(_prepare(entry, projection=projection) for entry in entries)
            duplicate_contexts = defaultdict(list)
            for record in records:
                duplicate_contexts[(record["summary"]["category"], record["name"], record["summary"]["context"])].append(record)
            for group in duplicate_contexts.values():
                if len(group) < 2:
                    continue
                notes = [" ".join(_known(r["entry"], "notes")) for r in group]
                for ordinal, (record, note) in enumerate(zip(group, notes), start=1):
                    # Source wording distinguishes repeated pathway variants;
                    # identical/absent notes use neutral numbered variants.
                    suffix = note if all(notes) and len(set(notes)) == len(group) else f"Variant {ordinal}"
                    record["summary"]["context"] += f" · {suffix}"
            self._index = LibraryIndex(signature, revision, records, {r["entry"]["catalogue_id"]: r for r in records}, projection)
            return self._index


cache = LibraryCache()


def _score(record: dict, query: str, matches: dict[str, dict[str, int]], groups: list | None = None) -> int | None:
    if not query:
        return 0
    terms = _query_terms(query)
    words = record["words"]
    penalties = 0
    semantic_scores = []
    for chunk, rules in groups or [(terms, ())]:
        supported = [rule for rule in rules if rule in record.get("discovery", [])]
        literal = all(set(matches[term]).intersection(words) for term in chunk)
        # Recognised fighter intents need a phrase/name match or supported
        # concept. Scattered mechanical-risk words cannot satisfy the intent.
        phrase = " ".join(chunk)
        strong_literal = any(phrase in record.get(field, "") for field in ("name", "aliases", "metadata", "description")) or all(
            any(word.startswith(term) for word in record["name"].split()) for term in chunk)
        if supported:
            semantic_scores.append(max(450 if rule.related else
                800 if any(text_key(phrase) in record.get("aliases", "") for phrase in rule.phrases) else 700 for rule in supported))
        elif not literal or (rules and not strong_literal):
            return None
        for term in chunk:
            costs = [cost for word, cost in matches[term].items() if word in words]
            if costs:
                penalties += min(costs)
    if query == record["name"]:
        return 1000
    scores = [400]
    for field, score in (("name", 900), ("aliases", 800), ("metadata", 650), ("description", 500)):
        if query in record.get(field, ""):
            scores.append(score)
    if all(any(word.startswith(term) for word in record["name"].split()) for term in terms):
        scores.append(850)
    if semantic_scores:
        scores.append(min(semantic_scores))
    return max(scores) - penalties


def _query_terms(query: str) -> list[str]:
    words = query.split()
    # A small closed list permits "I want to hit harder" without treating
    # unsupported training concepts as synonyms. Single-word searches survive.
    meaningful = [word for word in words if word not in {"i", "want", "to", "my", "for", "the", "a", "an", "and", "with"}]
    return meaningful or words


def _word_matches(terms: list[str], vocabulary: set | frozenset) -> dict:
    return {term: {word: 0 if term == word else 1 if word.startswith(term) else 2
                   for word in vocabulary if term == word or
                   (len(term) >= 3 and word.startswith(term)) or
                   (len(term) >= 4 and abs(len(term) - len(word)) <= 2 and SequenceMatcher(None, term, word).ratio() >= .84)}
            for term in terms}


def _canonical_query(record: dict, query: str, projection: dict | None) -> str:
    for mapping in (projection or {}).get("mappings", []):
        evidence = next((value for value in record.get("projection", [])
                         if value["audit_decision"] == mapping["audit_decision"] and value["filter_eligible"]), None)
        if not evidence:
            continue
        phrases = {text_key(value) for value in (*mapping["source_values"], mapping["label"])}
        for phrase in sorted(phrases, key=lambda value: (-len(value), value)):
            pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
            if re.search(pattern, query):
                query = re.sub(pattern, text_key(evidence["source_value"]), query)
                break
    return query


def _intent_groups(query: str) -> list:
    terms = _query_terms(query)
    phrases = [(tuple(_query_terms(text_key(phrase))), rule) for rule in CONCEPTS for phrase in rule.phrases]
    groups = []
    position = 0
    while position < len(terms):
        candidates = []
        for words, rule in phrases:
            chunk = terms[position:position + len(words)]
            if len(chunk) == len(words) and all(term == word or (len(term) >= 3 and word.startswith(term)) or
                    (len(term) >= 4 and abs(len(term) - len(word)) <= 2 and SequenceMatcher(None, term, word).ratio() >= .84)
                    for term, word in zip(chunk, words)):
                candidates.append((len(words), rule))
        length = max((length for length, _ in candidates), default=1)
        groups.append((terms[position:position + length], tuple(dict.fromkeys(rule for size, rule in candidates if size == length))))
        position += length
    return groups


def _discovery_match(record: dict, query: str, groups: list) -> str | None:
    terms = set(_query_terms(query))
    original = set(text_key(" ".join(record.get(field, "") for field in ("name", "aliases", "metadata", "description"))).split())
    if not terms or terms <= original:
        return None
    for _, rules in groups:
        supported = [rule for rule in rules if rule in record.get("discovery", [])]
        if supported:
            rule = next((rule for rule in supported if not rule.related), supported[0])
            return f"{'Related' if rule.related else 'Matches'} · {rule.label}"
    return None


def _matches(record: dict, filters: dict, *, except_field: str | None = None) -> bool:
    for field, selected in filters.items():
        if selected and field != except_field:
            values = record["facets"][field]
            if selected not in values and not (field == "sport" and "universal" in values):
                return False
    return True


def search(index: LibraryIndex, *, q: str = "", category: str = "training", filters: dict | None = None, offset: int = 0, limit: int = 24) -> dict:
    filters = {field: canonical_filter(field, value, category, index.projection) for field, value in (filters or {}).items()}
    ranked = []
    query = text_key(q)
    groups = _intent_groups(query) if query and category == "training" else []
    vocabulary = set().union(*(r["words"] for r in index.records if r["summary"]["category"] == category))
    matches = {term: {word: 0 if term == word else 1 if word.startswith(term) else 2
                      for word in vocabulary if term == word or
                      (len(term) >= 3 and word.startswith(term)) or
                      (len(term) >= 4 and abs(len(term) - len(word)) <= 2 and SequenceMatcher(None, term, word).ratio() >= .84)}
               for term in _query_terms(query)}
    for record in index.records:
        if record["summary"]["category"] != category:
            continue
        # Suspect equipment declarations remain source evidence, but cannot
        # establish that a climbing drill is battle-rope work.
        blocked_phrases = [text_key(value) for item in record.get("projection", []) if not item["filter_eligible"]
                           for mapping in (index.projection or {}).get("mappings", []) if mapping["audit_decision"] == item["audit_decision"]
                           for value in mapping["source_values"]]
        if any(re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", query) for phrase in blocked_phrases):
            continue
        score = _score(record, query, matches, groups)
        # Only previously unmatched lexical queries can use a reviewed naming
        # equivalent. Existing intent/ranking evidence stays unchanged.
        if score is None and not any(rules for _, rules in groups):
            alternate = _canonical_query(record, query, index.projection)
            if alternate != query:
                alternate_score = _score(record, alternate, _word_matches(_query_terms(alternate), record["words"]), _intent_groups(alternate) if category == "training" else [])
                score = min(650, alternate_score) if alternate_score is not None else None
        if score is not None:
            ranked.append((score, record))
    facets = {}
    for field in FILTERS:
        counts = Counter(value for _, r in ranked if _matches(r, filters, except_field=field) for value in r["facets"][field])
        facets[field] = [{"value": value, "label": filter_label(field, value, index.projection) or CLASS_LABELS.get(value, BODY_LABELS.get(value, "No equipment" if value == "no_equipment" else label(value))), "count": count}
                         for value, count in sorted(counts.items(), key=lambda pair: label(pair[0]))]
    selected = [r for score, r in sorted(ranked, key=lambda pair: (-pair[0], pair[1]["name"], pair[1]["entry"]["catalogue_id"])) if _matches(r, filters)]
    return {"entries": [{**r["summary"], "discovery_match": _discovery_match(r, query, groups)} for r in selected[offset:offset + limit]], "total": len(selected),
            "catalogue_total": len(index.records), "offset": offset, "limit": limit,
            "next_offset": offset + limit if offset + limit < len(selected) else None,
            "revision": index.revision, "facets": facets}


def preview(record: dict) -> dict:
    entry = record["entry"]
    return {**record["summary"], "source": entry["source"], "source_revision": entry["source_sha256"],
            "metadata_projection": record.get("projection", []),
            "equipment_source": {"state": entry["metadata"]["equipment"]["state"], "raw": entry["raw"].get("equipment"),
                                 "guidance": {f: entry["raw"][f] for f in ("name", "equipment_note", "instructions", "notes", "description") if f in entry["raw"]}},
            "row_revision": entry["row_sha256"], "guidance": {
                title: list(dict.fromkeys(value for field in fields for value in _known(entry, field)))
                for title, fields in GUIDANCE_FIELDS.items() if any(_known(entry, field) for field in fields)
            }}
