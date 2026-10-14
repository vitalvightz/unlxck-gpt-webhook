"""Exercise execution guidance, independent of dose and calendar authority.

These conservative profiles coach the selected movement at its existing dose.
Progress means a specific improvement in execution, never permission to add
load, repetitions, duration, impact or complexity. Unknown movements get their
authored bank notes only. No exercise substitutions are selected here.
"""
from __future__ import annotations

import re
from typing import Any


# cue, easier execution, quality target, stop criterion. More specific matches
# precede movement families; no medical/rehab progression is authored here.
_PROFILES = (
    (r"swimming|freestyle", (
        "Keep the stroke relaxed and breathe regularly; avoid breath holds.",
        "Slow the stroke and relax the pull while keeping breathing comfortable.",
        "Keep the same swim dose; aim for an even stroke rhythm from start to finish.",
        "End the swim if shoulder pain, dizziness or breathing difficulty appears.",
    )),
    (r"easy assault bike|nasal jog|aerobic", (
        "Keep a relaxed rhythm and breathing comfortable throughout the aerobic work.",
        "Ease the pace or resistance until breathing settles; do not chase the effort target.",
        "At the same duration and effort ceiling, aim for a steadier pace without breathing strain.",
        "End the work if dizziness, chest discomfort or unusual breathlessness appears.",
    )),
    (r"cossack", (
        "Sit into the working hip with the heel grounded and knee tracking the toes.",
        "Use a shallower pain-free depth; keep the heel grounded.",
        "Once every rep is stable and pain-free, improve control into the same depth at the prescribed dose.",
        "End the set if knee or groin pain appears or the heel lifts.",
    )),
    (r"single-leg trx.*hold", (
        "Keep the pelvis level and use the straps to steady the single-leg position.",
        "Take more support through the straps without extending the hold.",
        "Once the holds stay level and pain-free, aim for less sway at the same hold dose.",
        "End the hold if joint pain appears or the pelvis drops despite strap support.",
    )),
    (r"staggered stance hold|standing stance", (
        "Set a balanced stance with soft knees and ribs stacked over the pelvis.",
        "Use a more comfortable stance width and keep the position relaxed.",
        "Once the stance stays steady, aim for even pressure through both feet at the same dose.",
        "End the hold if pain appears or you cannot keep a balanced stance.",
    )),
    (r"lateral bound", (
        "Land quietly, control the knee and reset the stance before the next bound.",
        "Shorten the bound to a distance you can land and balance cleanly.",
        "Once every landing is controlled, aim for a cleaner stance reset at the same bound distance and dose.",
        "End the set if knee or ankle pain appears or landings become unstable.",
    )),
    (r"jump|hop|bound", (
        "Stick each landing with the knee tracking the toes; reset before the next take-off.",
        "Reduce jump distance or height until each landing is quiet and stable.",
        "Once every landing is stable, aim for more repeatable take-offs at the same height, distance and dose.",
        "End the set if pain appears, jump quality drops or you cannot stick the landing.",
    )),
    (r"sled push.*speed", (
        "Drive the sled with quick steps and a braced trunk; keep each acceleration crisp.",
        "Use less sled resistance so steps stay quick without changing the work or rest.",
        "Once all accelerations stay crisp, aim for more even step speed at the same sled load and dose.",
        "End the effort if speed drops, the trunk collapses or pain appears.",
    )),
    (r"sled pull|sled drag|carry", (
        "Keep the trunk braced and steps steady; move the load without twisting or jerking.",
        "Reduce the carried or sled load until steps are steady.",
        "Once every length is controlled, aim for a smoother unbroken rhythm at the same load and distance.",
        "End the effort if pain appears or you cannot keep the trunk and steps controlled.",
    )),
    (r"thruster|push press|swing", (
        "Drive through the legs and keep the trunk braced; finish each rep without grinding.",
        "Use a lighter load so the same movement stays crisp and controlled.",
        "Once all reps stay crisp, aim for more consistent rep speed at the same load and dose.",
        "End the set if speed drops, trunk control fails or pain appears.",
    )),
    (r"bag burst|pocket frame|pull-counter|entry.*exit|punch|shadowbox", (
        "Keep punches balanced, return to guard and reset the stance between exchanges.",
        "Ease punch force and simplify the exchange until balance and guard return are clean.",
        "Once each exchange stays balanced, aim for a cleaner guard return at the same effort ceiling and dose.",
        "End the effort if punch speed, guard return or balance deteriorates, or pain appears.",
    )),
    (r"first.step|acceleration|sprint", (
        "Push off a stable stance and regain balance before the next effort.",
        "Ease acceleration until you can brake and reset under control.",
        "Once every reset is balanced, aim for more consistent first-step timing at the same dose.",
        "End the effort if speed drops, braking becomes uncontrolled or pain appears.",
    )),
    (r"throw|med.*ball", (
        "Drive the throw from the legs and trunk; reset your balance before the next release.",
        "Use a lighter ball and reduce throw force until the release stays controlled.",
        "Once every release is balanced, aim for a more consistent throw at the same ball weight and dose.",
        "End the set if throw speed drops, balance is lost or shoulder or back pain appears.",
    )),
    (r"squat|deadlift|\brdl\b|\brow\b|\bpress\b|pull.up", (
        "Keep the trunk braced and the movement controlled; avoid grinding repetitions.",
        "Use a lighter load or more assistance through the same pain-free movement.",
        "Once every rep stays controlled, aim for more consistent movement at the same load and dose.",
        "End the set if pain appears or you lose trunk or joint control.",
    )),
)


def exercise_coaching(
    assignment: dict[str, Any], role: dict[str, Any], *,
    phase: str = "", d_day: int | None = None,
    athlete: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return concise coaching for this selected exercise and athlete context.

    Taper, final fortnight, active injury, high fatigue and weight-cut risk are
    maintenance contexts: no Progress instruction. Easier never asks the athlete
    to push through a stop criterion. It changes execution, not the exact dose.
    """
    athlete = athlete or {}
    name = str(assignment.get("name") or "")
    fields: dict[str, Any] = {
        "coaching_cues": [], "regression_options": [], "stop_rules": [],
    }
    # Keep authored safety criteria in the safety field, rather than burying
    # "Stop..." halfway through a cue. Notes remain evidence, never a new dose.
    notes = str(assignment.get("coaching_notes") or "").strip()
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", notes):
        if sentence:
            key = "stop_rules" if re.match(r"stop\b|end\b", sentence, re.I) else "coaching_cues"
            fields[key].append(sentence)
    if assignment.get("slot_group") not in {"strength_slots", "conditioning_slots", "priority_microdose"}:
        return fields
    profile = next((p for pattern, p in _PROFILES if re.search(pattern, name, re.I)), None)
    if profile is None:
        return fields
    cue, easier, progress, stop = profile
    # An authored bank cue is more specific than the family cue.
    if not fields["coaching_cues"]:
        fields["coaching_cues"] = [cue]
    fields["coaching_cues"] = fields["coaching_cues"][:2]
    fields["regression_options"] = [easier]
    if not fields["stop_rules"]:
        fields["stop_rules"] = [stop]
    phase = str(phase or role.get("phase") or assignment.get("source_phase") or "").upper()
    constrained = (
        phase == "TAPER" or (d_day is not None and d_day <= 14)
        or str(athlete.get("fatigue") or "").lower() == "high"
        or bool(athlete.get("has_active_injury") or athlete.get("injuries") or athlete.get("injury_restrictions"))
        or bool(athlete.get("weight_cut_risk"))
        or str(athlete.get("cut_severity_bucket") or "none").lower() not in {"none", "low"}
        or assignment.get("slot_group") == "priority_microdose"
    )
    if not constrained and assignment.get("support_only") is not True:
        fields["progression_rule"] = progress
    return fields


def coaching_lines(fields: dict[str, Any]) -> list[str]:
    lines = [f"  Cue: {cue}" for cue in fields.get("coaching_cues") or []]
    lines.extend(f"  Easier: {text}" for text in fields.get("regression_options") or [])
    if fields.get("progression_rule"):
        lines.append(f"  Progress: {fields['progression_rule']}")
    lines.extend(f"  Stop: {text}" for text in fields.get("stop_rules") or [])
    return lines
