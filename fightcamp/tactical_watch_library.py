"""Deterministic content library for the Fight Tactical Watch.

The Tactical Watch is a single, existing mandatory support role (``tactical_watch``)
placed once per GPP / SPP / TAPER week by the fight-camp scheduler (see
``camp_week_fillers`` and ``gap_fill_inserts``). This module does not add a new
session type or a second progression engine — it only decides *which* Tactical
Watch content is selected and rendered so that repeated watches stop looking
identical.

What lives here:

* Tactical-style normalisation (intake aliases -> a small family set).
* Camp-phase normalisation (GPP / SPP / TAPER + common aliases).
* A typed :class:`TacticalWatch` content library, banked by ``(style, phase)``.
* Deterministic selection that never repeats a watch key within one camp and
  falls back to the phase-matched generic bank when a style bank is exhausted.
* Rendering-ready projections (display text for the plan markdown, and the
  structured-session fields the athlete actually sees).

Every athlete-visible field (name, why, intent, focus, reset, anchor, context,
inner activity title, instruction bullets, required output and progress) is
authored distinctly per watch. There is deliberately no shared four-line
"entry/danger/reset/round 1" output contract — that repetition is the failure
mode this module exists to remove.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

__all__ = [
    "TacticalWatch",
    "TacticalWatchBankExhausted",
    "STYLE_FAMILIES",
    "PHASES",
    "normalize_tactical_style",
    "normalize_camp_phase",
    "extract_tactical_style",
    "ordered_phase_bank",
    "select_tactical_watch",
    "select_watch_by_occurrence",
    "watch_metadata",
    "build_watch_display_text",
    "canonical_watch_signature",
    "all_watches",
]


# --- style + phase vocabularies -------------------------------------------

STYLE_FAMILIES = ("distance_striker", "brawler", "counter_striker", "generic")
PHASES = ("GPP", "SPP", "TAPER")


class TacticalWatchBankExhausted(RuntimeError):
    """Raised when a ``(style, phase)`` bank has no unused watch left.

    This is an invariant violation, not an expected runtime path: every generic
    phase bank is sized to cover the maximum number of weeks that phase can ever
    carry (see ``calculate_phase_weeks``), so a real camp can never exhaust a
    bank. The selector fails loudly rather than silently repeating a watch, so a
    capacity regression is caught by the test suite instead of shipping a
    duplicate card.
    """

# Intake aliases -> tactical-style family. Keys are compared after the value is
# lower-cased and its separators (spaces / hyphens / slashes) collapse to a
# single underscore, so "Out-Boxer", "out boxer" and "out_boxer" all match the
# same alias. Sport is deliberately excluded upstream: a boxer is not assumed to
# be a distance striker.
_STYLE_ALIASES: dict[str, str] = {
    # distance striker
    "distance_striker": "distance_striker",
    "distance": "distance_striker",
    "distance_fighter": "distance_striker",
    "outside_fighter": "distance_striker",
    "out_fighter": "distance_striker",
    "outfighter": "distance_striker",
    "out_boxer": "distance_striker",
    "outboxer": "distance_striker",
    "range_fighter": "distance_striker",
    "range_striker": "distance_striker",
    "long_range_striker": "distance_striker",
    "long_range": "distance_striker",
    "rangy": "distance_striker",
    "point_fighter": "distance_striker",
    # brawler / pressure fighter
    "brawler": "brawler",
    "pressure_fighter": "brawler",
    "pressure": "brawler",
    "inside_fighter": "brawler",
    "infighter": "brawler",
    "in_fighter": "brawler",
    "swarmer": "brawler",
    "volume_pressure": "brawler",
    "volume_puncher": "brawler",
    "aggressive": "brawler",
    "forward_pressure": "brawler",
    "slugger": "brawler",
    # counter striker
    "counter_striker": "counter_striker",
    "counter_puncher": "counter_striker",
    "counterpuncher": "counter_striker",
    "counter_fighter": "counter_striker",
    "counter": "counter_striker",
    "reactive_counter_fighter": "counter_striker",
    "reactive_counter": "counter_striker",
    "reactive": "counter_striker",
    "counter_attacker": "counter_striker",
}

# Athlete-model fields that may carry a tactical/technical style. ``sport`` is
# intentionally absent — style must come from a declared style, never inferred
# from the sport.
_STYLE_FIELDS = (
    "tactical_style",
    "tactical_styles",
    "style_tactical",
    "technical_styles",
    "style_technical",
    "fighting_style",
    "fighting_styles",
    "style",
)

_PHASE_ALIASES: dict[str, str] = {
    "gpp": "GPP",
    "general_prep": "GPP",
    "general_preparation": "GPP",
    "general_physical_preparation": "GPP",
    "base": "GPP",
    "early_camp": "GPP",
    "early": "GPP",
    "foundation": "GPP",
    "spp": "SPP",
    "specific_prep": "SPP",
    "specific_preparation": "SPP",
    "specific_physical_preparation": "SPP",
    "specific": "SPP",
    "sharpening": "SPP",
    "taper": "TAPER",
    "taper_week": "TAPER",
    "fight_week": "TAPER",
    "fightweek": "TAPER",
    "peak": "TAPER",
    "peaking": "TAPER",
}


def _collapse(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    for sep in (" ", "-", "/", ".", "+"):
        text = text.replace(sep, "_")
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_")


def normalize_tactical_style(value: Any) -> str:
    """Normalise a single intake style token into a tactical-style family.

    Unknown or empty values fall back to ``"generic"`` so a missing/unsupported
    style is always safe. A value already equal to a family name is returned
    unchanged.
    """
    token = _collapse(value)
    if not token:
        return "generic"
    if token in STYLE_FAMILIES:
        return token
    if token in _STYLE_ALIASES:
        return _STYLE_ALIASES[token]
    # A multi-word token may still contain a recognised alias phrase
    # ("orthodox out-boxer" -> "out_boxer").
    for alias, family in _STYLE_ALIASES.items():
        if alias in token:
            return family
    return "generic"


def extract_tactical_style(athlete_model: dict[str, Any] | None) -> str:
    """Resolve the athlete's tactical-style family from the athlete model.

    Scans the declared style fields in priority order and returns the first
    recognised family. Returns ``"generic"`` when nothing declared maps to a
    supported family (missing or unsupported style).
    """
    if not isinstance(athlete_model, dict):
        return "generic"
    for field_name in _STYLE_FIELDS:
        raw = athlete_model.get(field_name)
        if raw is None:
            continue
        values: Iterable[Any]
        if isinstance(raw, (list, tuple, set)):
            values = raw
        else:
            values = [raw]
        for value in values:
            family = normalize_tactical_style(value)
            if family != "generic":
                return family
    return "generic"


def normalize_camp_phase(value: Any) -> str:
    """Normalise a phase label into ``GPP`` / ``SPP`` / ``TAPER``.

    Unknown values default to ``GPP`` (the analytical, information-building
    phase) so an ambiguous label never selects a taper cue-compression task.
    """
    token = _collapse(value)
    if not token:
        return "GPP"
    upper = token.upper()
    if upper in PHASES:
        return upper
    return _PHASE_ALIASES.get(token, "GPP")


# --- content model ---------------------------------------------------------


@dataclass(frozen=True)
class TacticalWatch:
    """One selectable Fight Tactical Watch.

    ``instructions`` are the athlete's required output for the session, phrased
    as labelled prompts. They are authored distinctly per watch — there is no
    shared four-line output contract.
    """

    key: str
    name: str
    style: str
    phase: str
    why: str
    intent: str
    focus: str
    reset: str
    anchor: str
    context: str
    duration_minutes: int
    instructions: tuple[str, ...]
    progress: str

    def metadata(self) -> dict[str, str]:
        return watch_metadata(self)


def _w(
    style: str,
    phase: str,
    slug: str,
    name: str,
    *,
    why: str,
    intent: str,
    focus: str,
    reset: str,
    anchor: str,
    context: str,
    instructions: tuple[str, ...],
    progress: str,
    duration_minutes: int,
) -> TacticalWatch:
    return TacticalWatch(
        key=f"{style}.{phase.lower()}.{slug}",
        name=name,
        style=style,
        phase=phase,
        why=why,
        intent=intent,
        focus=focus,
        reset=reset,
        anchor=anchor,
        context=context,
        duration_minutes=duration_minutes,
        instructions=instructions,
        progress=progress,
    )


_GPP_MIN = 10
_SPP_MIN = 10
_TAPER_MIN = 8


# --- Distance striker library ---------------------------------------------

_DISTANCE_STRIKER: dict[str, tuple[TacticalWatch, ...]] = {
    "GPP": (
        _w(
            "distance_striker", "GPP", "range_map", "Range Map",
            why="Establish the ranges where you can score without being drawn into the opponent's preferred exchange.",
            intent="Control the space before trying to increase output.",
            focus="Notice where each fighter can land without overreaching.",
            reset="Return to the last range where you could see and react clearly.",
            anchor="Make the opponent cross your range before they can attack.",
            context="Early-camp range study for a distance striker.",
            instructions=(
                "Safe range: where can you score while remaining difficult to reach?",
                "Danger range: where is the opponent most dangerous?",
                "Range weapon: which strike controls the space?",
                "Distance rule: write one rule you will use in technical training.",
            ),
            progress="Test the distance rule during the next technical session.",
            duration_minutes=_GPP_MIN,
        ),
        _w(
            "distance_striker", "GPP", "lead_hand_battle", "Lead-Hand Battle",
            why="Understand how your lead hand controls entry and distance before an opponent is ever named.",
            intent="Own the lead-hand exchange instead of trading it evenly.",
            focus="Watch what the lead hand does in the half-second before every entry.",
            reset="Re-touch the lead hand and re-measure the gap before committing.",
            anchor="Win the lead-hand touch and the entry belongs to you.",
            context="Early-camp lead-hand study for a distance striker.",
            instructions=(
                "Opponent's normal jab reaction: how do fighters answer a jab at range?",
                "Your lead-hand answer: which lead-hand action beats that reaction?",
                "Follow-up action: what comes immediately after the lead hand lands?",
                "One action to avoid: which lead-hand habit gets you countered?",
            ),
            progress="Drill the chosen lead-hand answer and follow-up on the pads this week.",
            duration_minutes=_GPP_MIN,
        ),
        _w(
            "distance_striker", "GPP", "exit_discipline", "Exit Discipline",
            why="Identify whether you stay in range too long after scoring and cost yourself the return.",
            intent="Leave the exchange a beat earlier than feels natural.",
            focus="Mark the exact frame where the scoring stops and the standing-still starts.",
            reset="Step out to your strong side and re-establish distance.",
            anchor="Score, then be gone before the answer arrives.",
            context="Early-camp exit study for a distance striker.",
            instructions=(
                "Most common current exit: how do you usually leave after scoring?",
                "Stay-too-long moment: when do you linger one beat too long?",
                "Safest exit side: which direction keeps you off the return?",
                "Exit rule: write one exit rule to rehearse this week.",
            ),
            progress="Rehearse the exit rule on the bag and in light technical rounds.",
            duration_minutes=_GPP_MIN,
        ),
    ),
    "SPP": (
        _w(
            "distance_striker", "SPP", "intercept_the_entry", "Intercept the Entry",
            why="Stop the opponent's pressure before it reaches the pocket where they want to fight.",
            intent="Meet the entry early rather than absorbing it late.",
            focus="Read the opponent's first committing step, not their hands.",
            reset="Re-set your feet to the intercepting position after each attempt.",
            anchor="Their entry is your cue to fire, not to retreat blindly.",
            context="Opponent-specific entry defence for a distance striker.",
            instructions=(
                "Opponent entry trigger: what movement starts their pressure?",
                "Intercepting action: what stops it before the pocket?",
                "Exit direction: where do you go once you have intercepted?",
                "Reset position: what stance do you return to?",
            ),
            progress="Rehearse the intercept-and-exit against a pressure partner this week.",
            duration_minutes=_SPP_MIN,
        ),
        _w(
            "distance_striker", "SPP", "exit_lane_audit", "Exit Lane Audit",
            why="Choose the safest exit based on the opponent's pursuit and their strongest side.",
            intent="Pre-decide each exit so you never freeze in the pocket.",
            focus="Track which way the opponent cuts after you punch.",
            reset="Return to the exit lane that keeps their power hand away.",
            anchor="Every combination already has its exit chosen.",
            context="Opponent-specific exit planning for a distance striker.",
            instructions=(
                "Exit after the jab: which lane is open?",
                "Exit after the cross: which lane is open?",
                "Exit under pressure: where do you go when rushed?",
                "Direction to avoid: which exit walks onto their power?",
            ),
            progress="Shadow each exit lane after its combination before sparring this week.",
            duration_minutes=_SPP_MIN,
        ),
        _w(
            "distance_striker", "SPP", "rope_and_corner_escape", "Rope and Corner Escape",
            why="Prepare a calm escape against an opponent who cuts the ring and traps you on the ropes.",
            intent="Turn the trap into a pivot, not a firefight.",
            focus="Spot the step that pins you before your back touches the ropes.",
            reset="Pivot off the ropes and re-open the centre.",
            anchor="The ropes are a doorway out, not a place to trade.",
            context="Opponent-specific ring-craft for a distance striker under pressure.",
            instructions=(
                "Escape trigger: what tells you the ring is being cut?",
                "First defensive action: what buys you the half-second to move?",
                "Exit route: which pivot returns you to open space?",
                "Range reset: how do you re-establish your distance after escaping?",
            ),
            progress="Drill the rope pivot and range reset in constrained-space rounds this week.",
            duration_minutes=_SPP_MIN,
        ),
    ),
    "TAPER": (
        _w(
            "distance_striker", "TAPER", "first_round_range_script", "First-Round Range Script",
            why="Confirm the first-round distance plan using patterns you have already trained.",
            intent="Walk in knowing your opening distance, not discovering it.",
            focus="Confirm the one range you will own from the first bell.",
            reset="If it gets close, step out and re-take your distance.",
            anchor="Touch the jab, hold the range, exit left.",
            context="Fight-week confirmation for a distance striker — no new theory.",
            instructions=(
                "Opening weapon: what do you lead with?",
                "First range test: how do you measure the opponent early?",
                "Response if rushed: what is your one answer to early pressure?",
                "First-round cue: write one short cue for the opening round.",
            ),
            progress="Repeat the first-round cue during your fight-week movement session.",
            duration_minutes=_TAPER_MIN,
        ),
    ),
}


# --- Brawler / pressure-fighter library -----------------------------------

_BRAWLER: dict[str, tuple[TacticalWatch, ...]] = {
    "GPP": (
        _w(
            "brawler", "GPP", "pressure_route_scan", "Pressure Route Scan",
            why="Understand how opponents retreat and where your pressure should be directed to trap them.",
            intent="Steer the opponent, do not just chase them.",
            focus="Watch which way fighters break when pressure arrives.",
            reset="Re-take the centre and re-start the cut.",
            anchor="Send them where you want them, then close the door.",
            context="Early-camp pressure-route study for a pressure fighter.",
            instructions=(
                "Preferred opponent retreat side: which way do they usually break?",
                "Ring-cutting direction: which way do you step to cut it off?",
                "Pressure trigger: what movement of yours starts the retreat?",
                "Intended trap location: where do you want them pinned?",
            ),
            progress="Practise cutting toward the trap location in footwork drills this week.",
            duration_minutes=_GPP_MIN,
        ),
        _w(
            "brawler", "GPP", "safe_entry_builder", "Safe Entry Builder",
            why="Enter the pocket without walking onto clean shots on the way in.",
            intent="Arrive behind cover, not behind your chin.",
            focus="Watch the guard and head position during each entry, not the punches.",
            reset="Re-set your guard before attempting the next entry.",
            anchor="Get in clean and the exchange is already yours.",
            context="Early-camp entry-safety study for a pressure fighter.",
            instructions=(
                "Entry setup: what feint or step opens the door?",
                "Guard position: where are your hands as you close?",
                "First punch: which shot do you enter behind?",
                "Head position: where is your head as you arrive?",
            ),
            progress="Drill the covered entry and first punch on the pads this week.",
            duration_minutes=_GPP_MIN,
        ),
        _w(
            "brawler", "GPP", "pressure_reset", "Pressure Reset",
            why="Prevent your pressure from turning into reckless, unbalanced chasing.",
            intent="Keep pressure heavy but composed, never frantic.",
            focus="Catch the moment pressure tips into chasing.",
            reset="Pause, re-set the feet, and re-apply pressure behind the jab.",
            anchor="Relentless is a rhythm, not a sprint.",
            context="Early-camp composure study for a pressure fighter.",
            instructions=(
                "Rushed signal: what tells you pressure is becoming a chase?",
                "Safe pause action: what steadies you without giving up ground?",
                "Re-entry setup: how do you resume pressure calmly?",
                "Pressure rule: write one rule that keeps your pressure controlled.",
            ),
            progress="Apply the pause-and-re-enter rule during conditioning rounds this week.",
            duration_minutes=_GPP_MIN,
        ),
    ),
    "SPP": (
        _w(
            "brawler", "SPP", "pocket_exchange_map", "Pocket Exchange Map",
            why="Learn what the opponent does after their first two punches so you can answer it.",
            intent="Have your answer ready before their sequence finishes.",
            focus="Track the opponent's third action in every pocket exchange.",
            reset="Smother or step, then re-set to fire again.",
            anchor="Their combination ends where your answer begins.",
            context="Opponent-specific pocket study for a pressure fighter.",
            instructions=(
                "Opponent's common pocket sequence: what are their first shots?",
                "Your answer: what do you fire back with?",
                "Best finishing shot: which of yours lands cleanest?",
                "Exit or smother decision: do you tie up or step off after?",
            ),
            progress="Rehearse the answer-and-decision against a pocket-fighting partner this week.",
            duration_minutes=_SPP_MIN,
        ),
        _w(
            "brawler", "SPP", "body_attack_opportunity", "Body Attack Opportunity",
            why="Identify when a body attack is available without entering blindly into a counter.",
            intent="Invest in the body when it is safe, not whenever it is open.",
            focus="Watch what the opponent's elbows and hands do when you dip.",
            reset="Return the guard high before and after the body shot.",
            anchor="The body pays off later — bank it safely now.",
            context="Opponent-specific body-work study for a pressure fighter.",
            instructions=(
                "Body opening: when does the body become available?",
                "Setup punch: what shot hides the level change?",
                "Body target: which body target is cleanest?",
                "Head follow-up: what comes up top after the body shot?",
            ),
            progress="Drill the setup, body shot and head follow-up on the bag this week.",
            duration_minutes=_SPP_MIN,
        ),
        _w(
            "brawler", "SPP", "smother_and_reset", "Smother and Reset",
            why="Stop the opponent returning fire immediately after your combination.",
            intent="Close the space you just created before they use it.",
            focus="Watch the instant after your last punch, not the punch itself.",
            reset="Smother, re-position, and re-open on your terms.",
            anchor="End every combination in control, not in a trade.",
            context="Opponent-specific follow-through study for a pressure fighter.",
            instructions=(
                "Post-combination position: where are you when your shots end?",
                "Response if they fire back: what covers the return?",
                "Smother position: how do you tie up or close the space?",
                "Reset action: what re-opens the exchange on your terms?",
            ),
            progress="Rehearse the smother-and-reset after combinations in sparring this week.",
            duration_minutes=_SPP_MIN,
        ),
    ),
    "TAPER": (
        _w(
            "brawler", "TAPER", "first_round_pressure_script", "First-Round Pressure Script",
            why="Confirm controlled pressure for the opening round without a reckless start.",
            intent="Start heavy and composed, not wild.",
            focus="Confirm the one pressure action you open with.",
            reset="If it gets sloppy, re-set behind the jab and close again.",
            anchor="Close calmly, touch the body, block the exit.",
            context="Fight-week confirmation for a pressure fighter — no new theory.",
            instructions=(
                "Opening pressure action: how do you begin closing the distance?",
                "First ring cut: which way do you steer them first?",
                "First combination: what is your opening combination?",
                "Reset cue: write one short cue to stay composed.",
            ),
            progress="Repeat the reset cue during your fight-week movement session.",
            duration_minutes=_TAPER_MIN,
        ),
    ),
}


# --- Counter-striker library ----------------------------------------------

_COUNTER_STRIKER: dict[str, tuple[TacticalWatch, ...]] = {
    "GPP": (
        _w(
            "counter_striker", "GPP", "trigger_library", "Trigger Library",
            why="Build a library of visible signals that reliably predict an incoming attack.",
            intent="Read the tell, not the punch.",
            focus="Watch the shoulder, weight and feet that precede each shot.",
            reset="Return your eyes to the reliable cue after every exchange.",
            anchor="You are early because you saw it start.",
            context="Early-camp read-building study for a counter striker.",
            instructions=(
                "Jab trigger: what visibly precedes the jab?",
                "Cross trigger: what visibly precedes the cross?",
                "Entry trigger: what precedes a committed entry?",
                "Most reliable cue: which single tell do you trust most?",
            ),
            progress="Call the most reliable cue aloud while watching rounds this week.",
            duration_minutes=_GPP_MIN,
        ),
        _w(
            "counter_striker", "GPP", "draw_the_lead", "Draw the Lead",
            why="Create the opponent's attack on purpose instead of waiting passively for it.",
            intent="Invite the shot you already have an answer for.",
            focus="Watch how small openings pull a predictable lead.",
            reset="Re-set the bait and re-offer the opening.",
            anchor="You chose which punch they threw.",
            context="Early-camp baiting study for a counter striker.",
            instructions=(
                "Bait: what opening do you deliberately show?",
                "Expected attack: what does that bait draw?",
                "Counter: what answers the drawn attack?",
                "Exit: how do you leave after countering?",
            ),
            progress="Rehearse one bait-counter-exit sequence on the pads this week.",
            duration_minutes=_GPP_MIN,
        ),
        _w(
            "counter_striker", "GPP", "counter_activity_check", "Counter Activity Check",
            why="Prevent counter-fighting from sliding into inactivity that loses rounds.",
            intent="Stay busy enough to win the round, not only the exchange.",
            focus="Notice how long you go without offering anything.",
            reset="Break the wait with a safe, active touch.",
            anchor="Active patience scores; passive waiting does not.",
            context="Early-camp activity study for a counter striker.",
            instructions=(
                "Safe information-gathering action: what can you throw to learn without risk?",
                "Wait-too-long moment: when does patience become inactivity?",
                "Provoking action: what safely forces a response?",
                "Activity rule: write one rule to keep you working.",
            ),
            progress="Hold the activity rule for a full round in sparring this week.",
            duration_minutes=_GPP_MIN,
        ),
    ),
    "SPP": (
        _w(
            "counter_striker", "SPP", "first_beat_or_second_beat", "First Beat or Second Beat",
            why="Decide whether to counter immediately or after the opponent continues their sequence.",
            intent="Pick the beat before the exchange, not during it.",
            focus="Watch whether this opponent commits to one shot or a string.",
            reset="Re-choose your beat based on what they just showed.",
            anchor="Right punch, right beat, right exit.",
            context="Opponent-specific timing study for a counter striker.",
            instructions=(
                "First-beat condition: when do you counter the first shot?",
                "Second-beat condition: when do you wait for the follow-up?",
                "Preferred counter: which counter do you trust here?",
                "Safety rule: what keeps you safe if you read it wrong?",
            ),
            progress="Drill first-beat and second-beat counters off the same feed this week.",
            duration_minutes=_SPP_MIN,
        ),
        _w(
            "counter_striker", "SPP", "counter_and_exit", "Counter and Exit",
            why="Avoid staying available in the pocket after you land the counter.",
            intent="Counter and leave in one motion.",
            focus="Watch what is still coming after the opponent's first shot.",
            reset="Step to safe distance and re-set your guard.",
            anchor="Land it, then be somewhere else.",
            context="Opponent-specific exit study for a counter striker.",
            instructions=(
                "Counter: which counter are you landing?",
                "Exit direction: where do you move immediately after?",
                "Guard position: where are your hands on the way out?",
                "Reset distance: what range do you re-establish?",
            ),
            progress="Add the exit and reset to your counter on the pads this week.",
            duration_minutes=_SPP_MIN,
        ),
        _w(
            "counter_striker", "SPP", "counter_the_counter", "Counter the Counter",
            why="Prepare for the opponent adapting to your first counter and answering it.",
            intent="Have a second answer ready before they adjust.",
            focus="Watch how the opponent responds the second time you counter.",
            reset="If the read is gone, abort and re-set to neutral.",
            anchor="Your first counter is bait for your second.",
            context="Opponent-specific adjustment study for a counter striker.",
            instructions=(
                "Initial counter: what do you land first?",
                "Likely opponent adjustment: how do they adapt to it?",
                "Second answer: what beats their adjustment?",
                "Abort cue: what tells you to stop and reset instead?",
            ),
            progress="Rehearse the second answer and abort cue in reactive sparring this week.",
            duration_minutes=_SPP_MIN,
        ),
    ),
    "TAPER": (
        _w(
            "counter_striker", "TAPER", "first_round_patience_script", "First-Round Patience Script",
            why="Confirm active patience for the opening round rather than passive waiting.",
            intent="Be patient and busy from the first bell.",
            focus="Confirm the one safe action that keeps you working early.",
            reset="If you drift passive, throw the safe bait and re-engage.",
            anchor="Show the jab, draw the return, counter and leave.",
            context="Fight-week confirmation for a counter striker — no new theory.",
            instructions=(
                "First information-gathering action: how do you open safely?",
                "Safe bait: which bait do you trust early?",
                "Preferred counter: what is your go-to first counter?",
                "Activity cue: write one short cue to stay busy.",
            ),
            progress="Repeat the activity cue during your fight-week movement session.",
            duration_minutes=_TAPER_MIN,
        ),
    ),
}


# --- Generic library -------------------------------------------------------
# Used when style is missing/unsupported, or when a same-phase style bank is
# exhausted and an additional distinct weekly watch is required.

_GENERIC: dict[str, tuple[TacticalWatch, ...]] = {
    "GPP": (
        _w(
            "generic", "GPP", "opponent_pattern_scan", "Opponent Pattern Scan",
            why="Find the repeated patterns in the footage so training targets something real.",
            intent="Look for what happens again, not what happened once.",
            focus="Watch for the sequence that repeats across rounds.",
            reset="Return attention to the repeated pattern when you drift.",
            anchor="Patterns beat highlights.",
            context="Early-camp pattern study.",
            instructions=(
                "Main repeated pattern: what happens again and again?",
                "Best opportunity: where does that pattern open a chance?",
                "Main danger: where does that pattern hurt you?",
                "One observation to test in training: what will you check this week?",
            ),
            progress="Bring the one observation into this week's technical session.",
            duration_minutes=_GPP_MIN,
        ),
        _w(
            "generic", "GPP", "threat_priority", "Threat Priority",
            why="Rank the threats so preparation starts with the one that matters most.",
            intent="Solve the biggest problem first.",
            focus="Weigh how often and how badly each threat lands.",
            reset="Come back to the top-priority threat when the plan sprawls.",
            anchor="One threat, one first answer.",
            context="Early-camp threat-ranking study.",
            instructions=(
                "Top three threats: what are the three biggest?",
                "Highest-priority threat: which one leads?",
                "First answer: what is your first response to it?",
                "Training note: how will you rehearse that answer?",
            ),
            progress="Rehearse the first answer to the top threat this week.",
            duration_minutes=_GPP_MIN,
        ),
        _w(
            "generic", "GPP", "defensive_habit_review", "Defensive Habit Review",
            why="Review your own defensive habits so a repeated mistake does not follow you into the fight.",
            intent="Fix the habit, not just the moment.",
            focus="Watch your first reaction when a shot comes back.",
            reset="Return to the position that restores your control.",
            anchor="Clean defence buys clean offence.",
            context="Early-camp defensive self-review.",
            instructions=(
                "First defensive reaction: what do you do when hit at first?",
                "Repeated defensive mistake: which error keeps recurring?",
                "Control-restoring position: what stance brings you back?",
                "Defensive rule: write one rule to drill this week.",
            ),
            progress="Drill the control-restoring position after contact this week.",
            duration_minutes=_GPP_MIN,
        ),
        _w(
            "generic", "GPP", "rhythm_and_tempo_map", "Rhythm and Tempo Map",
            why="Understand the pace you naturally settle into so you can control tempo instead of following it.",
            intent="Set the pace rather than react to it.",
            focus="Watch when the tempo speeds up and who caused it.",
            reset="Return to your own steady count when the pace runs away.",
            anchor="You choose the speed of the round.",
            context="Early-camp tempo self-study.",
            instructions=(
                "Natural pace: what tempo do you settle into?",
                "Speed-up trigger: what makes you rush?",
                "Slow-down tool: what action lets you reset the pace?",
                "Tempo rule: write one rule for owning the pace.",
            ),
            progress="Hold your chosen tempo for a full round this week.",
            duration_minutes=_GPP_MIN,
        ),
        _w(
            "generic", "GPP", "position_baseline", "Position Baseline",
            why="Establish the ring positions where you are strongest before opponent-specific planning.",
            intent="Fight from your positions, not wherever you land.",
            focus="Notice where you score cleanly and where you get stuck.",
            reset="Move back to your strongest position after each exchange.",
            anchor="Own the ground before you own the exchange.",
            context="Early-camp positioning self-study.",
            instructions=(
                "Strongest position: where do you score most cleanly?",
                "Weakest position: where do you struggle?",
                "Route in: how do you reach your strong position?",
                "Position rule: write one rule for holding it.",
            ),
            progress="Rehearse the route into your strong position this week.",
            duration_minutes=_GPP_MIN,
        ),
        _w(
            "generic", "GPP", "entry_inventory", "Entry Inventory",
            why="Catalogue the ways you get in so you enter on purpose instead of by habit.",
            intent="Enter behind a plan, not on instinct alone.",
            focus="Watch what sets up each successful entry.",
            reset="Return to your most reliable entry when unsure.",
            anchor="A known entry beats a hopeful one.",
            context="Early-camp entry self-study.",
            instructions=(
                "Main entry: which entry do you use most?",
                "Setup: what makes that entry work?",
                "Backup entry: what is your second option?",
                "Entry rule: write one rule for entering safely.",
            ),
            progress="Drill your main and backup entries on the pads this week.",
            duration_minutes=_GPP_MIN,
        ),
        _w(
            "generic", "GPP", "recovery_habit_review", "Recovery Habit Review",
            why="Study how you recover after a hard exchange so a bad moment does not become a bad round.",
            intent="Recover on a plan, not on adrenaline.",
            focus="Watch the seconds right after a hard exchange.",
            reset="Take your rehearsed breath-and-move before re-engaging.",
            anchor="One clean recovery steadies the whole round.",
            context="Early-camp recovery self-study.",
            instructions=(
                "Recovery habit: what do you do after a hard exchange?",
                "Weak moment: when does recovery break down?",
                "Steadying action: what calms and protects you?",
                "Recovery rule: write one rule for resetting after adversity.",
            ),
            progress="Rehearse the steadying action under fatigue this week.",
            duration_minutes=_GPP_MIN,
        ),
        _w(
            "generic", "GPP", "feint_and_read_study", "Feint and Read Study",
            why="Learn which feints draw a reaction so you can lead the opponent instead of guessing.",
            intent="Make the opponent show you their hand.",
            focus="Watch which feints earn a real reaction.",
            reset="Return to the feint that reliably draws a response.",
            anchor="A good feint answers the question for you.",
            context="Early-camp feint self-study.",
            instructions=(
                "Reliable feint: which feint draws a reaction?",
                "Reaction: what does it pull from the opponent?",
                "Follow-up: what do you do with that reaction?",
                "Feint rule: write one rule for using feints safely.",
            ),
            progress="Rehearse one feint-and-follow-up sequence this week.",
            duration_minutes=_GPP_MIN,
        ),
        _w(
            "generic", "GPP", "output_and_composure_check", "Output and Composure Check",
            why="Balance work rate against composure so you stay busy without losing control.",
            intent="Work hard and stay calm at the same time.",
            focus="Notice where output tips into wildness.",
            reset="Return to a controlled, repeatable combination.",
            anchor="Busy and composed wins rounds.",
            context="Early-camp work-rate self-study.",
            instructions=(
                "Comfortable output: how much can you throw and stay balanced?",
                "Tipping point: when does output become wild?",
                "Controlled combination: which combination stays clean?",
                "Output rule: write one rule for staying busy but composed.",
            ),
            progress="Hold your controlled combination at pace this week.",
            duration_minutes=_GPP_MIN,
        ),
    ),
    "SPP": (
        _w(
            "generic", "SPP", "trigger_response_builder", "Trigger-Response Builder",
            why="Turn opponent reads into clear if-then responses you can execute under pressure.",
            intent="Make each read a reflex, not a decision.",
            focus="Pair every trigger you see with a single response.",
            reset="Return to your reset position after each if-then rep.",
            anchor="When I see it, I already know what I do.",
            context="Opponent-specific if-then study.",
            instructions=(
                "When I see: what is the trigger?",
                "I do: what is the response?",
                "Then I exit: how do you leave?",
                "I reset with: what returns you to ready?",
            ),
            progress="Rehearse the full if-then-exit-reset chain on the pads this week.",
            duration_minutes=_SPP_MIN,
        ),
        _w(
            "generic", "SPP", "round_flow_map", "Round Flow Map",
            why="Map how a round tends to flow so you know when to take control.",
            intent="Own the minute that decides the round.",
            focus="Watch how behaviour changes from the first minute to the last.",
            reset="Re-anchor to your plan at the start of each minute.",
            anchor="Take the round in the minute that counts.",
            context="Opponent-specific round-tempo study.",
            instructions=(
                "First-minute behaviour: what happens early?",
                "Middle-minute behaviour: what happens in the middle?",
                "Final-minute behaviour: what happens late?",
                "Best time to take control: when do you make your move?",
            ),
            progress="Rehearse your control move at the chosen minute in sparring this week.",
            duration_minutes=_SPP_MIN,
        ),
        _w(
            "generic", "SPP", "scoring_map", "Scoring Map",
            why="Define exactly how you score against this opponent and what to stop wasting.",
            intent="Repeat what scores; cut what does not.",
            focus="Watch which of your actions actually land clean.",
            reset="Return to your cleanest scoring action when unsure.",
            anchor="Score with the shot that already works.",
            context="Opponent-specific scoring study.",
            instructions=(
                "Cleanest scoring action: what lands most reliably?",
                "Position to control: which position lets you score?",
                "Combination to repeat: which combination works?",
                "Low-value action to avoid: what should you stop doing?",
            ),
            progress="Drill the repeatable combination from its scoring position this week.",
            duration_minutes=_SPP_MIN,
        ),
        _w(
            "generic", "SPP", "momentum_shift_review", "Momentum Shift Review",
            why="Understand what changes momentum in a round so you can create or survive it.",
            intent="Recognise the shift as it starts.",
            focus="Watch what the winning fighter did just before momentum turned.",
            reset="Apply the correct response the moment you feel the shift.",
            anchor="Momentum is earned by the right response.",
            context="Opponent-specific momentum study.",
            instructions=(
                "What changed the round: what caused the shift?",
                "What the winning fighter noticed: what read did they act on?",
                "Correct response: what is the right answer to that shift?",
                "Momentum rule: write one rule for handling the swing.",
            ),
            progress="Rehearse the correct response to a momentum swing in sparring this week.",
            duration_minutes=_SPP_MIN,
        ),
        _w(
            "generic", "SPP", "adversity_reset", "Adversity Reset",
            why="Have a rehearsed route back to control for the moment the fight goes wrong.",
            intent="Get safe first, then get back to the plan.",
            focus="Watch how composed fighters recover after being hurt or rushed.",
            reset="Say your reset phrase and take the next safe action.",
            anchor="One safe action rebuilds control.",
            context="Opponent-specific adversity study.",
            instructions=(
                "Immediate defensive action: what do you do first when it goes bad?",
                "Reset phrase: what do you say to yourself?",
                "Next safe action: what comes after the reset?",
                "Route back to control: how do you return to the plan?",
            ),
            progress="Rehearse the reset phrase and safe action under fatigue this week.",
            duration_minutes=_SPP_MIN,
        ),
        _w(
            "generic", "SPP", "opponent_tendency_map", "Opponent Tendency Map",
            why="Map the opponent's most repeated action so you know what is coming most often.",
            intent="Prepare for their habit, not their highlight.",
            focus="Watch for the action the opponent returns to again and again.",
            reset="Come back to the top tendency when the read gets noisy.",
            anchor="Their favourite move is your prepared answer.",
            context="Opponent-specific tendency study.",
            instructions=(
                "Top tendency: what does the opponent do most?",
                "Trigger: what precedes it?",
                "Answer: what beats it?",
                "Tendency rule: write one rule for handling it.",
            ),
            progress="Rehearse the answer to their top tendency this week.",
            duration_minutes=_SPP_MIN,
        ),
        _w(
            "generic", "SPP", "entry_route_plan", "Entry Route Plan",
            why="Choose the safest route past the opponent's first line of defence.",
            intent="Get in on a planned line, not a hopeful lunge.",
            focus="Watch what opens the opponent's guard on the way in.",
            reset="Return to your chosen entry line after a failed attempt.",
            anchor="A planned route in is a safe route in.",
            context="Opponent-specific entry-route study.",
            instructions=(
                "Opening: what gap does the opponent leave?",
                "Route: which line or angle uses that gap?",
                "Setup: what reaction opens the route?",
                "Entry rule: write one rule for using it safely.",
            ),
            progress="Drill the entry route against a partner this week.",
            duration_minutes=_SPP_MIN,
        ),
        _w(
            "generic", "SPP", "ring_position_plan", "Ring Position Plan",
            why="Decide where in the ring you want the fight to happen against this opponent.",
            intent="Fight where you win, not where they drag you.",
            focus="Watch where the opponent is most and least comfortable.",
            reset="Steer back to your chosen area of the ring.",
            anchor="Win the position, win the exchange.",
            context="Opponent-specific ring-position study.",
            instructions=(
                "Your area: where do you want the fight?",
                "Their area: where do they want it?",
                "Steering tool: what moves them to your area?",
                "Position rule: write one rule for keeping it there.",
            ),
            progress="Rehearse steering the fight to your area this week.",
            duration_minutes=_SPP_MIN,
        ),
        _w(
            "generic", "SPP", "exit_lane_plan", "Exit Lane Plan",
            why="Pre-choose the safest way out of each exchange against this opponent's pursuit.",
            intent="Leave every exchange with the exit already chosen.",
            focus="Watch which way the opponent follows after you fire.",
            reset="Take the exit lane that keeps their strong side away.",
            anchor="Every exchange has a planned way out.",
            context="Opponent-specific exit-lane study.",
            instructions=(
                "Pursuit: which way does the opponent chase?",
                "Safe lane: which exit avoids their power?",
                "Under pressure: where do you go when trapped?",
                "Exit rule: write one rule for leaving safely.",
            ),
            progress="Shadow your chosen exit lanes after combinations this week.",
            duration_minutes=_SPP_MIN,
        ),
        _w(
            "generic", "SPP", "clinch_and_break_plan", "Clinch and Break Plan",
            why="Prepare what to do when the exchange ties up so the clinch is not a surprise.",
            intent="Own the tie-up instead of surviving it.",
            focus="Watch what the opponent does the moment you tie up.",
            reset="Break to your chosen side and re-set your distance.",
            anchor="The clinch is a decision, not an accident.",
            context="Opponent-specific clinch study.",
            instructions=(
                "Clinch trigger: when does the exchange tie up?",
                "In the clinch: what does the opponent try?",
                "Your work: what do you do before the break?",
                "Break rule: write one rule for how and where to break.",
            ),
            progress="Rehearse a clean break-and-reset from the clinch this week.",
            duration_minutes=_SPP_MIN,
        ),
        _w(
            "generic", "SPP", "round_score_checklist", "Round-Score Checklist",
            why="Decide exactly what a winning round looks like against this opponent so you bank it clearly.",
            intent="Win the round on purpose, not by hoping.",
            focus="Watch what actually reads as scoring against this opponent.",
            reset="Return to the scoring action when the round drifts.",
            anchor="Score clearly and bank the round.",
            context="Opponent-specific round-scoring study.",
            instructions=(
                "Scoring action: what clearly scores here?",
                "Bank early: what do you land in the first minute?",
                "Close strong: what do you finish the round with?",
                "Score rule: write one rule for winning the round.",
            ),
            progress="Rehearse banking the round early and closing strong this week.",
            duration_minutes=_SPP_MIN,
        ),
    ),
    "TAPER": (
        _w(
            "generic", "TAPER", "corner_instruction_translation", "Corner Instruction Translation",
            why="Reduce a complicated corner instruction into one observable action you can execute.",
            intent="Turn advice into a single thing to watch and do.",
            focus="Confirm the one cue you can actually see mid-round.",
            reset="Return to the three-word cue when the corner gets noisy.",
            anchor="One instruction, one action.",
            context="Fight-week instruction compression — no new theory.",
            instructions=(
                "Full instruction: what does the corner want?",
                "What to notice: what is the observable cue?",
                "What to do: what is the single action?",
                "Three-word cue: compress it to three words.",
            ),
            progress="Say the three-word cue during your fight-week movement session.",
            duration_minutes=_TAPER_MIN,
        ),
        _w(
            "generic", "TAPER", "final_tactical_cue_card", "Final Tactical Cue Card",
            why="Reduce the whole plan to familiar cues only for the final taper compression.",
            intent="Carry cues, not a strategy essay.",
            focus="Confirm each cue is one you have already trained.",
            reset="Return to the reset phrase whenever the plan feels heavy.",
            anchor="Simple cues, calm head.",
            context="Fight-week final compression — cues only, no new theory.",
            instructions=(
                "One entry cue: how do you get in?",
                "One scoring cue: how do you score?",
                "One danger cue: what do you avoid?",
                "One reset phrase: how do you recover?",
                "One final sentence: your single closing thought.",
            ),
            progress="Read the cue card once before your fight-week movement session.",
            duration_minutes=_TAPER_MIN,
        ),
        _w(
            "generic", "TAPER", "first_action_confirmation", "First-Action Confirmation",
            why="Confirm the single opening action you have already trained so round one starts on autopilot.",
            intent="Start with a decision you have already made.",
            focus="Confirm the one action you open with — no new ideas.",
            reset="If the opening stalls, repeat the confirmed action once more.",
            anchor="One trained opening, thrown with certainty.",
            context="Fight-week opening confirmation — no new theory.",
            instructions=(
                "Opening action: what single action starts your fight?",
                "Cue to fire it: what tells you to go?",
                "If it lands: what is the immediate follow-up?",
                "One-word trigger: name the opening in one word.",
            ),
            progress="Rehearse the confirmed opening action in your fight-week movement session.",
            duration_minutes=_TAPER_MIN,
        ),
    ),
}


_LIBRARY: dict[str, dict[str, tuple[TacticalWatch, ...]]] = {
    "distance_striker": _DISTANCE_STRIKER,
    "brawler": _BRAWLER,
    "counter_striker": _COUNTER_STRIKER,
    "generic": _GENERIC,
}


# --- selection -------------------------------------------------------------


def _phase_bank(style: str, phase: str) -> tuple[TacticalWatch, ...]:
    return _LIBRARY.get(style, {}).get(phase, ())


def ordered_phase_bank(style: Any, phase: Any) -> tuple[TacticalWatch, ...]:
    """The full ordered selection bank for a ``(style, phase)`` request.

    Style-specific watches come first in their authored order, then the
    phase-matched generic watches as the exhaustion fallback. When the style is
    already generic (or unsupported), only the generic bank is returned. The
    first item is always the first authored watch of the style's phase bank, so
    the first occurrence in a phase is deterministic.
    """
    style_family = normalize_tactical_style(style) if isinstance(style, str) else style
    if style_family not in STYLE_FAMILIES:
        style_family = "generic"
    phase_key = normalize_camp_phase(phase)

    bank: list[TacticalWatch] = list(_phase_bank(style_family, phase_key))
    if style_family != "generic":
        seen = {w.key for w in bank}
        for watch in _phase_bank("generic", phase_key):
            if watch.key not in seen:
                bank.append(watch)
    return tuple(bank)


def select_tactical_watch(
    style: Any,
    phase: Any,
    used_keys: Iterable[str] | None = None,
) -> TacticalWatch:
    """Select the next unused Tactical Watch for a ``(style, phase)`` request.

    Deterministic: returns the first watch in :func:`ordered_phase_bank` whose
    key is not in ``used_keys``. Callers add the returned key to their own ledger
    so no key repeats within one camp. Raises :class:`TacticalWatchBankExhausted`
    when every watch in the style and generic banks is already used — there is no
    silent repetition fallback, so an under-sized bank fails loudly.
    """
    used = set(used_keys or ())
    bank = ordered_phase_bank(style, phase)
    for watch in bank:
        if watch.key not in used:
            return watch
    raise TacticalWatchBankExhausted(
        f"no unused Tactical Watch for style={style!r} phase={phase!r}: "
        f"bank holds {len(bank)} watch(es), all already used"
    )


def select_watch_by_occurrence(
    style: Any,
    phase: Any,
    occurrence: int,
) -> TacticalWatch:
    """Select the watch for the ``occurrence``-th appearance in a phase (1-based).

    Equivalent to :func:`select_tactical_watch` fed a ledger of the preceding
    occurrences. Raises :class:`TacticalWatchBankExhausted` when the occurrence
    exceeds the bank size — no clamping, so an over-run fails loudly.
    """
    bank = ordered_phase_bank(style, phase)
    index = max(1, int(occurrence)) - 1
    if index >= len(bank):
        raise TacticalWatchBankExhausted(
            f"occurrence {occurrence} exceeds the {len(bank)}-watch bank for "
            f"style={style!r} phase={phase!r}"
        )
    return bank[index]


# --- rendering-ready projections ------------------------------------------


def watch_metadata(watch: TacticalWatch) -> dict[str, str]:
    """Debug/selection metadata carried through the pipeline on a role/session."""
    return {
        "tactical_watch_key": watch.key,
        "tactical_watch_name": watch.name,
        "tactical_watch_style": watch.style,
        "tactical_watch_phase": watch.phase,
    }


def build_watch_display_text(watch: TacticalWatch, camp_focus: str = "") -> str:
    """Render the plan-markdown display text for a watch.

    This is the source text that flows into the Stage 2 plan and the structured
    conversion. It names the inner activity explicitly and lists the required
    output, so the plan markdown carries the specific watch rather than a
    generic film-watch stub.
    """
    lines = [
        f"Fight Tactical Watch: {watch.name} - {watch.duration_minutes} min",
        "",
        f"Why: {watch.why}",
        "",
        "Mindset",
        f"Intent: {watch.intent}",
        f"Focus: {watch.focus}",
        f"Reset: {watch.reset}",
        f"Anchor: {watch.anchor}",
        f"Context: {watch.context}",
        "",
        f"Inner activity: {watch.name}",
        f"Duration: {watch.duration_minutes} minutes",
        "Instructions:",
    ]
    lines.extend(f"- {item}" for item in watch.instructions)
    lines.append(f"Progress: {watch.progress}")
    if camp_focus:
        lines.extend(["", camp_focus])
    return "\n".join(lines)


def canonical_watch_signature(watch: TacticalWatch) -> tuple[Any, ...]:
    """A hashable canonical representation of every athlete-visible field.

    Two watches whose signatures are equal render identically to the athlete.
    Used by the uniqueness tests to prove no two watches are the same beyond a
    title-only difference.
    """
    return (
        watch.name,
        watch.why,
        watch.intent,
        watch.focus,
        watch.reset,
        watch.anchor,
        watch.context,
        watch.name,  # inner activity title
        tuple(watch.instructions),
        watch.progress,
    )


def all_watches() -> tuple[TacticalWatch, ...]:
    """Every watch in the library, in a stable order (style, phase, authored)."""
    watches: list[TacticalWatch] = []
    for style in STYLE_FAMILIES:
        for phase in PHASES:
            watches.extend(_phase_bank(style, phase))
    return tuple(watches)
