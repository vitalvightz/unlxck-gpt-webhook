import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import harness
for days, hard in ((20, ("Thursday",)), (20, ()), (21, ("Thursday",))):
    r = harness.run(days=days, hard=hard, goals=("strength", "speed"), primary_goal="strength", weak=("strength",), primary_weak="strength", target="68")
    b = r["planning_brief"]
    snap = b["athlete_snapshot"]
    print(days, hard, "key_goals", snap.get("key_goals"), "weak", snap.get("weaknesses"), "pf", b["priority_focus"]["primary_goal"], "gp", [(g["goal"], g["priority"], g["state"]) for g in b["goal_preservation"]], "disposition", b.get("primary_weakness_disposition"))
