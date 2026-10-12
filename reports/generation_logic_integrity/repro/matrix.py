import json
import sys
import traceback
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import harness
import metrics
from pathlib import Path
OUT = Path(__file__).resolve().parent / "out"
FOOT_LOW = harness.FOOT_PAIN
FOOT_MOD = [{"area": "Right foot", "severity": "moderate", "trend": "worsening", "injury_type": "pain", "timeframe": "this_week"}]
ANKLE_MOD = [{"area": "Left ankle", "severity": "moderate", "trend": "stable", "injury_type": "sprain", "timeframe": "last_week"}]
SHOULDER_LOW = [{"area": "Right shoulder", "severity": "low", "trend": "improving", "injury_type": "pain", "timeframe": "last_month"}]
KNEE_HIGH = [{"area": "Left knee", "severity": "high", "trend": "stable", "injury_type": "pain", "timeframe": "this_week"}]
LOWBACK_LOW = [{"area": "Lower back", "severity": "low", "trend": "stable", "injury_type": "tightness", "timeframe": "last_week"}]
ALLDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
SCENARIOS = {
 "S01_boxer21_noinj": {},
 "S02_boxer21_foot_low": {"guided": FOOT_LOW},
 "S03_boxer21_foot_mod_worse": {"guided": FOOT_MOD},
 "S04_boxer21_avail4": {"availability": ("Monday", "Tuesday", "Thursday", "Saturday")},
 "S05_boxer21_nocut": {"target": "68"},
 "S06_boxer21_highfatigue": {"fatigue": "high"},
 "S07_boxer21_freq6": {"frequency": 6},
 "S08_boxer21_bodyweight": {"equipment": ("bodyweight",)},
 "S09_boxer56_trunk": {"days": 56},
 "S10_boxer56_novice_f3_nocut": {"days": 56, "frequency": 3, "target": "68", "goals": ("strength", "conditioning"), "primary_goal": "strength"},
 "S11_boxer70_gpp_trunk_strength": {"days": 70, "goals": ("strength", "power"), "primary_goal": "strength", "weak": ("trunk_strength", "gas_tank"), "target": "68", "equipment": ("barbell", "dumbbells", "kettlebells", "sled", "yoke", "sandbag", "bodyweight", "bands", "cable", "medicine_ball")},
 "S12_mma42_pro_strength_power": {"days": 42, "sport": "mma", "status": "professional", "record": "12-3", "rounds": "3x5", "goals": ("strength", "power"), "primary_goal": "strength", "weak": ("gas_tank", "trunk_strength"), "primary_weak": "gas_tank", "fatigue": "moderate", "hard": ("Tuesday", "Friday"), "frequency": 5, "weight": "80", "target": "77"},
 "S13_muaythai28_ankle_cut7": {"days": 28, "sport": "muay thai", "goals": ("power", "conditioning"), "primary_goal": "power", "weak": ("balance", "trunk_strength"), "primary_weak": "balance", "frequency": 5, "weight": "70", "target": "65", "guided": ANKLE_MOD, "hard": ("Wednesday", "Saturday")},
 "S14_kick10_late_trunk": {"days": 10, "sport": "kickboxing", "goals": ("speed",), "primary_goal": "speed"},
 "S15_openbox8w": {"no_fight": True, "open_weeks": 8, "goals": ("strength", "conditioning"), "primary_goal": "strength", "target": "68"},
 "S16_bjj35_shoulder": {"days": 35, "sport": "bjj", "goals": ("strength", "mobility"), "primary_goal": "strength", "weak": ("trunk_strength",), "guided": SHOULDER_LOW, "hard": ("Tuesday", "Thursday"), "target": "68"},
 "S17_boxer21_threehard_pro": {"status": "professional", "record": "10-2", "hard": ("Monday", "Wednesday", "Friday"), "rounds": "10x3", "frequency": 5},
 "S18_wrestling14": {"days": 14, "sport": "wrestling", "goals": ("conditioning", "strength"), "primary_goal": "conditioning", "weak": ("gas_tank",), "primary_weak": "gas_tank"},
 "S19_boxer3d": {"days": 3},
 "S20_boxer21_knee_high": {"guided": KNEE_HIGH},
 "S21_boxer35_lowback": {"days": 35, "guided": LOWBACK_LOW, "weak": ("trunk_strength", "power"), "goals": ("power", "speed"), "primary_goal": "power"},
 "S22_boxer28_nohard": {"days": 28, "hard": (), "target": "68", "goals": ("conditioning", "speed"), "primary_goal": "conditioning"},
 "S23_boxer21_seed99": {"seed": 99},
 "S24_boxer21_foot_low_seed99": {"seed": 99, "guided": FOOT_LOW},
 "S25_mma21_trunk_primary_strength": {"sport": "mma", "goals": ("strength", "speed"), "primary_goal": "strength", "hard": ("Tuesday",), "target": "68"},
 "S26_boxer49_freq2": {"days": 49, "frequency": 2, "target": "68", "goals": ("speed", "conditioning")},
}
SCENARIOS.update({
 "S27_bw_strength35": {"days": 35, "equipment": ("bodyweight",), "goals": ("strength", "power"), "primary_goal": "strength", "weak": ("power",), "primary_weak": "power", "target": "68"},
 "S28_shoulder_strength35_onehard": {"days": 35, "sport": "bjj", "goals": ("strength",), "primary_goal": "strength", "weak": ("trunk_strength",), "guided": SHOULDER_LOW, "hard": ("Thursday",), "target": "68"},
 "S29_ankle_low_speed21": {"guided": [{"area": "Left ankle", "severity": "low", "trend": "stable", "injury_type": "sprain", "timeframe": "last_week"}]},
})

SCENARIOS.update({
 "S30_muaythai28_noinj_cut7": {"days": 28, "sport": "muay thai", "goals": ("power", "conditioning"), "primary_goal": "power", "weak": ("balance", "trunk_strength"), "primary_weak": "balance", "frequency": 5, "weight": "70", "target": "65", "hard": ("Wednesday", "Saturday")},
 "S31_wrestling42": {"days": 42, "sport": "wrestling", "goals": ("strength", "conditioning"), "primary_goal": "strength", "weak": ("gas_tank",), "primary_weak": "gas_tank", "hard": ("Tuesday", "Thursday"), "target": "68"},
 "S32_kick35_trunk": {"days": 35, "sport": "kickboxing", "goals": ("speed", "power"), "primary_goal": "speed", "target": "68"},
})
if __name__ == "__main__":
    names = sys.argv[1:] or list(SCENARIOS)
    allm = {}
    for name in names:
        kw = dict(SCENARIOS[name])
        try:
            res = harness.run(**kw)
            OUT.mkdir(exist_ok=True)
            json.dump(res, open(OUT / f"{name}.json", "w"), default=str)
            m = metrics.scenario_metrics(res)
        except Exception as exc:
            m = {"error": "EXC " + repr(exc), "tb": traceback.format_exc()[-1500:]}
        allm[name] = m
        print(metrics.fmt(name, m), flush=True)
    json.dump(allm, open(OUT / ("metrics_" + ("_".join(names) if len(names) < 3 else "all") + ".json"), "w"), default=str, indent=1)
