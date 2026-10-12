"""Observe session_composition strength caps and trunk records (read-only).

Usage: python trace_trunk.py            # known case, no injury
       python trace_trunk.py '{"foot": true}'
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from fightcamp import session_composition as sc  # noqa: E402

_original_select = sc._select_bounded_records
_original_trunk = sc._trunk_strength_selected
calls = []


def _observed_select(records, **kw):
    selected, dropped = _original_select(records, **kw)
    calls.append((
        kw,
        [(r["name"], r["quality_class"], r["core_balance_support"], sorted(r["families"])) for r in records],
        [r["name"] for r in selected],
    ))
    return selected, dropped


def _observed_trunk(model):
    value = _original_trunk(model)
    fields = {k: (model or {}).get(k) for k in ("key_goals", "weaknesses")}
    print("trunk_selected:", value, fields)
    return value


sc._select_bounded_records = _observed_select
sc._trunk_strength_selected = _observed_trunk

kw = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
if kw.pop("foot", False):
    kw["guided"] = harness.FOOT_PAIN
harness.run(**kw)

seen = set()
for kw_, records, selected in calls:
    key = (kw_["role_key"], tuple(selected), tuple(r[0] for r in records))
    if key in seen:
        continue
    seen.add(key)
    print(kw_, "SELECTED", selected)
    for record in records:
        print("    ", record)
