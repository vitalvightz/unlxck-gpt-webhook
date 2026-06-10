"""Tests for admin role management: set_profile_role, audit writes, and the CLI."""
from __future__ import annotations

import pytest

import re

from postgrest.exceptions import APIError

from api.store import LastAdminError, SupabaseAppStore


def _ilike_match(value: str, pattern: str) -> bool:
    regex = re.escape(pattern).replace(re.escape("%"), ".*").replace("_", ".")
    return re.fullmatch(regex, value, re.IGNORECASE) is not None


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    """Minimal fluent stand-in for the Supabase query builder."""

    def __init__(self, client, table, rows):
        self._client = client
        self._table = table
        self._rows = rows
        self._filters: dict[str, object] = {}
        self._ilike: tuple[str, str] | None = None
        self._op = "select"
        self._payload = None

    def select(self, *_args, **_kwargs):
        self._op = "select"
        return self

    def ilike(self, column, pattern):
        self._op = "select"
        self._ilike = (column, pattern)
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def limit(self, _n):
        return self

    def _matches(self, row) -> bool:
        if not all(str(row.get(k)) == str(v) for k, v in self._filters.items()):
            return False
        if self._ilike is not None:
            column, pattern = self._ilike
            return _ilike_match(str(row.get(column) or ""), pattern)
        return True

    def execute(self):
        if self._op == "insert":
            if self._table in self._client.insert_should_fail:
                raise self._client.insert_should_fail[self._table]
            self._client.inserted.setdefault(self._table, []).append(self._payload)
            return _Result([self._payload])
        if self._op == "update":
            updated = []
            for row in self._rows:
                if self._matches(row):
                    row.update(self._payload)
                    updated.append(row)
            return _Result(updated)
        return _Result([row for row in self._rows if self._matches(row)])


class _Rpc:
    def __init__(self, client, name, params):
        self._client = client
        self._name = name
        self._params = params

    def execute(self):
        if self._name != "set_profile_role_with_audit":
            raise AssertionError(f"unexpected rpc {self._name!r}")
        return _Result(self._client._set_profile_role_with_audit(self._params))


class FakeSupabaseClient:
    def __init__(self, profiles):
        self.tables: dict[str, list[dict]] = {"profiles": profiles}
        self.inserted: dict[str, list[dict]] = {}
        self.insert_should_fail: dict[str, Exception] = {}

    def table(self, name):
        rows = self.tables.setdefault(name, [])
        return _Query(self, name, rows)

    def rpc(self, name, params):
        return _Rpc(self, name, params)

    def _set_profile_role_with_audit(self, params):
        """Mirror the SQL function: role update + audit insert, all-or-nothing."""
        athlete_id = str(params["p_athlete_id"])
        profile = next(
            (row for row in self.tables["profiles"] if str(row.get("id")) == athlete_id),
            None,
        )
        if profile is None:
            raise APIError({"message": f"profile_missing:{athlete_id}", "code": "P0002"})
        previous_role = str(profile.get("role") or "athlete")
        expected = params.get("p_expected_previous_role")
        if expected is not None and previous_role != expected:
            raise APIError(
                {
                    "message": f"stale_profile_role:{athlete_id} expected {expected}, got {previous_role}",
                    "code": "P0001",
                }
            )
        new_role = str(params["p_new_role"])
        target_email = str(profile.get("email") or params.get("p_target_email") or "").lower()
        if previous_role == new_role:
            return {
                "athlete_id": athlete_id,
                "email": target_email,
                "previous_role": previous_role,
                "new_role": new_role,
                "changed": False,
            }
        action = "promote" if new_role == "admin" else "revoke"
        # Transactional emulation: a failing audit insert aborts before the
        # role is touched, exactly like the single-transaction SQL function.
        failure = self.insert_should_fail.get("admin_role_audit")
        if failure is not None:
            raise failure
        profile["role"] = new_role
        self.inserted.setdefault("admin_role_audit", []).append(
            {
                "target_athlete_id": athlete_id,
                "target_email": target_email,
                "previous_role": previous_role,
                "new_role": new_role,
                "action": action,
                "actor": params.get("p_actor"),
                "reason": params.get("p_reason"),
            }
        )
        return {
            "athlete_id": athlete_id,
            "email": target_email,
            "previous_role": previous_role,
            "new_role": new_role,
            "action": action,
            "changed": True,
        }


def _store(profiles):
    client = FakeSupabaseClient(profiles)
    store = SupabaseAppStore(client=client, admin_emails=set())
    return store, client


def _profile(email, role="athlete", pid="uid-1"):
    return {"id": pid, "email": email, "role": role}


def test_promote_changes_role_and_writes_audit():
    store, client = _store([_profile("a@x.com", "athlete")])
    result = store.set_profile_role(email="a@x.com", new_role="admin", actor="op", reason="coach")

    assert result["changed"] is True
    assert result["action"] == "promote"
    assert result["previous_role"] == "athlete"
    assert result["new_role"] == "admin"
    assert client.tables["profiles"][0]["role"] == "admin"

    audit = client.inserted["admin_role_audit"]
    assert len(audit) == 1
    assert audit[0]["action"] == "promote"
    assert audit[0]["target_email"] == "a@x.com"
    assert audit[0]["actor"] == "op"
    assert audit[0]["reason"] == "coach"


def test_set_role_returns_authoritative_rpc_values():
    store, client = _store([_profile("stale@x.com", "athlete", pid="uid-1")])
    original_rpc = client._set_profile_role_with_audit

    def _return_authoritative_row(params):
        original_rpc(params)
        return [
            {
                "athlete_id": "uid-1",
                "email": "authoritative@x.com",
                "previous_role": "athlete",
                "new_role": "admin",
                "action": "promote",
                "changed": True,
            }
        ]

    client._set_profile_role_with_audit = _return_authoritative_row

    result = store.set_profile_role(email="stale@x.com", new_role="admin", actor="op")

    assert result == {
        "athlete_id": "uid-1",
        "email": "authoritative@x.com",
        "previous_role": "athlete",
        "new_role": "admin",
        "action": "promote",
        "changed": True,
    }


def test_revoke_demotes_to_athlete_when_other_admins_remain():
    store, client = _store(
        [_profile("b@x.com", "admin", pid="1"), _profile("keeper@x.com", "admin", pid="2")]
    )
    result = store.set_profile_role(email="b@x.com", new_role="athlete", actor="op")

    assert result["action"] == "revoke"
    assert client.tables["profiles"][0]["role"] == "athlete"
    assert client.inserted["admin_role_audit"][0]["action"] == "revoke"


def test_revoke_last_admin_is_blocked_and_writes_nothing():
    store, client = _store([_profile("solo@x.com", "admin")])
    with pytest.raises(LastAdminError):
        store.set_profile_role(email="solo@x.com", new_role="athlete", actor="op")

    # No demotion, no audit row.
    assert client.tables["profiles"][0]["role"] == "admin"
    assert "admin_role_audit" not in client.inserted


def test_revoke_last_admin_allowed_with_override():
    store, client = _store([_profile("solo@x.com", "admin")])
    result = store.set_profile_role(
        email="solo@x.com", new_role="athlete", actor="op", allow_last_admin=True
    )
    assert result["changed"] is True
    assert client.tables["profiles"][0]["role"] == "athlete"


def test_email_lookup_falls_back_to_case_insensitive_for_legacy_rows():
    # Legacy row stored with mixed-case email; the lowercase fast-path misses it.
    store, client = _store([_profile("Mixed@X.com", "athlete")])
    result = store.set_profile_role(email="mixed@x.com", new_role="admin", actor="op")
    assert result["changed"] is True
    assert client.tables["profiles"][0]["role"] == "admin"


def test_set_role_is_idempotent_and_writes_no_audit():
    store, client = _store([_profile("c@x.com", "admin")])
    result = store.set_profile_role(email="c@x.com", new_role="admin", actor="op")

    assert result["changed"] is False
    assert "admin_role_audit" not in client.inserted


def test_email_lookup_is_case_insensitive():
    store, client = _store([_profile("mixed@x.com", "athlete")])
    result = store.set_profile_role(email="MIXED@X.COM", new_role="admin", actor="op")
    assert result["changed"] is True
    assert client.tables["profiles"][0]["role"] == "admin"


def test_unknown_email_raises_lookup_error():
    store, _ = _store([_profile("a@x.com")])
    with pytest.raises(LookupError):
        store.set_profile_role(email="missing@x.com", new_role="admin", actor="op")


def test_invalid_role_raises_value_error():
    store, _ = _store([_profile("a@x.com")])
    with pytest.raises(ValueError):
        store.set_profile_role(email="a@x.com", new_role="superuser", actor="op")


def test_audit_write_failure_rolls_back_role_change(caplog):
    store, client = _store([_profile("a@x.com", "athlete")])
    client.insert_should_fail["admin_role_audit"] = APIError({"message": "no table"})

    with pytest.raises(RuntimeError, match="rolled back"):
        store.set_profile_role(email="a@x.com", new_role="admin", actor="op")

    # The role change and the audit insert commit in one transaction: if the
    # audit write fails, the role change must not land either.
    assert client.tables["profiles"][0]["role"] == "athlete"
    assert "admin_role_audit" not in client.inserted
    assert any("role:change_rolled_back" in rec.message for rec in caplog.records)


def test_concurrent_role_change_is_rejected_by_cas_guard():
    # The RPC CAS-checks the expected previous role against the locked row, so
    # a decision made against a stale read cannot write a misleading audit row.
    store, client = _store([_profile("a@x.com", "athlete")])
    original_rpc = client._set_profile_role_with_audit

    def _race_then_call(params):
        # Simulate another actor changing the role between the store's read
        # and the RPC executing.
        client.tables["profiles"][0]["role"] = "admin"
        return original_rpc(params)

    client._set_profile_role_with_audit = _race_then_call

    with pytest.raises(RuntimeError, match="rolled back"):
        store.set_profile_role(email="a@x.com", new_role="admin", actor="op")

    assert "admin_role_audit" not in client.inserted


def test_list_and_count_admins():
    store, _ = _store(
        [
            _profile("admin1@x.com", "admin", pid="1"),
            _profile("athlete@x.com", "athlete", pid="2"),
            _profile("admin2@x.com", "admin", pid="3"),
        ]
    )
    admins = store.list_admin_profiles()
    assert {row["email"] for row in admins} == {"admin1@x.com", "admin2@x.com"}
    assert store.count_admin_profiles() == 2


# ---------------------------------------------------------------------------
# CLI tool
# ---------------------------------------------------------------------------


def _patch_cli_store(monkeypatch, store):
    from tools import manage_admin

    monkeypatch.setattr(manage_admin.SupabaseAppStore, "from_env", classmethod(lambda cls: store))
    return manage_admin


def test_cli_promote_changes_role(monkeypatch, capsys):
    store, client = _store([_profile("a@x.com", "athlete")])
    manage_admin = _patch_cli_store(monkeypatch, store)

    exit_code = manage_admin.main(["promote", "a@x.com", "--reason", "coach"])

    assert exit_code == 0
    assert client.tables["profiles"][0]["role"] == "admin"
    assert "promoted a@x.com" in capsys.readouterr().out


def test_cli_revoke_last_admin_is_blocked(monkeypatch, capsys):
    store, client = _store([_profile("only@x.com", "admin")])
    manage_admin = _patch_cli_store(monkeypatch, store)

    exit_code = manage_admin.main(["revoke", "only@x.com"])

    assert exit_code == 2
    assert "--force-last-admin" in capsys.readouterr().out
    assert client.tables["profiles"][0]["role"] == "admin"


def test_cli_revoke_last_admin_forced_succeeds(monkeypatch, capsys):
    store, client = _store([_profile("only@x.com", "admin")])
    manage_admin = _patch_cli_store(monkeypatch, store)

    exit_code = manage_admin.main(["revoke", "only@x.com", "--force-last-admin"])

    assert exit_code == 0
    assert "0 admins" in capsys.readouterr().out
    assert client.tables["profiles"][0]["role"] == "athlete"


def test_cli_unknown_email_returns_error_code(monkeypatch, capsys):
    store, _ = _store([_profile("a@x.com", "athlete")])
    manage_admin = _patch_cli_store(monkeypatch, store)

    exit_code = manage_admin.main(["promote", "missing@x.com"])

    assert exit_code == 2
    assert "error:" in capsys.readouterr().out
