import json
from pathlib import Path

from api.contracts.injury_policy import resolve_injury_policy
from fightcamp.rehab_clinical import load_clinical_policies
from fightcamp.rehab_protocols import get_rehab_bank
from tools.report_rehab_reachability import build_report


def test_report_is_current_and_baseline_ids_agree_with_actual_policy_decisions():
    report = build_report()
    assert report == json.loads(Path("docs/rehab-bank-reachability.json").read_text())
    assert report["summary"]["active_profiles"] == 64
    assert report["summary"]["live_unique_identities"] == 130
    assert report["summary"]["approved_never_surfaced_ids"] == []
    policies, bank = load_clinical_policies(), get_rehab_bank()
    equipment = sorted({e for group in bank for d in group["drills"] for e in (d.get("equipment") or [])})
    for profile in report["profiles"]:
        for stage in ("calm", "restore"):
            if stage not in profile["live_stages"]:
                continue
            injury = dict(id="probe", episode_id="episode", athlete_id="athlete", side="left",
                body_area=f"Left {profile['region']}", canonical_location=profile["region"],
                body_region=profile["region"], injury_type=profile["injury_type"], description=profile["injury_type"],
                severity="mild", status="monitoring", latest_reported_status="improving", rehab_stage=stage)
            # No transition is fabricated: higher stages need evidence and stay
            # closed. Baseline policy/priority/bundle selection is the real one.
            decision = resolve_injury_policy(injury, policies=policies, bank=bank, equipment=equipment)
            prescription = decision.get("prescription")
            actual = [p["drill_id"] for p in prescription.get("drills", [prescription])] if prescription else []
            assert actual == profile["stages"][stage]["surfaced_by_severity"]["low"], (profile["policy_id"], stage)
        for stage in ("dynamic", "return"):
            assert profile["stages"][stage]["availability"] == "closed"
            assert not profile["stages"][stage]["approved_exact_ids"]
    groin = next(p for p in report["profiles"] if p["policy_id"] == "groin_strain")
    assert groin["stages"]["load"]["availability"] == "closed"
