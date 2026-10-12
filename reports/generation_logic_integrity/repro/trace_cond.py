import json
import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import harness
from fightcamp import plan_pipeline_blocks as pb
orig=pb._generate_conditioning_blocks
out={}
def w(context, **kw):
    blocks, log = orig(context, **kw)
    for ph,b in blocks.items():
        out[ph]={"missing":b["missing_systems"], "grouped":{k:[d.get("name") for d in v] for k,v in (b["grouped_drills"] or {}).items()}, "res":{k:len(v) for k,v in (b.get("candidate_reservoir") or {}).items()} if isinstance(b.get("candidate_reservoir"),dict) else type(b.get("candidate_reservoir")).__name__}
    return blocks, log
pb._generate_conditioning_blocks=w
kw=json.loads(sys.argv[1]) if len(sys.argv)>1 else {}
if kw.pop("foot", False):
    kw["guided"] = harness.FOOT_PAIN
harness.run(**kw)
print(json.dumps(out,indent=1))
