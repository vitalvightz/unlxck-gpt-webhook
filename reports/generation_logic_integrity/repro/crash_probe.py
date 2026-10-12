import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import harness
from fightcamp.tactical_watch_library import TacticalWatchBankExhausted
print("is RuntimeError subclass:", issubclass(TacticalWatchBankExhausted, RuntimeError))
cases = [
 ("wrestling", 42, ("Tuesday","Thursday")), ("wrestling", 28, ("Tuesday","Thursday")), ("wrestling", 42, ()),
 ("bjj", 42, ("Tuesday","Thursday")), ("bjj", 56, ("Tuesday",)), ("wrestling", 70, ("Tuesday",)),
 ("mma", 42, ("Tuesday","Thursday")), ("boxing", 42, ("Tuesday","Thursday")),
]
for sport, days, hard in cases:
    try:
        r = harness.run(sport=sport, days=days, hard=hard, target="68", goals=("strength","conditioning"), primary_goal="strength", weak=("gas_tank",), primary_weak="gas_tank")
        print(sport, days, hard, "OK", r.get("status"))
    except Exception as exc:
        print(sport, days, hard, "EXC", type(exc).__name__, str(exc)[:120])
