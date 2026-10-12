"""Diagnostic only: does expanding the weakness through WEAKNESS_TAG_MAP surface trunk work?"""
import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import harness
import metrics
from fightcamp import plan_pipeline_blocks as pb
from fightcamp.tag_maps import WEAKNESS_TAG_MAP
orig=pb.generate_strength_block
def patched(*, flags, weaknesses=None):
    expanded=list(dict.fromkeys([*(weaknesses or []), *[t for w in (weaknesses or []) for t in WEAKNESS_TAG_MAP.get(w, [])]]))
    return orig(flags=flags, weaknesses=expanded)
pb.generate_strength_block=patched
for days in (21, 56):
    res=harness.run(days=days)
    m=metrics.scenario_metrics(res)
    b=res["planning_brief"]
    pools={ph:[(s.get("selected") or {}).get("name") for s in p.get("strength_slots",[])] for ph,p in b["candidate_pools"].items() if isinstance(p,dict)}
    print(days, "trunk members:", m["trunk_members"])
    for ph, names in pools.items():
        print("   ", ph, names)
