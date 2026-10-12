import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import harness
for weak in ("balance", "coordination", "trunk_strength"):
    for days in (21, 35, 56):
        r = harness.run(days=days, weak=(weak,), primary_weak=weak, target="68")
        b = r["planning_brief"]
        coord = []
        trunk = []
        for w in b["weekly_role_map"]["weeks"]:
            for role in w["session_roles"]:
                if role.get("role_key") == "coordination_support":
                    coord.append(role.get("scheduled_countdown_label") or role.get("scheduled_day_hint"))
                for a in role.get("selected_exercise_assignments") or []:
                    if a.get("embedded_support"):
                        trunk.append(a["name"])
        print(weak, days, "coordination_support inserts:", coord, "embedded trunk:", trunk)
