"""Formula migration and confirmed-send boundary tests; no live sends."""
import copy
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(TOOLS))
    monkeypatch.delitem(sys.modules, "sync_notion_followups", raising=False)
    return load("confirm_notion_warm_send"), load("migrate_notion_warm_counter")


def test_migration_only_removes_legacy_counter_without_touching_other_branches(modules):
    _, migration = modules
    properties = {
        name: {"formula": {"expression": 'if(prop("Stage (AI Fills First)") == "Activated", "feedback", lets(n,if(prop("Signup Nudges Sent") == "1",1,0)' + legacy + ',"warm"))'}}
        for name, legacy in zip(migration.FIELDS, (*migration.LEGACY_TERMS, migration.LEGACY_TERMS[0]))
    }
    changes = migration.formula_changes(properties)
    assert set(changes) == set(migration.FIELDS)
    for name, patch in changes.items():
        expression = patch["formula"]["expression"]
        assert '"feedback"' in expression
        assert 'prop("Signup Nudges Sent")' in expression
        assert 'Onboarding Nudges Sent' not in expression
    merged = {**properties, **changes}
    assert migration.formula_changes(merged) == {}
    assert migration.formula_changes({"Warm Next DM": {"formula": {"expression": "untouched"}}, "Next DM to Copy": {"formula": {"expression": "untouched"}}, "Outreach Next Step": {"formula": {"expression": "untouched"}}}) == {}


@pytest.fixture
def sending(modules, monkeypatch, tmp_path):
    helper, _ = modules
    fixtures = load_fixture()
    page = fixtures.warm_row("Replied")
    page["id"] = "safe-test"
    now = fixtures.OBSERVED_NOW
    writes = []

    def request(method, path, body=None):
        if method == "GET":
            return copy.deepcopy(page)
        writes.append(body)
        page["properties"].update(copy.deepcopy(body["properties"]))
        return copy.deepcopy(page)

    monkeypatch.setattr(helper.sync, "request", request)
    return helper, page, now, str(tmp_path / "journal.db"), writes


def load_fixture():
    spec = importlib.util.spec_from_file_location("followup_fixtures", Path(__file__).with_name("test_sync_notion_followups.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_attempt_never_marks_a_send_and_duplicate_attempt_is_held(sending):
    helper, page, now, path, writes = sending
    digest = helper.guard(helper.sync.WARM_MESSAGES["Replied"][0])
    helper.prepare(path, page["id"], 1, digest, now)
    assert writes == []
    with pytest.raises(sqlite3.IntegrityError):
        helper.prepare(path, page["id"], 1, digest, now)
    with pytest.raises(ValueError):
        helper.confirm(path, page["id"], 1, "", now)
    assert writes == []


def test_confirmed_sends_increment_once_survive_stage_switch_and_stop_at_two(sending):
    from datetime import timedelta
    helper, page, now, path, writes = sending
    helper.prepare(path, page["id"], 1, helper.guard(helper.sync.WARM_MESSAGES["Replied"][0]), now)
    helper.confirm(path, page["id"], 1, "verified-message-1", now)
    helper.confirm(path, page["id"], 1, "verified-message-1", now)
    assert len(writes) == 1
    first = copy.deepcopy(page["properties"]["Signup Nudge 1 At"])
    page["properties"]["Stage (AI Fills First)"]["select"]["name"] = "Accepted"
    later = now + timedelta(days=4)
    helper.prepare(path, page["id"], 2, helper.guard(helper.sync.WARM_MESSAGES["Accepted"][1]), later)
    helper.confirm(path, page["id"], 2, "verified-message-2", later)
    helper.confirm(path, page["id"], 2, "verified-message-2", later)
    assert len(writes) == 2
    assert page["properties"]["Signup Nudge 1 At"] == first
    assert page["properties"]["Signup Nudges Sent"]["select"]["name"] == "2"
    with pytest.raises(ValueError):
        helper.prepare(path, page["id"], 2, helper.guard(helper.sync.WARM_MESSAGES["Accepted"][1]), later)


def test_ambiguous_patch_response_is_reconciled_without_incrementing_again(sending, monkeypatch):
    helper, page, now, path, writes = sending
    helper.prepare(path, page["id"], 1, helper.guard(helper.sync.WARM_MESSAGES["Replied"][0]), now)
    request = helper.sync.request

    def lost_response(method, route, body=None):
        result = request(method, route, body)
        if method == "PATCH":
            raise TimeoutError("response lost after write")
        return result

    monkeypatch.setattr(helper.sync, "request", lost_response)
    with pytest.raises(TimeoutError):
        helper.confirm(path, page["id"], 1, "verified-message", now)
    monkeypatch.setattr(helper.sync, "request", request)
    helper.confirm(path, page["id"], 1, "verified-message", now)
    assert len(writes) == 1


@pytest.mark.parametrize("change", ["stage", "history", "copy", "count"])
def test_live_revalidation_blocks_changed_or_undated_record(sending, change):
    helper, page, now, path, writes = sending
    digest = helper.guard(helper.sync.WARM_MESSAGES["Replied"][0])
    p = page["properties"]
    if change == "stage":
        p["Stage (AI Fills First)"]["select"]["name"] = "Activated"
    elif change == "history":
        p["Details Sent At"] = helper.sync.date_patch(None)
    elif change == "copy":
        digest = "stale"
    else:
        p["Signup Nudges Sent"]["select"]["name"] = "2"
    with pytest.raises(ValueError):
        helper.prepare(path, page["id"], 1, digest, now)
    assert writes == []
