"""Deterministic source-backed search, separate from all prescription engines."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
import hashlib
from pathlib import Path
import re
import threading
import unicodedata

from fightcamp.training_catalogue import (
    ALIASES_FILE, DATA_DIR, MANIFEST_FILE, PHYSICAL_CLASSES, SOURCE_CLASSES,
    build_catalogue, strings,
)

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


def _prepare(entry: dict) -> dict:
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
    if equipment_known and (not equipment or equipment_values <= {"none", "bodyweight"}):
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
    # A reviewed display term for the explicit lower_body category lets a fighter
    # type 'legs' without inventing a training quality.
    body_text = " ".join(BODY_LABELS.get(value, label(value)) for value in body)
    gear_text = "no equipment bodyweight" if equipment_values == {"no_equipment"} else ""
    corpus = text_key(" ".join((name, alias_text, metadata_text, description_text, body_text, gear_text)))
    return {
        "entry": entry, "facets": facets, "name": name, "aliases": alias_text,
        "metadata": metadata_text, "description": description_text,
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


class LibraryCache:
    """Cheap source stats per request; rebuild only on a revision change.

    Invalid revisions fail closed: never fall back to a previously valid index.
    The lock prevents concurrent requests rebuilding the same 2,855 records.
    """
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self._lock = threading.Lock()
        self._index: LibraryIndex | None = None

    def _signature(self) -> tuple:
        return tuple((source, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
                     for source in (*SOURCE_CLASSES, MANIFEST_FILE, ALIASES_FILE)
                     for stat in [(self.data_dir / source).stat()])

    def get(self) -> LibraryIndex:
        with self._lock:
            signature = self._signature()
            if self._index is not None and self._index.signature == signature:
                return self._index
            entries = build_catalogue(self.data_dir)
            if self._signature() != signature:
                raise ValueError("Catalogue changed while loading")
            records = tuple(_prepare(entry) for entry in entries)
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
            revision = hashlib.sha256(repr(signature).encode()).hexdigest()
            self._index = LibraryIndex(signature, revision, records, {r["entry"]["catalogue_id"]: r for r in records})
            return self._index


cache = LibraryCache()


def _score(record: dict, query: str, matches: dict[str, dict[str, int]]) -> int | None:
    if not query:
        return 0
    terms = query.split()
    words = record["words"]
    # Bound fuzzy work to spelling variations, not arbitrary semantic guesses.
    penalties = 0
    for term in terms:
        costs = [cost for word, cost in matches[term].items() if word in words]
        if not costs:
            return None
        penalties += min(costs)
    if query == record["name"]:
        return 1000
    for field, score in (("name", 900), ("aliases", 800), ("metadata", 650), ("description", 500)):
        if query in record[field]:
            return score - penalties
    if all(any(word.startswith(term) for word in record["name"].split()) for term in terms):
        return 850 - penalties
    return 400 - penalties


def _matches(record: dict, filters: dict, *, except_field: str | None = None) -> bool:
    for field, selected in filters.items():
        if selected and field != except_field:
            values = record["facets"][field]
            if selected not in values and not (field == "sport" and "universal" in values):
                return False
    return True


def search(index: LibraryIndex, *, q: str = "", category: str = "training", filters: dict | None = None, offset: int = 0, limit: int = 24) -> dict:
    filters = filters or {}
    ranked = []
    query = text_key(q)
    vocabulary = set().union(*(r["words"] for r in index.records if r["summary"]["category"] == category))
    matches = {term: {word: 0 if term == word else 1 if word.startswith(term) else 2
                      for word in vocabulary if term == word or
                      (len(term) >= 3 and word.startswith(term)) or
                      (len(term) >= 4 and abs(len(term) - len(word)) <= 2 and SequenceMatcher(None, term, word).ratio() >= .84)}
               for term in query.split()}
    for record in index.records:
        if record["summary"]["category"] != category:
            continue
        score = _score(record, query, matches)
        if score is not None:
            ranked.append((score, record))
    facets = {}
    for field in FILTERS:
        counts = Counter(value for _, r in ranked if _matches(r, filters, except_field=field) for value in r["facets"][field])
        facets[field] = [{"value": value, "label": CLASS_LABELS.get(value, BODY_LABELS.get(value, "No equipment" if value == "no_equipment" else label(value))), "count": count}
                         for value, count in sorted(counts.items(), key=lambda pair: label(pair[0]))]
    selected = [r for score, r in sorted(ranked, key=lambda pair: (-pair[0], pair[1]["name"], pair[1]["entry"]["catalogue_id"])) if _matches(r, filters)]
    return {"entries": [r["summary"].copy() for r in selected[offset:offset + limit]], "total": len(selected),
            "catalogue_total": len(index.records), "offset": offset, "limit": limit,
            "next_offset": offset + limit if offset + limit < len(selected) else None,
            "revision": index.revision, "facets": facets}


def preview(record: dict) -> dict:
    entry = record["entry"]
    return {**record["summary"], "source": entry["source"], "source_revision": entry["source_sha256"],
            "row_revision": entry["row_sha256"], "guidance": {
                title: list(dict.fromkeys(value for field in fields for value in _known(entry, field)))
                for title, fields in GUIDANCE_FIELDS.items() if any(_known(entry, field) for field in fields)
            }}
