import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import harness
import metrics
from fightcamp.main import generate_plan_sync
CASES = {
 "foot_mod_stable": [{"area": "Right foot", "severity": "moderate", "trend": "stable", "injury_type": "pain", "timeframe": "last_week"}],
 "foot_low_improving": [{"area": "Right foot", "severity": "low", "trend": "improving", "injury_type": "pain", "timeframe": "last_week"}],
 "ankle_low_sprain": [{"area": "Left ankle", "severity": "low", "trend": "stable", "injury_type": "sprain", "timeframe": "last_week"}],
 "achilles_low": [{"area": "Achilles", "severity": "low", "trend": "stable", "injury_type": "pain", "timeframe": "last_week"}],
 "knee_low": [{"area": "Left knee", "severity": "low", "trend": "stable", "injury_type": "pain", "timeframe": "last_week"}],
 "foot_high_resumed": [{"area": "Right foot", "severity": "high", "trend": "stable", "injury_type": "pain", "timeframe": "this_week"}],
}
for name, guided in CASES.items():
    data = harness.payload(guided=guided)
    if name.endswith("resumed"):
        data["_triage_resume_override"] = {"approved": True, "allowed_modes": ["needs_review"]}
    res = generate_plan_sync(data)
    m = metrics.scenario_metrics(res)
    if "error" in m:
        print(name, "BLOCKED", (res.get("why_log") or {}).get("injury_triage", {}).get("routing_reasons"))
        continue
    print(name, "triage", m["triage"], "lower_impact:", m["lower_impact_members"])
    for w in m["weeks"][:1]:
        for r in w["roles"]:
            if r["cat"] in ("strength", "conditioning"):
                print("    ", r["d"], r["key"], r["members"])
        print("     suppressed", w["suppressed"])
