import json
import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import harness
from fightcamp import strength as st
from fightcamp import strength_session_quality as q
orig=st._evaluate_strength_late_window
rec={}
CORE={"Plank","Cable Pallof Press","Anti-Rotation Press","Hollow-Body Hold","Controlled Bird-Dog","Isometric Pallof Hold","Wall ISO Deadbug","Deadbug (Band-Resisted)","Copenhagen Side Plank","Kettlebell Suitcase Carry Hold","Suitcase Carry (Heavy)","Side Plank Row(Band or DB)","Dead Bug","Pallof Press"}
def w(ex, **kw):
    r=orig(ex, **kw)
    if ex.get("name") in CORE or q.classify_strength_item(ex).get("core_balance_support"):
        rec[(ex.get("name"), kw.get("window"))]=(r["blocked"], r["block_codes"], round(r["adjustment"],2))
    return r
st._evaluate_strength_late_window=w
kw=json.loads(sys.argv[1]) if len(sys.argv)>1 else {}
harness.run(**kw)
for k, v in sorted(rec.items(), key=lambda x: str(x)):
    print(k, v)
