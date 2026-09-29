"""Values the backend and the web app must agree on live once, in shared/*.json.

Each contract below used to be a literal in a Python module and a second literal
in the web app, kept together by a "keep in sync" comment. These tests pin the
backend side to the file, check the web side imports the same file, and fail if
either side grows a literal copy again.
"""

import json
import math
from pathlib import Path

import pytest

import shared.contracts as contracts
from api import performance_focus
from api.contracts.training_day import DAY_ROLLOVER_HOUR
from api.errors import GENERATION_ALREADY_IN_FLIGHT_CODE, GENERATION_ALREADY_IN_FLIGHT_MESSAGE
from api.models import PROFILE_REFRESH_FAILED_WARNING, PROFILE_REFRESH_FAILED_WARNING_CODE
from api.services import notification_timing, session_timing_notifications
from api.stage2_automation import STAGE2_STAGE1_FALLBACK
from fightcamp.session_sequencing import SUPPORT_BLOCK_TYPES, SUPPORT_SESSION_TYPES
from fightcamp.training_context import EQUIP_ALIASES, PADS

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared"


def _contract(name: str) -> dict:
    return json.loads((SHARED / name).read_text(encoding="utf-8"))


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_focus_caps_come_from_the_shared_policy():
    policy = _contract("performance-focus-policy.json")
    cap = performance_focus._OPEN_PLAN_FOCUS_CAP

    assert (cap.max_selections, cap.window_label, cap.reason) == (
        policy["open_plan"]["max_selections"],
        policy["open_plan"]["window_label"],
        policy["open_plan"]["reason"],
    )
    assert [
        (
            None if math.isinf(window.max_days_until_fight) else window.max_days_until_fight,
            window.max_selections,
            window.window_label,
            window.reason,
        )
        for window in performance_focus._PERFORMANCE_FOCUS_CAP_WINDOWS
    ] == [
        (entry["max_days_until_fight"], entry["max_selections"], entry["window_label"], entry["reason"])
        for entry in policy["windows"]
    ]
    assert performance_focus._OVER_CAP_MESSAGE == policy["over_cap_message"]


def test_training_calendar_comes_from_the_shared_contract():
    calendar = _contract("training-calendar.json")

    assert DAY_ROLLOVER_HOUR == calendar["day_rollover_hour"]
    # The notification modules used to carry their own copies of the hour.
    assert notification_timing.TRAINING_DAY_ROLLOVER_HOUR == DAY_ROLLOVER_HOUR
    assert session_timing_notifications.TRAINING_DAY_ROLLOVER_HOUR == DAY_ROLLOVER_HOUR
    assert SUPPORT_SESSION_TYPES == frozenset(calendar["support_session_types"])
    assert SUPPORT_BLOCK_TYPES == frozenset(calendar["support_block_types"])


def test_api_messages_come_from_the_shared_contract():
    messages = _contract("api-messages.json")

    assert (GENERATION_ALREADY_IN_FLIGHT_CODE, GENERATION_ALREADY_IN_FLIGHT_MESSAGE) == (
        messages["generation_already_in_flight"]["code"],
        messages["generation_already_in_flight"]["message"],
    )
    assert (PROFILE_REFRESH_FAILED_WARNING_CODE, PROFILE_REFRESH_FAILED_WARNING) == (
        messages["profile_refresh_failed"]["code"],
        messages["profile_refresh_failed"]["message"],
    )


def test_stage1_fallback_status_comes_from_the_stage2_policy():
    assert STAGE2_STAGE1_FALLBACK == _contract("stage2-policy.json")["stage1_fallback_status"]


def test_every_shared_pad_spelling_normalizes_to_pads():
    pads = _contract("equipment-aliases.json")["pads"]

    assert PADS == pads["canonical"]
    assert {alias for alias, target in EQUIP_ALIASES.items() if target == PADS} == {
        *pads["aliases"],
        pads["canonical"],
    }


@pytest.mark.parametrize(
    ("web_file", "contract"),
    [
        ("web/lib/performance-focus-cap.ts", "performance-focus-policy.json"),
        ("web/lib/camp-map.ts", "training-calendar.json"),
        ("web/lib/generation-controller.ts", "api-messages.json"),
        ("web/lib/profile-refresh-warning.ts", "api-messages.json"),
        ("web/lib/stage2-policy.ts", "stage2-policy.json"),
        ("web/lib/intake-options.ts", "equipment-aliases.json"),
    ],
)
def test_web_reads_the_same_contract(web_file, contract):
    assert f'from "../../shared/{contract}"' in _source(web_file)


@pytest.mark.parametrize(
    ("relative", "literal"),
    [
        ("web/lib/performance-focus-cap.ts", '"Fight week"'),
        ("web/lib/performance-focus-cap.ts", "This camp allows"),
        ("web/lib/camp-map.ts", 'SUPPORT_SESSION_TYPES = new Set(["recovery"'),
        ("web/lib/camp-map.ts", "TRAINING_DAY_ROLLOVER_HOUR = 3"),
        ("web/lib/generation-controller.ts", '"generation_already_in_flight"'),
        ("web/lib/profile-refresh-warning.ts", "plan generated from submitted intake only"),
        ("web/components/plan-viewer.tsx", '"stage2_failed_stage1_fallback"'),
        ("web/lib/intake-options.ts", 'thai_pads: "pads"'),
        ("api/performance_focus.py", '"Fight week"'),
        ("api/errors.py", 'GENERATION_ALREADY_IN_FLIGHT_CODE = "generation_already_in_flight"'),
        ("api/models.py", "plan generated from submitted intake only"),
        ("api/stage2_automation.py", '"stage2_failed_stage1_fallback"'),
        ("api/contracts/training_day.py", "DAY_ROLLOVER_HOUR = 3"),
        ("api/services/notification_timing.py", "TRAINING_DAY_ROLLOVER_HOUR = 3"),
        ("api/services/session_timing_notifications.py", "TRAINING_DAY_ROLLOVER_HOUR = 3"),
        ("fightcamp/session_sequencing.py", 'SUPPORT_SESSION_TYPES = frozenset({"recovery"'),
        ("fightcamp/training_context.py", '"thai_pads": "pads"'),
    ],
)
def test_no_second_literal_copy(relative, literal):
    assert literal not in _source(relative)


def test_every_shared_contract_is_checked_by_the_image_build():
    dockerfile = _source("Dockerfile")

    for contract in sorted(path.name for path in SHARED.glob("*.json")):
        assert f"/app/shared/{contract}" in dockerfile, contract


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        (None, "missing"),
        ("{not json", "not valid JSON"),
        ("[]", "must be a JSON object"),
    ],
)
def test_a_broken_contract_fails_loudly(tmp_path, monkeypatch, contents, message):
    if contents is not None:
        (tmp_path / "example.json").write_text(contents, encoding="utf-8")
    monkeypatch.setattr(contracts, "SHARED_DIR", tmp_path)

    with pytest.raises(RuntimeError, match=message):
        contracts.load_shared_contract("example.json")


@pytest.mark.parametrize(
    ("value", "check"),
    [
        ({"k": ""}, lambda c: contracts.require_string(c, "k", source="t")),
        ({"k": True}, lambda c: contracts.require_positive_int(c, "k", source="t")),
        ({"k": 0}, lambda c: contracts.require_positive_int(c, "k", source="t")),
        ({"k": ["a", "a"]}, lambda c: contracts.require_string_list(c, "k", source="t")),
        ({"k": []}, lambda c: contracts.require_string_list(c, "k", source="t")),
        ({"k": "x"}, lambda c: contracts.require_object(c, "k", source="t")),
    ],
)
def test_contract_values_are_validated(value, check):
    with pytest.raises(RuntimeError):
        check(value)
