"""Exercise execution guidance, independent of dose and calendar authority.

Movement profiles supply execution and stop guidance only. Numerical Progress
comes from a resolved future exposure; Easier reduces one known work quantity.
Unknown movements keep their authored guidance without invented load targets.
"""
from __future__ import annotations

import re
from typing import Any
from .coaching_copy import concise_coaching
from .exercise_progression import (
    authored_progression_matches, effective_exercise_prescription, measured_dose,
    numerical_easier, numerical_guidance, progression_prohibited, normalise_measures,
)


# Cue, easier execution, legacy quality rule, stop criterion. The third value
# only identifies #2880's persisted wording for migration; it is never emitted
# as Progress. More specific matches precede movement families.
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
    (r"bag burst|heavy bag|boxing.*burst|pocket frame|pull-counter|entry.*exit|punch|shadowbox", (
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
    progression_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return concise coaching for this selected exercise and athlete context.

    Taper, final fortnight, active injury, high fatigue and weight-cut risk are
    maintenance contexts: no Progress instruction. Easier never asks the athlete
    to push through a stop criterion. It never rewrites the prescribed dose.
    """
    athlete = athlete or {}
    name = str(assignment.get("name") or "")
    fields: dict[str, Any] = {}
    for key in ("coaching_cues", "regression_options", "stop_rules"):
        value = assignment.get(key)
        fields[key] = ([value] if isinstance(value, str) and value.strip() else
                       list(value) if isinstance(value, list) else [])
    if isinstance(assignment.get("progression_rule"), str) and assignment["progression_rule"].strip():
        fields["progression_rule"] = assignment["progression_rule"]
    # Keep authored safety criteria in the safety field, rather than burying
    # "Stop..." halfway through a cue. Notes remain evidence, never a new dose.
    notes = str(assignment.get("coaching_notes") or "").strip()
    labels = {"cue": "coaching_cues", "coaching cues": "coaching_cues",
              "easier": "regression_options", "regression": "regression_options",
              "progress": "progression_rule", "progression": "progression_rule",
              "stop": "stop_rules", "stop rule": "stop_rules"}
    for line in notes.splitlines():
        labelled = re.match(r"^\s*([A-Za-z ]+)\s*:\s*(.+)$", line)
        if labelled and labelled[1].lower() in labels:
            key = labels[labelled[1].lower()]
            if key == "progression_rule":
                fields.setdefault(key, labelled[2])
            elif labelled[2] not in fields[key]:
                fields[key].append(labelled[2])
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", line.strip()):
            if sentence:
                embedded_stop = re.search(r"\bstop\s+(?:the\b|if\b|on\b|when\b|for\b|immediately\b).*$", sentence, re.I)
                if embedded_stop:
                    stop = embedded_stop[0]
                    if stop not in fields["stop_rules"]:
                        fields["stop_rules"].append(stop)
                    sentence = sentence[:embedded_stop.start()].strip(" ;,:")
                    if not sentence:
                        continue
                key = "stop_rules" if re.match(r"stop\b|end\b", sentence, re.I) else "coaching_cues"
                if sentence not in fields[key]:
                    fields[key].append(sentence)
    if assignment.get("slot_group") not in {"strength_slots", "conditioning_slots", "priority_microdose"}:
        return concise_coaching(fields)
    phase = str(phase or role.get("phase") or assignment.get("source_phase") or "").upper()
    constrained = progression_prohibited(role, assignment, phase, d_day, athlete)
    authored_progress = fields.pop("progression_rule", None)
    profile = next((p for pattern, p in _PROFILES if re.search(pattern, name, re.I)), None)
    if profile is not None:
        cue, easier, _, stop = profile
        if not fields["coaching_cues"]:
            fields["coaching_cues"] = [cue]
        if not fields["stop_rules"]:
            fields["stop_rules"] = [stop]
    prescription = effective_exercise_prescription(role, assignment)
    dose = measured_dose(prescription, assignment)
    if not fields["regression_options"]:
        option = numerical_easier(dose) if fields["stop_rules"] else None
        if option:
            fields["regression_options"] = [option]
        elif profile is not None:
            fields["regression_options"] = [easier]
    if not constrained:
        guidance = numerical_guidance(progression_context, dose, prescription)
        if guidance.get("progression_rule"):
            target = progression_context["next"]["dose"]
            fields["progression_rule"] = (
                authored_progress if authored_progress and authored_progression_matches(authored_progress, guidance, target)
                else guidance["progression_rule"]
            )
        elif guidance.get("maintenance_cue"):
            # A repeated dose is not a second execution cue. Show a genuine
            # maintenance step in the same Progress slot instead.
            fields["progression_rule"] = "Repeat current dose."
        elif prescription and dose:
            # Unknown future loads must not produce fabricated +kg claims.
            fields["progression_rule"] = "Repeat prescribed dose."
    if authored_progress and is_execution_quality_instruction(authored_progress) and not is_profile_progression(authored_progress):
        if authored_progress not in fields["coaching_cues"]:
            fields["coaching_cues"].append(authored_progress)
    return concise_coaching(fields)


def is_profile_progression(text: str) -> bool:
    """Identify only #2880's exact generated quality rules, never athlete prose."""
    return text.strip() in {profile[2] for _, profile in _PROFILES}


def is_profile_regression(text: str) -> bool:
    return text.strip() in {profile[1] for _, profile in _PROFILES}


def is_profile_cue(text: str) -> bool:
    return text.removeprefix("Cue: ").strip() in {profile[0] for _, profile in _PROFILES}


def has_measurable_step(text: str) -> bool:
    return bool(re.search(r"\d\s*(?:kg\b|lb\b|%|[x×]\s*\d|sets?\b|reps?\b|rounds?\b|m\b|min\b|minutes?\b|sec\b|seconds?\b)|RPE\s*\d", normalise_measures(text), re.I))


def is_execution_quality_instruction(text: str) -> bool:
    return not has_measurable_step(text) and not re.search(
        r"\b(?:add|extend|heavier|stronger)\b|\bincrease\s+(?:load|weight|volume|reps|sets|rounds|speed|effort|intensity)|"
        r"\b(?:advance|progress)\s+to\b|\bshorten\s+(?:the\s+)?rest", text, re.I)


def coaching_lines(fields: dict[str, Any]) -> list[str]:
    lines = [f"  Cue: {cue}" for cue in fields.get("coaching_cues") or []]
    lines.extend(f"  Easier: {text}" for text in fields.get("regression_options") or [])
    if fields.get("progression_rule"):
        lines.append(f"  Progress: {fields['progression_rule']}")
    lines.extend(f"  Stop: {text}" for text in fields.get("stop_rules") or [])
    return lines
