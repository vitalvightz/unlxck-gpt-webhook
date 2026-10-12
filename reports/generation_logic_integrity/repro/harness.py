"""Deterministic Stage 1 harness for the generation-integrity audit (read-only).

Runs the real Stage 1 entry point (fightcamp.main.generate_plan_sync) with a
frozen clock and fixed seed. No model calls, no database access.
"""
import datetime as dt
import json
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
logging.disable(logging.CRITICAL)

from fightcamp import input_parsing  # noqa: E402
from fightcamp.main import generate_plan_sync  # noqa: E402

NOW = dt.datetime(2026, 1, 4, 12)
input_parsing._utc_now = lambda: NOW


def payload(*, days=21, sport="boxing", status="amateur", record="0-0", rounds="3x3",
            weight="68", target="65", goals=("speed", "conditioning"), primary_goal="speed",
            weak=("trunk_strength",), primary_weak="trunk_strength", fatigue="low",
            frequency=4, availability=("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"),
            hard=("Thursday",), support=(), equipment=("barbell", "dumbbells", "kettlebells", "medicine_ball",
            "heavy_bag", "bodyweight", "pull_up_bar", "bands", "bench", "skipping_rope"),
            guided=None, injuries_text="", seed=7, no_fight=False, open_weeks=None, tactical="", age="24"):
    fight = (NOW.date() + dt.timedelta(days=days)).isoformat() if not no_fight else ""
    fields = {
        "Full name": "Audit Athlete", "Age": age, "Weight (kg)": weight, "Target Weight (kg)": target,
        "Height (cm)": "175", "Stance": "Orthodox", "Fighting Style (Technical)": sport,
        "Fighting Style (Tactical)": tactical, "Professional Status": status, "Current Record": record,
        "Rounds x Minutes": rounds, "Weekly Training Frequency": str(frequency), "Fatigue Level": fatigue,
        "Equipment Access": ", ".join(equipment), "Training Availability": ", ".join(availability),
        "Hard Sparring Days": ", ".join(hard), "Support Work Days": ", ".join(support),
        "What are your key performance goals?": ", ".join(goals), "Primary goal": primary_goal,
        "Where do you feel weakest right now?": ", ".join(weak), "Primary weak area": primary_weak,
        "When is your next fight?": fight, "Any injuries or areas you need to work around?": injuries_text,
        "Athlete Time Zone": "UTC",
    }
    data = {"data": {"fields": [{"label": k, "value": v} for k, v in fields.items()]}, "random_seed": seed}
    if guided:
        data["guided_injuries"] = guided
    if no_fight:
        data["no_scheduled_fight"] = True
        if open_weeks:
            data["open_camp_weeks"] = open_weeks
    return data


FOOT_PAIN = [{"area": "Right foot", "severity": "low", "trend": "stable", "injury_type": "pain",
              "timeframe": "last_week", "cleared": "", "notes": ""}]


def run(**kw):
    return generate_plan_sync(payload(**kw))


def summarize(result):
    brief = result.get("planning_brief") or {}
    out = []
    weeks = (brief.get("weekly_role_map") or {}).get("weeks") or []
    for week in weeks:
        out.append(f"== week {week.get('week_index')} phase={week.get('phase')} "
                   f"hard={week.get('effective_hard_sparring_days')} declared={week.get('declared_hard_sparring_days')}")
        for role in sorted(week.get("session_roles") or [], key=lambda r: -(r.get("scheduled_d_day") or r.get("countdown_offset") or 0)):
            names = [a.get("name") or a.get("exercise_name") for a in role.get("selected_exercise_assignments") or []]
            out.append(f"  D-{role.get('scheduled_d_day')} {role.get('scheduled_day_hint')} {role.get('role_key')} cat={role.get('category')} "
                       f"members={names}")
        for s in week.get("suppressed_roles") or []:
            out.append(f"  SUPPRESSED {s.get('role_key')} cat={s.get('category')} reasons={s.get('compression_reason_codes') or s.get('reason') or s.get('reason_codes')}")
    return "\n".join(out)


if __name__ == "__main__":
    name = sys.argv[1]
    kw = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    if kw.pop("foot", False):
        kw["guided"] = FOOT_PAIN
    res = run(**kw)
    outdir = Path(sys.argv[3] if len(sys.argv) > 3 else ".")
    (outdir / f"{name}.json").write_text(json.dumps(res, indent=1, default=str))
    print(summarize(res))
