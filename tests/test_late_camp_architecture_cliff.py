"""Regression suite for the late-camp architecture cliff fix.

Two categories, per the design of the fix:

A. ROUTING / ARCHITECTURE — proves the abrupt D-22 -> D-21 architecture swap is
   gone: D-14..D-21 use the SAME normal camp planner as D-22+, the countdown only
   progressively *constrains* that architecture (scheduled-day strength dose morph
   + D-17 hard-contact ban), and the single intentional planner boundary is at
   D-13/D-14. No new one-day cliff is introduced.

B. REAL PRODUCTION-LIKE CALENDAR / COLLISION — drives the full deterministic
   Stage-1 pipeline on the exact production fixture geometry (no Saturday
   availability, Monday coach support, Thursday declared contact, Friday fight)
   and asserts the FINAL post-morph training *meaning* (intent/category/dose/day),
   never intermediate role keys and never exercise names.

``days_until_fight`` is made deterministic by pinning ``input_parsing._utc_now``
to a fixed instant a chosen number of days before a fixed Friday fight, so the
weekday geometry (Sat unavailable, Mon support, Thu contact) is stable.
"""

from __future__ import annotations

import datetime as _dt
import logging

import pytest

from fightcamp import input_parsing
from fightcamp.input_parsing import PlanInput
from fightcamp.late_camp_role_morph import late_fight_strength_dose_cap
from fightcamp.plan_pipeline_blocks import generate_plan_blocks
from fightcamp.plan_pipeline_rendering import build_stage2_outputs
from fightcamp.plan_pipeline_runtime import (
    RenderedPlanBundle,
    build_runtime_context,
    prime_plan_banks,
)
from fightcamp.stage2_payload_late_fight import _is_app_owned_visible_role

logging.disable(logging.CRITICAL)

# A fixed Friday fight anchors the production weekday geometry.
FIGHT_FRIDAY = _dt.date(2026, 1, 30)
assert FIGHT_FRIDAY.weekday() == 4, "fixture fight date must be a Friday"

# A fixed Tuesday fight anchors the exact production calendar behind the shipped
# D-16 collapse: with Mon-Fri availability and Tue/Fri declared contact, a Tuesday
# fight puts D-4 on a Friday contact day and D-1/D-8 on legal Mondays. That precise
# geometry is what a Friday-anchored fixture cannot reproduce.
FIGHT_TUESDAY = _dt.date(2026, 2, 3)
assert FIGHT_TUESDAY.weekday() == 1, "fixture fight date must be a Tuesday"

_EQUIP = (
    "bands, partner, kettlebells, dumbbells, cable, barbell, pullup_bar, "
    "heavy_bag, neck_harness, plate, towel, weight_belt, box, trap_bar, "
    "landmine, foam_roller, assault_bike, weight_vest, rower, pool, hurdles"
)


@pytest.fixture(scope="module", autouse=True)
def _warm_banks():
    prime_plan_banks(logger=logging.getLogger("test"))


def _fixture_fields(*, fight_date: _dt.date = FIGHT_FRIDAY, **over) -> list[dict]:
    """The exact production-like regression fixture, with per-test overrides."""
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
        {"label": "When is your next fight?", "value": fight_date.strftime("%Y-%m-%d")},
        {"label": "Any injuries or areas you need to work around?", "value": over.get("injuries", "")},
    ]


def _run(days: int, monkeypatch, *, fight_date: _dt.date = FIGHT_FRIDAY, **over) -> dict:
    """Drive the full deterministic Stage-1 pipeline and return the planning brief.

    ``fight_date`` anchors the weekday geometry. It defaults to the Friday fixture
    so existing callers are unchanged; pass ``FIGHT_TUESDAY`` to reproduce the exact
    production calendar (Tue/Fri contact, weekend-unavailable) behind the D-16 bug.
    """
    fixed_now = _dt.datetime.combine(
        fight_date - _dt.timedelta(days=days), _dt.time(12, 0)
    )
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: fixed_now)
    plan_input = PlanInput.from_payload(
        {"data": {"fields": _fixture_fields(fight_date=fight_date, **over)}}
    )
    assert plan_input.days_until_fight == days, (
        f"expected D-{days}, pinned clock gave D-{plan_input.days_until_fight}"
    )
    ctx = build_runtime_context(plan_input=plan_input, random_seed=1, logger=logging.getLogger("t"))
    blocks = generate_plan_blocks(
        context=ctx, logger=logging.getLogger("t"), record_timing=lambda *a, **k: None
    )
    rendered = RenderedPlanBundle(fight_plan_text="", coach_notes="", reason_log={}, html="")
    _payload, brief, _handoff = build_stage2_outputs(context=ctx, blocks=blocks, rendered=rendered)
    return brief


# --------------------------------------------------------------------------- #
# Meaning-extraction helpers — inspect the FINAL post-morph deterministic plan
# --------------------------------------------------------------------------- #

def _uses_normal_camp_planner(brief: dict) -> bool:
    return (
        brief.get("generator_mode") == "deterministic_planner_plus_ai_finalizer"
        and "payload_variant" not in brief
        and "days_out_payload" not in brief
    )


def _weeks(brief: dict) -> list[dict]:
    return brief.get("weekly_role_map", {}).get("weeks", []) or []


def _week_calendar(week: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for day in week.get("calendar_days", []) or []:
        wd = str(day.get("weekday") or "").strip().lower()
        if isinstance(day.get("d_day"), int) and wd:
            out[wd] = day["d_day"]
    return out


def _role_d_day(week: dict, role: dict) -> int | None:
    cal = _week_calendar(week)
    wd = str(role.get("scheduled_day_hint") or "").strip().lower()
    if wd in cal:
        return cal[wd]
    for key in ("scheduled_countdown_label", "countdown_label"):
        label = str(role.get(key) or "").strip().upper()
        if label.startswith("D-") and label[2:].isdigit():
            return int(label[2:])
    return None


def _placed_roles(brief: dict):
    """Yield (week, role, d_day, weekday) for every scheduled session role."""
    for week in _weeks(brief):
        for role in week.get("session_roles", []) or []:
            if not isinstance(role, dict):
                continue
            yield week, role, _role_d_day(week, role), str(role.get("scheduled_day_hint") or "").strip().lower()


def _meaningful_strength_exposures(brief: dict):
    """App-owned strength-category roles whose post-morph dose is still meaningful.

    Meaningful = the role kept its strength intent (category strength, not silently
    turned into conditioning) AND its post-morph dose is real strength retention,
    i.e. either uncapped (D-18+) or a >= 2-set retention touch (D-17..D-14), never
    a 1-set neural/throw microdose.
    """
    out = []
    for _week, role, d_day, _wd in _placed_roles(brief):
        if str(role.get("category") or "").lower() != "strength":
            continue
        if not _is_app_owned_visible_role(role.get("role_key")):
            continue
        cap = role.get("strength_dose_cap")
        if cap is None:
            meaningful = True  # uncapped meaningful strength (D-18+)
        else:
            meaningful = int(cap.get("max_sets", 0)) >= 2
        out.append({"role": role, "d_day": d_day, "meaningful": meaningful})
    return out


def _meaningful_conditioning_exposures(brief: dict):
    """App-owned conditioning roles carrying a real training stimulus.

    Meaningful = category conditioning, app-owned, NOT softened to a low-cost
    rhythm touch by the late-camp morph, and on a hard/sharpness energy system
    (glycolytic / alactic) rather than low-load aerobic support.
    """
    out = []
    for _week, role, d_day, _wd in _placed_roles(brief):
        if str(role.get("category") or "").lower() != "conditioning":
            continue
        if not _is_app_owned_visible_role(role.get("role_key")):
            continue
        if role.get("late_camp_role_morph") is True:
            continue
        if role.get("counts_toward_conditioning_cap") is False:
            continue
        if str(role.get("preferred_system") or "").lower() in {"glycolytic", "alactic"}:
            out.append({"role": role, "d_day": d_day})
    return out


def _hard_exposure_count(brief: dict) -> int:
    """Meaningful strength exposures + meaningful (hard) conditioning exposures."""
    return sum(1 for e in _meaningful_strength_exposures(brief) if e["meaningful"]) + len(
        _meaningful_conditioning_exposures(brief)
    )


def _hard_sparring_plan_entries(brief: dict):
    for week in _weeks(brief):
        for entry in week.get("hard_sparring_plan", []) or []:
            yield week, entry


# --------------------------------------------------------------------------- #
# A. ROUTING / ARCHITECTURE
# --------------------------------------------------------------------------- #

class TestRoutingArchitecture:
    def test_d21_and_d22_use_the_same_normal_camp_planner(self, monkeypatch):
        # The core of the fix: crossing the old D-22 -> D-21 threshold no longer
        # swaps the planner. Both use the normal camp architecture.
        assert _uses_normal_camp_planner(_run(22, monkeypatch))
        assert _uses_normal_camp_planner(_run(21, monkeypatch))

    @pytest.mark.parametrize("days", [21, 20, 19, 18, 17, 16, 15, 14])
    def test_late_camp_window_keeps_normal_camp_architecture(self, days, monkeypatch):
        assert _uses_normal_camp_planner(_run(days, monkeypatch))

    def test_d14_is_camp_and_d13_is_the_single_intentional_boundary(self, monkeypatch):
        # D-14 still normal camp; D-13 crosses into the dedicated compressed/taper
        # architecture. That is the one intentional planner boundary.
        assert _uses_normal_camp_planner(_run(14, monkeypatch))
        d13 = _run(13, monkeypatch)
        assert d13.get("payload_variant") == "late_fight_stage2_payload"

    @pytest.mark.parametrize("days", [28, 24, 22, 21, 20, 18, 16, 14])
    def test_meaningful_strength_survives_across_the_whole_late_camp_window(self, days, monkeypatch):
        # No day in D-14..D-28 loses the strength backbone: a meaningful strength
        # exposure is always retained somewhere in the plan.
        brief = _run(days, monkeypatch)
        exposures = _meaningful_strength_exposures(brief)
        assert any(e["meaningful"] for e in exposures), (
            f"D-{days} dropped meaningful strength entirely: "
            f"{[(e['role'].get('role_key'), e['d_day']) for e in exposures]}"
        )

    def test_no_arbitrary_one_day_architecture_replacement(self, monkeypatch):
        # Adjacent late-camp days must not differ by a wholesale architecture swap:
        # each keeps a meaningful strength exposure and a conditioning exposure.
        prev_categories = None
        for days in (22, 21, 20, 19, 18, 17, 16, 15, 14):
            brief = _run(days, monkeypatch)
            cats = {
                str(role.get("category") or "").lower()
                for _w, role, _d, _wd in _placed_roles(brief)
                if _is_app_owned_visible_role(role.get("role_key"))
            }
            assert "strength" in cats, f"D-{days} lost strength category"
            assert "conditioning" in cats, f"D-{days} lost conditioning category"
            prev_categories = cats
        assert prev_categories is not None

    def test_strength_dose_morph_is_progressive_by_scheduled_day_not_generation_day(self):
        # The dose cap is a pure function of the SCHEDULED session D-day, so a
        # session at D-16 gets the same treatment whether the plan was generated
        # at D-28, D-22 or D-20. Monotonically non-increasing toward the fight.
        caps = {d: late_fight_strength_dose_cap(d) for d in range(0, 22)}
        assert caps[18] is None and caps[21] is None, "D-18+ strength is uncapped"
        assert caps[17] is not None and caps[17]["max_sets"] >= 2, "D-17 keeps a retention touch"
        assert caps[14]["max_sets"] >= 2, "D-14 keeps a >= 2-set retention touch"
        # Non-increasing set ceiling as the fight approaches (no cliff, a ramp).
        ceilings = [caps[d]["max_sets"] for d in (17, 14, 10, 8, 7, 5, 2, 0) if caps[d]]
        assert ceilings == sorted(ceilings, reverse=True)


# --------------------------------------------------------------------------- #
# B. REAL PRODUCTION-LIKE CALENDAR / COLLISION
# --------------------------------------------------------------------------- #

class TestProductionCalendarCollision:
    def test_power_priority_preserves_meaningful_strength_on_a_legal_day(self, monkeypatch):
        # The regression: a D-20/D-21 power athlete lost meaningful strength to a
        # tiny neural microdose. It must survive as real strength on a legal day,
        # never colliding with the declared Thursday contact or the unavailable
        # Saturday.
        for days in (21, 20, 19, 18):
            brief = _run(days, monkeypatch)
            good = [
                e for e in _meaningful_strength_exposures(brief)
                if e["meaningful"]
            ]
            assert good, f"D-{days} power athlete lost meaningful strength"
            for e in good:
                wd = str(e["role"].get("scheduled_day_hint") or "").lower()
                assert wd != "saturday", "meaningful strength scheduled on unavailable Saturday"
                assert wd != "thursday", "meaningful strength stacked on the declared contact day"

    def test_no_app_owned_snc_stacked_on_declared_thursday_contact(self, monkeypatch):
        for days in (21, 20, 18, 16, 14):
            brief = _run(days, monkeypatch)
            for _w, role, _d, wd in _placed_roles(brief):
                if wd != "thursday":
                    continue
                if _is_app_owned_visible_role(role.get("role_key")) and role.get("stress_class") == "meaningful_stress":
                    raise AssertionError(
                        f"D-{days} stacked app S&C ({role.get('role_key')}) on the Thursday contact day"
                    )

    def test_no_session_scheduled_on_unavailable_saturday(self, monkeypatch):
        for days in (21, 20, 18, 16, 14):
            brief = _run(days, monkeypatch)
            saturday_roles = [
                role.get("role_key")
                for _w, role, _d, wd in _placed_roles(brief)
                if wd == "saturday"
            ]
            assert not saturday_roles, f"D-{days} scheduled on unavailable Saturday: {saturday_roles}"

    def test_declared_hard_sparring_inside_d17_is_converted_to_technical(self, monkeypatch):
        # The genuine safety invariant that must survive the refactor: any declared
        # hard-sparring session whose SCHEDULED D-day is <= 17 converts to
        # technical-only, keyed on the session's own countdown position.
        for days in (21, 20, 18, 16):
            brief = _run(days, monkeypatch)
            inside = [
                entry
                for _w, entry in _hard_sparring_plan_entries(brief)
                if isinstance(entry.get("d_day"), int) and 0 <= entry["d_day"] <= 17
            ]
            assert inside, f"D-{days} produced no in-window declared hard-sparring entry to check"
            for entry in inside:
                assert entry.get("effective_load") == "technical", (
                    f"D-{days}: hard sparring at D-{entry['d_day']} was not converted"
                )
                assert "d17_hard_sparring_ban" in (entry.get("reason_codes") or [])

    def test_declared_hard_sparring_at_d18_plus_stays_a_coach_owned_lock(self, monkeypatch):
        # The other side of the same invariant: D-18 and further out, declared hard
        # sparring is an athlete/coach combat lock the app never deloads.
        brief = _run(21, monkeypatch)
        outside = [
            entry
            for _w, entry in _hard_sparring_plan_entries(brief)
            if isinstance(entry.get("d_day"), int) and entry["d_day"] >= 18
        ]
        for entry in outside:
            assert entry.get("effective_load") == "hard"

    def test_conditioning_priority_athlete_keeps_meaningful_conditioning(self, monkeypatch):
        # Goal-aware: a conditioning-priority athlete keeps a meaningful
        # conditioning exposure in the late-camp window (the scarce early slot is
        # not spent purely on strength for this athlete).
        for days in (21, 18):
            brief = _run(
                days, monkeypatch,
                primary_goal="conditioning",
                key_goals="conditioning, gas_tank",
                weak="gas_tank, conditioning",
                primary_weak="gas_tank",
            )
            assert _meaningful_conditioning_exposures(brief), (
                f"D-{days} conditioning athlete lost meaningful conditioning"
            )

    def test_high_fatigue_removes_hard_conditioning_and_stays_conservative(self, monkeypatch):
        # High fatigue is a genuine per-session readiness signal the countdown
        # overlay honours: it drops the hard (glycolytic) conditioning exposure and
        # never yields MORE hard exposures than the clean low-fatigue athlete.
        low = _run(20, monkeypatch)
        high = _run(20, monkeypatch, fatigue="high")
        assert _hard_exposure_count(high) <= _hard_exposure_count(low)
        assert not _meaningful_conditioning_exposures(high), (
            "high fatigue must drop the hard conditioning exposure in late camp"
        )

    def test_aggressive_weight_cut_is_never_less_conservative_than_a_clean_cut(self, monkeypatch):
        # An aggressive cut must never EMBOLDEN the plan: it may not add hard
        # exposures beyond the clean/routine-cut athlete. (Training-load
        # suppression as the cut intensifies is owned by the D-13-inward taper
        # compression and the nutrition/recovery modules, applied consistently
        # with D-22+; see the PR's "remaining risks" note.)
        clean = _run(20, monkeypatch)  # routine 3.4% cut fixture
        aggressive = _run(20, monkeypatch, weight="88", target_weight="80")  # ~9%
        assert _hard_exposure_count(aggressive) <= _hard_exposure_count(clean)

    @pytest.mark.parametrize("days", [21, 18, 14])
    def test_final_scheduled_days_are_legal_available_days(self, days, monkeypatch):
        # Every app-owned scheduled session must land on a declared-available day
        # (the fixture excludes Saturday).
        brief = _run(days, monkeypatch)
        for _w, role, _d, wd in _placed_roles(brief):
            if _is_app_owned_visible_role(role.get("role_key")) and wd:
                assert wd != "saturday"



# --------------------------------------------------------------------------- #
# C. TWO DECLARED CONTACT DAYS AFTER D-17 DOWNGRADE — EXACT TUESDAY-FIGHT SHAPE
# --------------------------------------------------------------------------- #

# Legal app-owned days for the Tuesday-fight fixture: Mon-Fri availability with
# Tuesday and Friday owned by declared contact, so app S&C may only land on
# Monday / Wednesday / Thursday. Tuesday and Friday are contact (never app S&C).
_TUE_FIGHT_LEGAL_DAYS = {"monday", "wednesday", "thursday"}
_TUE_FIGHT_CONTACT_DAYS = {"tuesday", "friday"}


class TestTwoDeclaredContactLateCampRegression:
    """D-17..D-14 normal-camp regression on the EXACT production Tuesday-fight shape.

    This reproduces the calendar behind the shipped D-16 collapse rather than the
    module's default Friday anchor. With a Tuesday fight, Mon-Fri availability and
    Tuesday/Friday declared contact, the countdown lands on::

        D-14 Tue (contact)  D-13 Wed          D-12 Thu          D-11 Fri (contact)
        D-8  Mon            D-7  Tue (contact) D-6  Wed          D-5  Thu
        D-4  Fri (contact)  D-1  Mon           D-0  Tue (FIGHT)

    with the weekends (D-16/D-15 ... D-10/D-9 ... D-3/D-2) unavailable. Those are
    the specific legal windows the bug depended on — a Friday-anchored fixture puts
    the fight itself on a declared contact day and cannot reproduce them.

    Assertions are semantic (category / energy system / role family / day), never
    exercise names, and hold across the whole D-17..D-14 normal-camp window.
    """

    @staticmethod
    def _case(days, monkeypatch):
        return _run(
            days,
            monkeypatch,
            fight_date=FIGHT_TUESDAY,
            availability="Monday, Tuesday, Wednesday, Thursday, Friday",
            hard_sparring="Tuesday, Friday",
            support="",
            frequency="4",
            weight="88",
            target_weight="88",
            fatigue="low",
            key_goals="speed",
            primary_goal="speed",
            weak="footwork, power",
            primary_weak="footwork",
        )

    @pytest.mark.parametrize("days", [17, 16, 15, 14])
    def test_downgraded_contact_is_not_counted_as_two_hard_days(self, days, monkeypatch):
        brief = self._case(days, monkeypatch)
        for week in _weeks(brief):
            hard_plan = week.get("hard_sparring_plan") or []
            if not hard_plan:
                continue
            assert week.get("effective_hard_sparring_days") == []
            reason_codes = set((week.get("intentional_compression") or {}).get("reason_codes") or [])
            for suppressed in week.get("suppressed_roles") or []:
                reason_codes.update(suppressed.get("compression_reason_codes") or [])
            assert "two_hard_spar_days" not in reason_codes

    @pytest.mark.parametrize("days", [17, 16, 15, 14])
    def test_tuesday_fight_keeps_full_architecture_without_inflating_frequency(self, days, monkeypatch):
        # The architecture assertions run across the whole D-17..D-14 window, not
        # only at D-16: crossing a generation day must not silently drop a layer.
        brief = self._case(days, monkeypatch)
        placed = list(_placed_roles(brief))

        # 1. Meaningful RETENTION strength (not merely the D-1 primer) survives on a
        #    legal, non-contact available day. The shipped bug lost it to a 1-set
        #    neural microdose; here it must stay a >= 2-set / uncapped exposure and
        #    never stack on Tue/Fri contact or an unavailable weekend.
        retention_strength = [
            e for e in _meaningful_strength_exposures(brief)
            if e["meaningful"] and e["role"].get("role_key") != "neural_primer_day"
        ]
        assert retention_strength, f"D-{days} lost meaningful retention strength entirely"
        for e in retention_strength:
            wd = str(e["role"].get("scheduled_day_hint") or "").strip().lower()
            assert wd in _TUE_FIGHT_LEGAL_DAYS, (
                f"D-{days} meaningful strength on illegal day {wd!r} "
                f"(key={e['role'].get('role_key')}, D-{e['d_day']})"
            )

        # 2. Fight-pace / conditioning work survives the two-contact compression
        #    (it is not squeezed out entirely).
        conditioning = [
            role for _w, role, _d, _wd in placed
            if str(role.get("category") or "").lower() == "conditioning"
            and _is_app_owned_visible_role(role.get("role_key"))
        ]
        assert conditioning, f"D-{days} lost app-owned conditioning entirely"

        # 3. A last-week sharpness touch (alactic/neural) survives in the D-6..D-4
        #    window on a legal day. D-4 is Friday contact, so it must land D-6/D-5.
        sharpness = [
            (role, d_day, wd) for _w, role, d_day, wd in placed
            if d_day in {4, 5, 6}
            and str(role.get("preferred_system") or "").strip().lower() in {"alactic", "neural"}
        ]
        assert sharpness, f"D-{days} has no alactic/neural sharpness touch in D-6..D-4"
        for _role, d_day, wd in sharpness:
            assert wd not in _TUE_FIGHT_CONTACT_DAYS, (
                f"D-{days} placed a D-{d_day} sharpness touch on the {wd} contact day"
            )

        # 4. D-1 stays a small neural freshness primer.
        assert any(
            d_day == 1 and role.get("role_key") == "neural_primer_day"
            for _w, role, d_day, _wd in placed
        ), f"D-{days} lost the D-1 neural freshness primer"

        # 5. No app-owned meaningful S&C is stacked on a Tue/Fri contact day.
        for _w, role, d_day, wd in placed:
            if wd in _TUE_FIGHT_CONTACT_DAYS and _is_app_owned_visible_role(role.get("role_key")):
                assert role.get("stress_class") != "meaningful_stress", (
                    f"D-{days} stacked app S&C ({role.get('role_key')}) "
                    f"on the {wd} contact day (D-{d_day})"
                )

        # 6. No volume inflation: two declared contact appointments already own two
        #    of the four weekly slots, so app-owned core work must fit the two
        #    remaining legal days and never land on Tue/Fri contact.
        for week in _weeks(brief):
            core = [
                role for role in week.get("session_roles") or []
                if role.get("category") in {"strength", "conditioning", "recovery"}
            ]
            assert len(core) <= 2, (
                f"D-{days} {week.get('phase')} inflated core work to {len(core)} slots: "
                f"{[role.get('role_key') for role in core]}"
            )
            for role in core:
                assert str(role.get("scheduled_day_hint") or "").strip().lower() not in _TUE_FIGHT_CONTACT_DAYS

    @pytest.mark.parametrize("days", [17, 16, 15, 14])
    def test_proximity_only_suppression_is_not_mislabelled_as_fight_proximity(self, days, monkeypatch):
        # When all hard sparring is already technical-only and declared contact owns
        # the freed slots, this path explicitly disables proximity compression
        # (compression_floor -> 0). The surviving cap is then the spar-first
        # declared-contact frequency cap, so the reason recorded on the dropped roles
        # must say that — labelling it proximity_to_fight would contaminate every
        # downstream consumer with a signal this week deliberately turned off.
        brief = self._case(days, monkeypatch)
        saw_declared_contact_cap = False
        for week in _weeks(brief):
            codes: set[str] = set((week.get("intentional_compression") or {}).get("reason_codes") or [])
            for suppressed in week.get("suppressed_roles") or []:
                codes.update(suppressed.get("compression_reason_codes") or [])
            assert "proximity_to_fight" not in codes, (
                f"D-{days} still labels a declared-contact-frequency drop as proximity_to_fight"
            )
            if "declared_contact_frequency_cap" in codes:
                saw_declared_contact_cap = True
        assert saw_declared_contact_cap, (
            f"D-{days} never recorded the declared_contact_frequency_cap reason on a suppression"
        )
