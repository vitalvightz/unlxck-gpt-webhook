from __future__ import annotations

import json
from pathlib import Path

path = Path("data/bank_inferred_tags.json")
rows = json.loads(path.read_text(encoding="utf-8"))
path.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
