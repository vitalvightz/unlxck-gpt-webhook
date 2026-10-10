"""Reviewed discovery language, never goal metadata or prescription evidence.

Groups are ANDed; alternatives within a group are ORed. Tokens match explicit
raw fields. Mechanical risk tags alone never establish a training intent.
"""
from dataclasses import dataclass
import re

from fightcamp.training_catalogue import metadata_state, strings


@dataclass(frozen=True)
class Concept:
    label: str
    phrases: tuple[str, ...]
    groups: tuple[tuple[tuple[str, tuple[str, ...]], ...], ...]
    rationale: str
    related: bool = False


def evidence(field: str, *values: str):
    return field, values


def concept(label: str, phrases: str, rationale: str, *groups, related: bool = False):
    return Concept(label, tuple(phrases.split(";")), groups, rationale, related)


# This is a deliberately inspectable taxonomy rather than inferred exercise
# classification. Several everyday phrases may express one source concept.
CONCEPTS = (
    concept("Punch-specific power", "punching power;hit harder;harder punches;powerful punches", "Punch-specific name plus explicit power/force-development evidence.",
            (evidence("name_words", "punch", "punching", "jab", "body shot", "hook throw"), evidence("modality", "maximal bag punching burst", "precision power")),
            (evidence("method", "power", "plyometric", "contrast"), evidence("goals", "power"), evidence("tags", "power", "explosive", "rate_of_force"))),
    concept("Rotational power", "rotational power;punching power;hit harder;harder punches", "Rotation plus power plus upper-body/striking context; related work, not a verified punching effect.",
            (evidence("movement", "rotation", "rotational"), evidence("tags", "rotational")),
            (evidence("method", "power"), evidence("tags", "power", "explosive", "rate_of_force")),
            (evidence("tags", "upper_body", "mech_upper_press", "boxing", "striking"), evidence("category", "upper_body", "boxing", "striking")), related=True),
    concept("Upper-body power", "punching power;hit harder;harder punches;upper body power", "Explicit pressing/upper-body context plus force-development/plyometric evidence; related work, not a verified punching effect.",
            (evidence("movement", "horizontal_push"), evidence("tags", "upper_body")),
            (evidence("tags", "rate_of_force", "explosive"), evidence("method", "plyometric", "contrast", "power")), related=True),
    concept("Fast force production", "explosive power;fast force;explosiveness", "Explicit rate-of-force or explosive quality; ballistic risk alone is insufficient.",
            (evidence("tags", "rate_of_force", "explosive"), evidence("method", "power", "contrast"))),
    concept("Leg power", "explosive legs;leg power;powerful legs;jumping power", "Explicit lower-body/jump context and power evidence.",
            (evidence("category", "lower_body"), evidence("movement", "vertical_jump", "horizontal_jump")),
            (evidence("method", "power", "plyometric", "contrast"), evidence("tags", "explosive", "power", "rate_of_force"))),
    concept("Aerobic endurance", "stamina;gas tank;cardio;endurance;lasting rounds;fight endurance", "Explicit aerobic system/quality.",
            (evidence("system", "aerobic"), evidence("tags", "aerobic", "gas_tank", "endurance"), evidence("qualities", "aerobic_capacity"))),
    concept("Repeated hard efforts", "round fitness;repeat bursts;repeated efforts;fight conditioning;lasting rounds;gas tank", "Glycolytic system or stated work capacity; not automatically an aerobic goal.",
            (evidence("system", "glycolytic"), evidence("tags", "work_capacity", "glycolytic"))),
    concept("Short explosive efforts", "short bursts;burst speed;alactic power", "Explicit ATP-PCr/alactic system.",
            (evidence("system", "ATP-PCr", "alactic", "anaerobic_alactic"),)),
    concept("Reaction to cues", "reaction speed;faster reactions;react quicker;reflexes;reaction time", "Explicit cue-response quality; reactive rebound mechanics are excluded.",
            (evidence("tags", "reaction"), evidence("qualities", "reaction", "decision_reaction", "tactile_reaction", "visual_motor"))),
    concept("Decision speed", "quick decisions;decision making;read cues", "Explicit cognitive decision/visual processing evidence.",
            (evidence("tags", "decision_making", "visual_processing"), evidence("qualities", "decision_reaction"))),
    concept("Footwork", "footwork;foot work;move my feet;faster feet;ring movement", "Explicit footwork classification/quality.",
            (evidence("tags", "footwork", "boxer_footwork"), evidence("movement", "footwork"), evidence("qualities", "footwork"), evidence("modality", "technical_footwork", "footwork"), evidence("name_words", "footwork"))),
    concept("Change direction", "change direction;agility;quick direction changes", "Explicit agility/lateral movement, not generic reactive risk.",
            (evidence("tags", "agility", "lateral_movement"), evidence("movement", "lateral", "lateral_reactive"))),
    concept("Create angles", "create angles;cut angles;angle footwork", "Explicit tactical angle creation/exit.",
            (evidence("tags", "angles", "angle_exit"), evidence("qualities", "angle_creation"), evidence("tactical_function", "angle_creation"))),
    concept("Defensive movement", "defensive movement;defence movement;escape pressure;defensive footwork", "Explicit defensive exit/range-recovery function or defence modality.",
            (evidence("tactical_function", "defensive_exit", "takedown_defense", "scramble_recovery"), evidence("modality", "defense", "defensive scrambling", "pressure escape interval"))),
    concept("Distance management", "distance control;manage range;keep distance;range control", "Explicit distance/range function.",
            (evidence("qualities", "distance_control"), evidence("tactical_function", "range_management"), evidence("modality", "range management"))),
    concept("Ring and cage control", "cut off ring;ring cutting;cage control;cut off cage", "Explicit ring-cutting/cage-control function.",
            (evidence("tactical_function", "ring_cutting", "cage_control", "exit_lane_control"), evidence("tags", "ringcraft", "cage_work"), evidence("name_words", "cage cutting", "ring cutting", "ring cut off"))),
    concept("Counter setup", "counter timing;counter attack;counterattacks", "Explicit counter setup, not every counter-striker style tag.",
            (evidence("tactical_function", "counter_setup"), evidence("modality", "counter timing sharpness", "reactive counter burst"))),
    concept("Takedown defence", "takedown defence;takedown defense;stop takedowns;sprawl", "Explicit takedown-defence function or sprawl movement in the name.",
            (evidence("tactical_function", "takedown_defense"), evidence("name_words", "sprawl"))),
    concept("Base recovery", "recover stance;stance recovery;recover balance;base recovery", "Explicit recovery/transition function.",
            (evidence("tactical_function", "base_recovery", "standup_transition", "scramble_recovery"), evidence("tags", "stance_reset"), evidence("qualities", "stance_transition"))),
    concept("Kick recovery", "kick recovery;kick balance;reset after kicks", "Explicit kick recovery quality/function.",
            (evidence("qualities", "kick_recovery"), evidence("tactical_function", "kick_recovery"))),
    concept("Balance", "balance;stay balanced", "Explicit balance/postural control quality.",
            (evidence("tags", "balance", "balance_static", "balance_challenge"), evidence("qualities", "balance", "postural_control"), evidence("goals", "balance"), evidence("category", "balance", "balance_support", "proprioception"))),
    concept("Core control", "core stability;stable core;trunk control;brace core", "Anti-rotation/extension or explicit core-stability weakness; trunk-loading risk alone is excluded.",
            (evidence("tags", "anti_rotation", "anti_extension", "breathing_core"), evidence("weaknesses", "core_stability"))),
    concept("Core training", "core strength;core work;ab strength", "Explicit core anatomy/quality.",
            (evidence("category", "core"), evidence("movement", "core"), evidence("tags", "core"))),
    concept("Shoulder control", "shoulder control;shoulder stability;scapular control", "Explicit scapular control/stability evidence; pressing/overhead risk alone is excluded.",
            (evidence("tags", "scap_control", "scap_retraction", "serratus"), evidence("weaknesses", "shoulder_stability"))),
    concept("Shoulder endurance", "shoulder endurance;shoulder stamina", "Explicit shoulder-endurance weakness/modality.",
            (evidence("weaknesses", "shoulder_endurance"), evidence("modality", "shoulder stamina"))),
    concept("Grip work", "grip strength;stronger grip;grappling grip", "Explicit grip quality/anatomy; grip-support risk alone is excluded.",
            (evidence("tags", "grip"), evidence("weaknesses", "grip_strength"), evidence("category", "grip"))),
    concept("Neck work", "neck control;neck training", "Explicit neck region/tag/name; no concussion-prevention claim.",
            (evidence("tags", "neck"), evidence("body_region", "neck", "neck_vestibular"), evidence("name_words", "neck"))),
    concept("Mobility", "mobility;less stiff;loosen up;movement range", "Explicit mobility/stiffness evidence.",
            (evidence("tags", "mobility"), evidence("movement", "mobility"), evidence("goals", "mobility"), evidence("weaknesses", "stiffness"))),
    concept("Hip mobility", "hip mobility;loose hips;hip movement", "Mobility evidence plus explicit hip region/name.",
            (evidence("movement", "mobility"), evidence("tags", "mobility"), evidence("goals", "mobility")),
            (evidence("body_region", "hip", "ankle_foot_hip", "foot_ankle_hip"), evidence("name_words", "hip", "hips"))),
    concept("Ankle mobility", "ankle mobility;ankle movement", "Explicit ankle-mobility tag or mobility plus ankle context.",
            (evidence("tags", "ankle_mobility"), evidence("movement", "mobility"), evidence("goals", "mobility")),
            (evidence("tags", "ankle_mobility"), evidence("body_region", "ankle", "calf_ankle", "ankle_foot_hip", "foot_ankle_hip"), evidence("name_words", "ankle"))),
    concept("Coordination", "coordination;move smoothly;body coordination", "Explicit coordination/bilateral/limb independence quality.",
            (evidence("tags", "coordination"), evidence("goals", "coordination"), evidence("qualities", "limb_independence", "bilateral_control", "hip_leg_coordination", "hip_hand_coordination", "hand_coordination"))),
    concept("Hand and foot timing", "hand foot coordination;hands and feet;hand foot timing", "Explicit hand/foot timing quality, not all coordination.",
            (evidence("qualities", "foot_hand_timing", "hand_foot_timing", "knee_foot_timing"),)),
    concept("Head movement timing", "head movement;head hand timing;head foot timing", "Explicit head-hand/foot timing quality.",
            (evidence("qualities", "head_hand_timing", "head_foot_timing"),)),
    concept("Rhythm", "rhythm;movement rhythm;timing rhythm", "Explicit rhythm quality/weakness.",
            (evidence("qualities", "rhythm"), evidence("weaknesses", "rhythm"))),
    concept("Weight transfer", "weight transfer;shift weight", "Explicit weight transfer quality.",
            (evidence("qualities", "weight_transfer"),)),
    concept("Transitions", "transitions;switch positions;position changes", "Explicit transition quality.",
            (evidence("tags", "transition"), evidence("qualities", "transition", "defense_offense_transition"))),
    concept("Spatial awareness", "spatial awareness;body awareness", "Explicit spatial-awareness quality.",
            (evidence("qualities", "spatial_awareness"), evidence("tags", "spatial_awareness"))),
    concept("Strength", "strength;get stronger;strength training", "Explicit strength method/goal.",
            (evidence("method", "strength", "strength_conditioning"), evidence("goals", "maximal_strength_maintenance"))),
    concept("Isometric work", "isometric holds;static holds;hold strength", "Explicit isometric movement/tag.",
            (evidence("movement", "isometric", "isometric_hold"), evidence("tags", "isometric"))),
    concept("Jump training", "jump training;plyometrics;jumping drills", "Explicit jump/plyometric movement/method.",
            (evidence("method", "plyometric"), evidence("movement", "vertical_jump", "horizontal_jump"), evidence("tags", "plyometric"))),
    concept("Posterior chain", "posterior chain;back of legs;hip drive", "Explicit posterior-chain/hip-dominant/hinge movement.",
            (evidence("tags", "posterior_chain", "hip_dominant", "hamstring"), evidence("movement", "hinge"))),
    concept("Pulling strength", "pulling strength;pull strength;back strength", "Explicit pulling movement plus strength method.",
            (evidence("movement", "pull"), evidence("tags", "pull", "upper_back")), (evidence("method", "strength", "strength_conditioning"),)),
    concept("Pressing strength", "pushing strength;press strength;push strength", "Explicit pushing movement plus strength method.",
            (evidence("movement", "horizontal_push", "vertical_push", "squat_to_press"), evidence("tags", "push", "upper_push", "horizontal_push")), (evidence("method", "strength", "strength_conditioning"),)),
    concept("Low impact", "low impact", "Explicit low/zero-impact tag; no injury clearance implied.",
            (evidence("tags", "low_impact", "zero_impact"),)),
    concept("Recovery movement", "recovery;easy recovery;recovery movement", "Explicit recovery classification/tag.",
            (evidence("tags", "recovery", "parasympathetic"), evidence("category", "recovery"), evidence("weaknesses", "recovery"))),
    concept("Medicine ball", "medicine ball;med ball;medball", "Explicit equipment token; does not alter equipment facets.",
            (evidence("equipment", "medicine_ball"),)),
    concept("Bodyweight", "no equipment;bodyweight;without equipment", "Explicit equipment empty/none/bodyweight only.",
            (evidence("equipment", "none", "bodyweight", "__empty__"),)),
    concept("Hand speed", "hand speed;faster hands;fast punches;quicker punches", "Explicit speed plus named punching/boxing or upper-body context.",
            (evidence("tags", "speed"), evidence("goals", "speed")),
            (evidence("name_words", "punch", "punching", "jab"), evidence("modality", "hand speed primer", "long-range hand speed", "maximal bag punching burst"),
             evidence("name_words", "boxing burst"))),
    concept("Single-leg balance", "single leg balance;one leg balance", "Balance evidence plus explicit one-leg context.",
            (evidence("tags", "balance"), evidence("qualities", "balance"), evidence("goals", "balance")),
            (evidence("name_words", "single leg", "one leg"), evidence("tags", "single_leg"))),
    concept("Grip endurance", "grip endurance;hold my grip", "Grip evidence plus stated endurance/isometric work.",
            (evidence("tags", "grip"), evidence("weaknesses", "grip_strength"), evidence("category", "grip")),
            (evidence("tags", "endurance", "isometric"), evidence("movement", "isometric", "isometric_hold"), evidence("modality", "isometric endurance"))),
    concept("Low-impact conditioning", "low impact cardio;low impact conditioning", "Conditioning source plus explicit low/zero-impact tag.",
            (evidence("content_class", "conditioning"),), (evidence("tags", "low_impact", "zero_impact"),)),
    concept("Readiness movement", "warm up;warmup;primer;readiness drills", "Explicit readiness/primer evidence, not automatic suitability for an athlete.",
            (evidence("goals", "readiness"), evidence("method", "primer"), evidence("tags", "neural_primer"))),
    concept("Level-change timing", "level change timing;takedown timing", "Explicit level-change timing quality.",
            (evidence("qualities", "level_change_timing"),)),
    concept("Hand timing", "hand timing;hand coordination", "Explicit hand-timing quality.",
            (evidence("qualities", "hand_timing", "hand_coordination"),)),
    concept("Bands", "resistance band;bands;band work", "Explicit band equipment.",
            (evidence("equipment", "band", "bands", "resistance_band"),)),
    concept("Kettlebells", "kettlebell;kb;bell work", "Explicit kettlebell equipment.",
            (evidence("equipment", "kettlebells", "kettlebell"),)),
    concept("Neck strength", "neck strength;stronger neck", "Neck context plus stated strength/isometric work; excludes mobility-only and vestibular drills.",
            (evidence("tags", "neck"), evidence("body_region", "neck"), evidence("name_words", "neck")),
            (evidence("method", "strength"), evidence("movement", "isometric", "isometric_hold"))),
)


def supports(entry: dict, rule: Concept) -> bool:
    raw = entry["raw"]

    def matches(condition):
        field, tokens = condition
        if field == "content_class":
            return entry["content_class"] in tokens
        if field == "name_words":
            # Whole word/phrase boundaries; e.g. a hook grip is not a hook throw.
            name = re.sub(r"[^a-z0-9]+", " ", entry["name"].casefold()).strip()
            return any(f" {token} " in f" {name} " for token in tokens)
        if metadata_state(raw, field) != "known":
            return False
        values = strings(raw.get(field))
        if field == "equipment" and raw.get(field) == []:
            values = ["__empty__"]
        return bool(set(values).intersection(tokens))

    return all(any(matches(condition) for condition in group) for group in rule.groups)
