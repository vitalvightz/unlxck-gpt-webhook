"""Regression suite for the late-camp -> fight-week countdown handoff fix.

Background
----------
PR #2383 removed the D-21 -> D-14 ``bridge_compression_payload`` architecture
cliff: D-14 and further out now stay on the normal camp planner, and continuation
ownership narrowed to D-13 inward (``_is_countdown_continuation_start`` == 3..13).
An unintended side effect was that a plan *generated* at D-14 or further out
stopped carrying the downstream D-13 -> D-0 countdown mode sequence into Stage 2
rendering: its continuous calendar still reaches fight week, but the Stage 2
handoff no longer told the finalizer that those scheduled tail days follow the
existing late-fight / fight-week contracts. Normal-camp output could therefore
survive into actual fight week (e.g. D-1 equipment work), even though
``pre_fight_day_payload`` already bans equipment on D-1.

The fix restores ONLY the downstream continuation (D-13 -> D-0), never the bridge:

* ``_camp_downstream_countdown_continuation`` returns the D-13 -> D-0 sequence for
  a D-14+ plan (identical to what a D-13-generated plan carries), and empty
  otherwise.
* ``_countdown_continuation_map_from_packet`` falls back to it when the normal-camp
  planning brief carries no late_fight_plan_spec / days_out_payload.

These tests use SEMANTIC assertions (routing + the existing mode contracts, plan
*meaning* in the deterministic role map), never exercise-name snapshots. Where a
guarantee is enforced by an existing late-fight contract, the test proves the tail
day is *routed* to that contract and that the contract is the single source of
truth for the ban — it does not re-implement the ban.

``days_until_fight`` is made deterministic by pinning ``input_parsing._utc_now`` to
a fixed instant a chosen number of days before a fixed Friday fight (same
technique as ``test_late_camp_architecture_cliff``).
"""

from __future__ import annotations

import datetime as _dt
import logging
import re

import pytest

from fightcamp import input_parsing
from fightcamp.input_parsing import PlanInput
from fightcamp.plan_pipeline_blocks import generate_plan_blocks
from fightcamp.plan_pipeline_rendering import build_stage2_outputs
from fightcamp.plan_pipeline_runtime import (
    RenderedPlanBundle,
    build_runtime_context,
    prime_plan_banks,
)
from fightcamp.stage2_payload_late_fight import (
    _camp_downstream_countdown_continuation,
    _countdown_mode_sequence,
    _days_out_payload_mode,
    _handoff_mode_instructions,
    _is_app_owned_visible_role,
    _uses_late_fight_stage2_payload,
)

logging.disable(logging.CRITICAL)

FIGHT_FRIDAY = _dt.date(2026, 1, 30)
assert FIGHT_FRIDAY.weekday() == 4, "fixture fight date must be a Friday"

# The canonical downstream fight-week windows, expressed as (stage_key,
# payload_mode, start_day, end_day). Any D-14+ camp plan's continuation must equal
# this, and it must equal what a D-13-generated plan carries.
_EXPECTED_DOWNSTREAM = [
    ("d13_to_d8", "pre_fight_compressed_payload", 13, 8),
    ("d7", "late_fight_week_payload", 7, 7),
    ("d6_to_d5", "late_fight_transition_payload", 6, 5),
    ("d4_to_d2", "late_fight_session_payload", 4, 2),
    ("d1", "pre_fight_day_payload", 1, 1),
    ("d0", "fight_day_protocol_payload", 0, 0),
]

_EQUIP = (
    "bands, partner, kettlebells, dumbbells, cable, barbell, pullup_bar, "
    "heavy_bag, neck_harness, plate, towel, weight_belt, box, trap_bar, "
    "landmine, foam_roller, assault_bike, weight_vest, rower, pool, hurdles"
)


@pytest.fixture(scope="module", autouse=True)
def _warm_banks():
    prime_plan_banks(logger=logging.getLogger("test"))


def _fixture_fields(**over) -> list[dict]:
    return [
        {"label": "Full name", "value": "Fixture Athlete"},
        {"label": "Age", "value": "30"},
        {"label": "Weight (kg)", "value": over.get("weight", "88")},
        {"label": "Target Weight (kg)", "value": over.get("target_weight", "85")},
        {"label": "Height (cm)", "value": "185"},
        {"label": "Fighting Style (Technical)", "value": over.get("technical", "boxing")},
        {"label": "Fighting Style (Tactical)", "value": over.get("tactical", "counter_striker")},
        {"label": "Stance", "value": "Orthodox"},
        {"label": "Professional Status", "value": "professional"},
        {"label": "Current Record", "value": "9-2"},
        {"label": "Athlete Time Zone", "value": "Europe/London"},
        {"label": "Rounds x Minutes", "value": "12x3"},
        {"label": "Weekly Training Frequency", "value": over.get("frequency", "4")},
        {"label": "Fatigue Level", "value": over.get("fatigue", "low")},
        {"label": "Equipment Access", "value": _EQUIP},
        {
            "label": "Training Availability",
            "value": over.get(
                "availability",
                "Monday, Tuesday, Wednesday, Thursday, Friday, Sunday",
            ),
        },
        {"label": "Hard Sparring Days", "value": over.get("hard_sparring", "Thursday")},
        {"label": "Support Work Days", "value": over.get("support", "Monday")},
        {"label": "What are your key performance goals?", "value": over.get("key_goals", "power, speed")},
        {"label": "Primary goal", "value": over.get("primary_goal", "power")},
        {"label": "Where do you feel weakest right now?", "value": over.get("weak", "coordination, speed")},
        {"label": "Primary weak area", "value": over.get("primary_weak", "coordination")},
        {"label": "When is your next fight?", "value": FIGHT_FRIDAY.strftime("%Y-%m-%d")},
        {"label": "Any injuries or areas you need to work around?", "value": over.get("injuries", "")},
    ]


def _run(days: int, monkeypatch, **over) -> tuple[dict, dict, str]:
    """Drive the full deterministic Stage-1 pipeline; return (payload, brief, handoff)."""
    fixed_now = _dt.datetime.combine(
        FIGHT_FRIDAY - _dt.timedelta(days=days), _dt.time(12, 0)
    )
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: fixed_now)
    plan_input = PlanInput.from_payload({"data": {"fields": _fixture_fields(**over)}})
    assert plan_input.days_until_fight == days, (
        f"expected D-{days}, pinned clock gave D-{plan_input.days_until_fight}"
    )
    ctx = build_runtime_context(plan_input=plan_input, random_seed=1, logger=logging.getLogger("t"))
    blocks = generate_plan_blocks(
        context=ctx, logger=logging.getLogger("t"), record_timing=lambda *a, **k: None
    )
    rendered = RenderedPlanBundle(fight_plan_text="D-0\n- Fight day protocol", coach_notes="", reason_log={}, html="")
    return build_stage2_outputs(context=ctx, blocks=blocks, rendered=rendered)


# --------------------------------------------------------------------------- #
# Handoff / role-map extraction helpers (semantic, not name snapshots)
# --------------------------------------------------------------------------- #

_MAP_LINE = re.compile(r"^- (?P<stage>\S+):\s+(?P<mode>\S+)\s+\(D-(?P<start>\d+) to D-(?P<end>\d+)\)$")


def _continuation_segments(handoff_text: str) -> list[tuple[str, str, int, int]]:
    out = []
    for line in handoff_text.splitlines():
        m = _MAP_LINE.match(line.strip())
        if m:
            out.append((m["stage"], m["mode"], int(m["start"]), int(m["end"])))
    return out


def _mode_for_day(segments: list[tuple[str, str, int, int]], d_day: int) -> str | None:
    for _stage, mode, start, end in segments:
        if end <= d_day <= start:
            return mode
    return None


def _placed_roles(brief: dict):
    """Yield (d_day, role) for every scheduled session role in the plan."""
    for week in brief.get("weekly_role_map", {}).get("weeks", []) or []:
        cal = {}
        for day in week.get("calendar_days", []) or []:
            wd = str(day.get("weekday") or "").strip().lower()
            if isinstance(day.get("d_day"), int) and wd:
                cal[wd] = day["d_day"]
        for role in week.get("session_roles", []) or []:
            if not isinstance(role, dict):
                continue
            wd = str(role.get("scheduled_day_hint") or "").strip().lower()
            d_day = cal.get(wd)
            if d_day is None:
                for key in ("scheduled_countdown_label", "countdown_label"):
                    label = str(role.get(key) or "").strip().upper()
                    if label.startswith("D-") and label[2:].isdigit():
                        d_day = int(label[2:])
                        break
            yield d_day, role


def _app_owned_roles_at(brief: dict, d_days: set[int]):
    for d_day, role in _placed_roles(brief):
        if d_day in d_days and _is_app_owned_visible_role(role.get("role_key")):
            yield d_day, role


def _hard_sparring_entries(brief: dict):
    for week in brief.get("weekly_role_map", {}).get("weeks", []) or []:
        for entry in week.get("hard_sparring_plan", []) or []:
            if isinstance(entry, dict):
                yield entry


def _uses_normal_camp_planner(brief: dict) -> bool:
    return (
        brief.get("generator_mode") == "deterministic_planner_plus_ai_finalizer"
        and "payload_variant" not in brief
        and "days_out_payload" not in brief
        and "late_fight_plan_spec" not in brief
    )


# --------------------------------------------------------------------------- #
# Pure-function unit tests: the restored downstream continuation
# --------------------------------------------------------------------------- #

class TestDownstreamContinuationHelper:
    @pytest.mark.parametrize("days", [14, 15, 17, 20, 21, 24, 28, 60])
    def test_camp_plan_carries_full_downstream_sequence(self, days):
        seq = _camp_downstream_countdown_continuation(days)
        assert [
            (s["stage_key"], s["payload_mode"], s["start_day"], s["end_day"]) for s in seq
        ] == _EXPECTED_DOWNSTREAM

    @pytest.mark.parametrize("days", [13, 8, 4, 1, 0, -1, None, "x"])
    def test_non_camp_or_undated_plans_get_no_camp_continuation(self, days):
        # D-13 inward already carries the sequence via late_fight_plan_spec; undated
        # / invalid inputs must never fabricate a countdown.
        assert _camp_downstream_countdown_continuation(days) == []

    def test_camp_downstream_equals_a_d13_generated_sequence(self):
        # Requirement 2: a D-14+ plan's tail is byte-identical to the sequence a
        # plan generated directly at D-13 carries.
        assert _camp_downstream_countdown_continuation(24) == _countdown_mode_sequence(13)

    def test_downstream_starts_at_d13_and_never_reintroduces_the_bridge(self):
        seq = _camp_downstream_countdown_continuation(24)
        assert max(s["start_day"] for s in seq) == 13, "tail must begin at D-13, not D-14+"
        assert all(s["payload_mode"] != "bridge_compression_payload" for s in seq)
        assert all(s["stage_key"] != "d21_to_d14" for s in seq)


# --------------------------------------------------------------------------- #
# Routing invariants: D-14+ ownership unchanged (no bridge, still camp_payload)
# --------------------------------------------------------------------------- #

class TestRoutingUnchanged:
    @pytest.mark.parametrize("days", [14, 15, 16, 17, 18, 19, 20, 21, 24, 30])
    def test_d14_plus_routing_stays_camp_payload(self, days):
        # Requirement 9 + hard constraint: the fix never changes D-14+ routing.
        assert _days_out_payload_mode(days) == "camp_payload"
        assert _uses_late_fight_stage2_payload(days) is False

    @pytest.mark.parametrize("days", list(range(0, 32)))
    def test_no_days_out_mode_is_ever_the_removed_bridge(self, days):
        # Requirement 8: bridge_compression_payload is produced nowhere.
        assert _days_out_payload_mode(days) != "bridge_compression_payload"


# --------------------------------------------------------------------------- #
# End-to-end: a D-24-generated plan and its fight-week tail
# --------------------------------------------------------------------------- #

class TestD24GeneratedFightWeek:
    def test_d24_keeps_normal_camp_architecture_through_d14(self, monkeypatch):
        # Requirement 1 + 10: top-level architecture stays on the normal camp
        # planner, and the plan still schedules real sessions at D-14 and further
        # out (the continuation only governs the D-13 -> D-0 tail).
        _payload, brief, handoff = _run(24, monkeypatch)
        assert _uses_normal_camp_planner(brief)

        out_of_window = {d for d, _role in _placed_roles(brief) if isinstance(d, int) and d >= 14}
        assert out_of_window, "D-24 plan scheduled nothing at D-14 or further out"

        # The continuation map governs only D-13 -> D-0; it never claims a D-14+ day.
        segments = _continuation_segments(handoff)
        assert segments, "D-24 handoff carried no continuation map"
        assert max(start for _s, _m, start, _e in segments) == 13

    def test_d24_tail_receives_same_downstream_sequence_as_a_d13_plan(self, monkeypatch):
        # Requirement 2: the rendered handoff map for a D-24 plan matches a
        # D-13-generated plan's map exactly.
        _p24, _b24, h24 = _run(24, monkeypatch)
        _p13, _b13, h13 = _run(13, monkeypatch)
        assert _continuation_segments(h24) == _continuation_segments(h13)
        assert [
            (s, m, a, b) for (s, m, a, b) in _continuation_segments(h24)
        ] == _EXPECTED_DOWNSTREAM

    def test_d1_is_routed_to_the_equipment_banning_primer_contract(self, monkeypatch):
        # Requirements 3 & 4: D-1 is governed by pre_fight_day_payload, whose
        # contract (the single source of truth) bans ALL equipment. We prove the
        # routing + the contract content, and that the deterministic role map places
        # no app-owned S&C on D-1 (the declared combat lock is athlete-owned context).
        _payload, brief, handoff = _run(24, monkeypatch)
        segments = _continuation_segments(handoff)
        assert _mode_for_day(segments, 1) == "pre_fight_day_payload"

        primer_contract = _handoff_mode_instructions("pre_fight_day_payload")
        banned = primer_contract.lower()
        assert "no equipment of any kind on d-1" in banned
        for tool in ("no bands", "no med ball", "no heavy bag", "no weights", "no core", "no neck", "no grip"):
            assert tool in banned, f"pre_fight_day contract stopped banning {tool!r}"

        # No app-owned strength/conditioning role is scheduled on D-1.
        d1_sc = [
            role.get("role_key")
            for _d, role in _app_owned_roles_at(brief, {1})
            if str(role.get("category") or "").lower() in {"strength", "conditioning"}
        ]
        assert not d1_sc, f"D-1 carried app-owned S&C role(s): {d1_sc}"

    def test_d4_to_d2_carries_no_normal_strength_or_hard_conditioning(self, monkeypatch):
        # Requirement 5: the D-4 -> D-2 window is routed to late_fight_session_payload
        # (contract bans strength + conditioning), and the deterministic role map
        # places no app-owned strength role and no glycolytic (hard) conditioning
        # there. Light sharpness / freshness / recovery touches remain allowed.
        _payload, brief, handoff = _run(24, monkeypatch)
        segments = _continuation_segments(handoff)
        for d in (4, 3, 2):
            assert _mode_for_day(segments, d) == "late_fight_session_payload"

        session_contract = _handoff_mode_instructions("late_fight_session_payload").lower()
        assert "no strength" in session_contract
        assert "no conditioning" in session_contract
        assert "no glycolytic" in session_contract

        window = {2, 3, 4}
        for d_day, role in _app_owned_roles_at(brief, window):
            category = str(role.get("category") or "").lower()
            assert category != "strength", (
                f"D-{d_day} carried an app-owned strength role {role.get('role_key')!r}"
            )
            if category == "conditioning":
                assert str(role.get("preferred_system") or "").lower() != "glycolytic", (
                    f"D-{d_day} carried a glycolytic hard-conditioning role {role.get('role_key')!r}"
                )

    def test_d0_is_fight_day_protocol_only(self, monkeypatch):
        # Requirement 6: D-0 routes to fight_day_protocol_payload and the
        # deterministic role map exposes only the fight-day protocol there.
        _payload, brief, handoff = _run(24, monkeypatch)
        segments = _continuation_segments(handoff)
        assert _mode_for_day(segments, 0) == "fight_day_protocol_payload"

        d0_roles = {
            str(role.get("role_key") or "")
            for d_day, role in _placed_roles(brief)
            if d_day == 0
        }
        assert d0_roles, "D-0 had no scheduled entry at all"
        assert d0_roles <= {"fight_day_protocol"}, f"D-0 carried non-protocol roles: {d0_roles}"

        protocol_contract = _handoff_mode_instructions("fight_day_protocol_payload")
        assert "FIGHT DAY PROTOCOL" in protocol_contract
        assert "No training plan" in protocol_contract

    def test_no_bridge_payload_anywhere_in_the_handoff(self, monkeypatch):
        # Requirement 8: nothing in the produced handoff mentions the removed bridge.
        _payload, _brief, handoff = _run(24, monkeypatch)
        assert "bridge_compression_payload" not in handoff
        assert "d21_to_d14" not in handoff


# --------------------------------------------------------------------------- #
# Hard-sparring conversion (must not be weakened by the fix)
# --------------------------------------------------------------------------- #

class TestHardSparringConversionPreserved:
    @pytest.mark.parametrize("days", [24, 20, 17])
    def test_declared_hard_sparring_inside_d17_stays_technical_only(self, days, monkeypatch):
        # Requirement 7: any declared hard-sparring session whose SCHEDULED D-day is
        # <= 17 converts to technical-only, keyed on its own countdown position, and
        # no app-owned S&C is stacked onto that day. The fix touches only the Stage 2
        # handoff, so this existing safety invariant must be untouched.
        _payload, brief, _handoff = _run(days, monkeypatch)
        inside = [
            entry
            for entry in _hard_sparring_entries(brief)
            if isinstance(entry.get("d_day"), int) and 0 <= entry["d_day"] <= 17
        ]
        assert inside, f"D-{days} produced no in-window declared hard-sparring entry to check"
        technical_days = set()
        for entry in inside:
            assert entry.get("effective_load") == "technical", (
                f"D-{days}: hard sparring at D-{entry['d_day']} was not converted to technical"
            )
            assert "d17_hard_sparring_ban" in (entry.get("reason_codes") or [])
            technical_days.add(entry["d_day"])

        # No extra app-owned strength/conditioning stacked on a technical-only day.
        for d_day, role in _app_owned_roles_at(brief, technical_days):
            assert str(role.get("category") or "").lower() not in {"strength", "conditioning"}, (
                f"D-{d_day}: extra S&C ({role.get('role_key')!r}) stacked on a technical-only day"
            )

    def test_declared_hard_sparring_beyond_d17_stays_a_real_hard_lock(self, monkeypatch):
        # The other side of the invariant: at D-18 and further out a declared hard
        # spar is a real athlete/coach combat lock the app never deloads.
        _payload, brief, _handoff = _run(24, monkeypatch)
        outside = [
            entry
            for entry in _hard_sparring_entries(brief)
            if isinstance(entry.get("d_day"), int) and entry["d_day"] >= 18
        ]
        assert outside, "D-24 plan produced no D-18+ declared hard-sparring entry to check"
        for entry in outside:
            assert entry.get("effective_load") == "hard"
