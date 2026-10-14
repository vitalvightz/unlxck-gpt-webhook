"""Replay the single reviewed round-length edit for historical audit evidence.

Never used by selection, dosing or catalogue identity. Frozen audit digests
remain unchanged and still reject every unrelated byte/content edit.
"""
import json

from fightcamp.training_catalogue import content_hash

BEFORE = "f0c9e109d33804e1181f7692924354446a38acd7a1babc6752d0498c53c4987f"
AFTER = "408d6f76d8c5ccabbb084fa34ab1e443d76df37554050a6547441501135b5729"


def pre_combat_round_source(relative: str, data: bytes) -> bytes:
    data = data.replace(b"\r\n", b"\n")
    if relative == "data/style_conditioning_bank.json":
        rows = json.loads(data)
        row = next(r for r in rows if r.get("name") == "Pressure Combination Rounds")
        if content_hash(row) == BEFORE:
            return data
        if content_hash(row) != AFTER:
            raise ValueError("Unreviewed Pressure Combination Rounds drift")
        original = {k: v for k, v in row.items() if k != "round_based"}
        assert content_hash(original) == BEFORE
        def encoded(value):
            return ("  " + json.dumps(value, ensure_ascii=False, indent=2).replace("\n", "\n  ")).encode()
        if data.count(encoded(row)) != 1:
            raise ValueError("Ambiguous combat round metadata edit")
        return data.replace(encoded(row), encoded(original))
    if relative == "data/training_catalogue_ids.json":
        # The same catalogue identity is bound to the new content hash. Only
        # this reviewed binding is reversed; the frozen file digest checks IDs.
        if data.count(AFTER.encode()) != 1:
            raise ValueError("Unreviewed combat round identity binding")
        return data.replace(AFTER.encode(), BEFORE.encode())
    return data
