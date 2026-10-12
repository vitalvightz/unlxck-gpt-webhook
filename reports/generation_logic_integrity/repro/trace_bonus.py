"""Observe strength._append_core_balance_bonus decisions per phase (read-only).

Usage: python trace_bonus.py '{"days": 56}'
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402

_KEEP = ("core_balance_bonus", "target_exercises", "num_strength_sessions", "current_core_balance", "bonus_entry")
events = []


def prof(frame, event, arg):
    if frame.f_code.co_name != "_append_core_balance_bonus":
        return
    if event == "call":
        events.append(("call", [e.get("name") for e in frame.f_locals.get("exercises") or []]))
    elif event == "return":
        names = [e.get("name") for e in arg] if isinstance(arg, list) else arg
        state = {k: v for k, v in frame.f_locals.items() if k in _KEEP}
        if isinstance(state.get("bonus_entry"), tuple):
            state["bonus_entry"] = state["bonus_entry"][0].get("name")
        events.append(("return", names, state))


kw = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
sys.setprofile(prof)
harness.run(**kw)
sys.setprofile(None)
for event in events:
    print(event)
