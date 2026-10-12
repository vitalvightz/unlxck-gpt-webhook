import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from fightcamp.calendar_context import role_d_day
from fightcamp.goal_preservation import validate_goal_preservation
from fightcamp.planner_authority_integrity import planner_authority_findings

TRUNK_RE = re.compile(r"plank|pallof|dead.?bug|bird.?dog|hollow|anti.?rotation|suitcase|carry|rollout|copenhagen|leg raise|stir the pot|crunch|russian twist|trunk|core", re.I)
LOWER_IMPACT = {"mech_landing_impact", "mech_lower_jump", "mech_reactive_rebound", "mech_max_velocity", "mech_plantarflexion", "mech_acceleration", "mech_change_of_direction", "mech_deceleration"}
PHYS = {"strength", "conditioning", "recovery"}


def week_metrics(week):
    roles = week.get("session_roles") or []
    out = {"week": week.get("week_index"), "phase": week.get("phase"),
           "d_range": [min((d.get("d_day") for d in week.get("calendar_days") or [] if isinstance(d.get("d_day"), int)), default=None),
                       max((d.get("d_day") for d in week.get("calendar_days") or [] if isinstance(d.get("d_day"), int)), default=None)],
           "declared_hard": week.get("declared_hard_sparring_days"), "effective_hard": week.get("effective_hard_sparring_days"),
           "roles": [], "suppressed": [], "empty_closed": [], "phys_sessions": 0, "phys_days": set()}
    for role in roles:
        cat = str(role.get("category") or "")
        members = role.get("selected_exercise_assignments")
        dd = role_d_day(week, role)
        entry = {"key": role.get("role_key"), "cat": cat, "d": dd, "day": role.get("scheduled_day_hint"),
                 "members": [m.get("name") for m in members or []] if isinstance(members, list) else None,
                 "tail": bool(role.get("late_fight_tail_owned"))}
        out["roles"].append(entry)
        if cat in PHYS:
            out["phys_sessions"] += 1
            out["phys_days"].add(dd)
        if cat in {"strength", "conditioning"} and isinstance(members, list) and not members:
            out["empty_closed"].append((role.get("role_key"), dd))
    out["phys_days"] = sorted(x for x in out["phys_days"] if x is not None)
    for s in week.get("suppressed_roles") or []:
        out["suppressed"].append((s.get("role_key"), s.get("compression_reason_codes") or s.get("reason_codes") or s.get("reason")))
    return out


def scenario_metrics(result):
    if result.get("error") or not result.get("planning_brief"):
        return {"error": result.get("error"), "status": result.get("status"), "keys": list(result.keys())[:10]}
    brief = result["planning_brief"]
    weeks = (brief.get("weekly_role_map") or {}).get("weeks") or []
    m = {"weeks": [week_metrics(w) for w in weeks], "render_mode": brief.get("generator_mode")}
    (brief.get("weekly_role_map") or {}).get("session_sequence") or brief.get("session_sequence")
    gp = brief.get("goal_preservation") or []
    m["goals"] = [(g.get("goal"), g.get("priority"), g.get("state"), g.get("satisfied"), [c.get("reason_code") or c.get("reason") for c in g.get("constraints") or []], len(g.get("evidence") or [])) for g in gp]
    m["weakness_disposition"] = brief.get("primary_weakness_disposition")
    try:
        m["gp_findings"] = [(f.get("code"), f.get("goal")) for f in validate_goal_preservation(brief)]
    except Exception as exc:  # noqa
        m["gp_findings"] = f"ERR {exc!r}"
    try:
        m["authority_findings"] = [(f.get("code"), f.get("role_key")) for f in planner_authority_findings(brief)]
    except Exception as exc:
        m["authority_findings"] = f"ERR {exc!r}"
    all_members = []
    lower_impact = []
    for w in weeks:
        for role in w.get("session_roles") or []:
            for a in role.get("selected_exercise_assignments") or []:
                all_members.append(a.get("name"))
                tags = set(a.get("mechanical_risk_tags") or [])
                if tags & LOWER_IMPACT:
                    lower_impact.append((a.get("name"), role_d_day(w, role), sorted(tags & LOWER_IMPACT)))
            pm = role.get("priority_microdose")
            if isinstance(pm, dict) and pm.get("name"):
                all_members.append(pm.get("name"))
    m["trunk_members"] = sorted({n for n in all_members if n and TRUNK_RE.search(n)})
    m["lower_impact_members"] = lower_impact
    m["strength_members"] = sorted({n for n in all_members if n})
    m["triage"] = (brief.get("athlete_snapshot") or {}).get("triage_summary", {}).get("mode")
    return m


def fmt(name, m):
    lines = [f"### {name}"]
    if "error" in m:
        lines.append(f"ERROR/blocked: {m}")
        return "\n".join(lines)
    lines.append(f"mode={m['render_mode']} triage={m['triage']}")
    for w in m["weeks"]:
        lines.append(f" W{w['week']} {w['phase']} D{w['d_range'][1]}..D{w['d_range'][0]} hard decl={w['declared_hard']} eff={w['effective_hard']} phys={w['phys_sessions']} days={w['phys_days']}")
        for r in w["roles"]:
            if r["cat"] in {"support_insert"}:
                continue
            lines.append(f"    D-{r['d']} {r['key']} [{r['cat']}] {'TAIL ' if r['tail'] else ''}{r['members']}")
        if w["suppressed"]:
            lines.append(f"    suppressed={w['suppressed']}")
        if w["empty_closed"]:
            lines.append(f"    EMPTY_CLOSED={w['empty_closed']}")
    lines.append(f" goals={m['goals']}")
    lines.append(f" weakness={m['weakness_disposition']}")
    lines.append(f" gp_findings={m['gp_findings']} authority={m['authority_findings']}")
    lines.append(f" trunk_members={m['trunk_members']}")
    lines.append(f" lower_impact={m['lower_impact_members'][:8]}")
    return "\n".join(lines)
