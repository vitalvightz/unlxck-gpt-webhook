"""Exact inverse of the 14 reviewed duplicate-token edits, for audit replay only.

Never a runtime bank loader. Frozen baselines still verify reconstructed bytes;
neither identities nor historical clinical records are rewritten.
"""
from pathlib import Path
import json

from fightcamp.training_catalogue import content_hash

ROOT = Path(__file__).resolve().parents[1]


def source_changes():
    return json.loads((ROOT / "tools/safety_metadata_source_changes.json").read_bytes())["changes"]


def original_safety_source(relative: str, data: bytes) -> bytes:
    for change in source_changes():
        if relative == "data/style_taper_conditioning.json":
            row = next((r for r in json.loads(data) if content_hash(r) == change["after_sha256"]), None)
            if row is None or row.get("mechanical_risk_tags") != change["after"]["mechanical_risk_tags"]:
                raise ValueError("Safety source history drift: " + change["catalogue_id"])
            old = {**row, **change["before"]}
            if content_hash(old) != change["before_sha256"]:
                raise ValueError("Safety source changes unrelated fields")

            def encoded(value):
                return ("  " + json.dumps(value, ensure_ascii=False, indent=2).replace("\n", "\n  ")).encode()

            if data.count(encoded(row)) != 1:
                raise ValueError("Ambiguous safety source history")
            data = data.replace(encoded(row), encoded(old))
        elif relative == "data/training_catalogue_ids.json":
            if data.count(change["after_sha256"].encode()) != 1:
                raise ValueError("Safety manifest history drift")
            data = data.replace(change["after_sha256"].encode(), change["before_sha256"].encode())
    return data
