"""SupabaseAppStore's XP and milestone methods issue the queries production runs.

These reads and RPCs used to live in the XP services as raw-client fallbacks.
Every test store supplied its own methods or in-memory dicts, so the queries
production actually sends were never exercised. They are now store methods;
these tests pin each one against a recording client.
"""

from types import SimpleNamespace

from api.services.xp_awards import XP_ABUSE_HARDENING_VERSION, ensure_xp_abuse_hardening
from api.services.xp_progress import _read_xp_state
from api.store import SupabaseAppStore


class _Query:
    def __init__(self, log: list, target: str, data):
        self._log = log
        self._target = target
        self._data = data

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self._log.append((self._target, name, args, kwargs))
            return self

        return record

    def execute(self):
        self._log.append((self._target, "execute", (), {}))
        return SimpleNamespace(data=self._data)


class RecordingClient:
    def __init__(self, *, tables=None, rpcs=None):
        self.tables = tables or {}
        self.rpcs = rpcs or {}
        self.log: list = []

    def table(self, name):
        return _Query(self.log, name, self.tables.get(name, []))

    def rpc(self, name, params=None):
        self.log.append((name, "rpc", (params,), {}))
        return _Query(self.log, name, self.rpcs.get(name))

    def calls(self, target):
        return [(name, args) for t, name, args, _ in self.log if t == target and name != "execute"]


def _store(client: RecordingClient) -> SupabaseAppStore:
    return SupabaseAppStore(client=client, admin_emails=set())


def test_xp_progress_state_reads_the_account_and_newest_awards():
    award = {"id": "a1", "action": "daily_login", "amount": 5, "awarded_at": "t", "calendar_date": "2026-08-01"}
    client = RecordingClient(
        tables={
            "xp_accounts": [{"total_xp": 120, "last_daily_login_date": "2026-08-01"}],
            "xp_awards": [award],
        }
    )

    state = _store(client).get_xp_progress_state("athlete-1", limit=20)

    assert state == {"total_xp": 120, "last_daily_login_date": "2026-08-01", "recent_awards": [award]}
    assert client.calls("xp_accounts") == [
        ("select", ("total_xp,last_daily_login_date",)),
        ("eq", ("athlete_id", "athlete-1")),
        ("limit", (1,)),
    ]
    assert client.calls("xp_awards") == [
        ("select", ("id,action,amount,awarded_at,calendar_date",)),
        ("eq", ("athlete_id", "athlete-1")),
        ("order", ("awarded_at",)),
        ("order", ("id",)),
        ("limit", (20,)),
    ]
    orders = [kwargs for t, name, _, kwargs in client.log if t == "xp_awards" and name == "order"]
    assert orders == [{"desc": True}, {"desc": True}]


def test_xp_progress_service_normalizes_an_empty_account():
    client = RecordingClient(tables={"xp_accounts": [], "xp_awards": []})

    assert _read_xp_state(_store(client), "athlete-1") == {
        "total_xp": 0,
        "last_daily_login_date": None,
        "recent_awards": [],
    }


def test_award_exists_filters_only_on_the_given_fields():
    client = RecordingClient(tables={"xp_awards": [{"id": "a1"}]})

    assert _store(client).xp_award_exists("athlete-1", action="first_plan_ready") is True
    assert client.calls("xp_awards") == [
        ("select", ("id",)),
        ("eq", ("athlete_id", "athlete-1")),
        ("eq", ("action", "first_plan_ready")),
        ("limit", (1,)),
    ]
    assert _store(RecordingClient()).xp_award_exists("athlete-1", idempotency_key="k") is False


def test_plan_milestones_are_read_newest_first():
    row = {"id": "m1", "milestone_type": "week_completed"}
    client = RecordingClient(tables={"plan_milestones": [row]})

    assert _store(client).list_plan_milestones("athlete-1", limit=50) == [row]
    assert client.calls("plan_milestones")[-2:] == [("order", ("completed_at",)), ("limit", (50,))]
    orders = [kwargs for t, name, _, kwargs in client.log if t == "plan_milestones" and name == "order"]
    assert orders == [{"desc": True}]


def test_milestone_and_week_lifecycle_rpcs_send_their_parameters():
    client = RecordingClient(
        rpcs={
            "record_plan_milestone": [{"recorded": True}],
            "begin_week_lifecycle_reconciliation": {"claimed": True},
            "complete_week_lifecycle_reconciliation": [],
        }
    )
    store = _store(client)

    assert store.record_plan_milestone(
        "athlete-1",
        plan_id="plan-1",
        milestone_type="week_completed",
        milestone_key="week:1",
        phase_label="GPP",
        metadata={"week": 1},
    ) == {"recorded": True}
    assert store.begin_week_lifecycle_reconciliation("athlete-1", plan_id="plan-1", week_id="w1") == {
        "claimed": True
    }
    assert store.complete_week_lifecycle_reconciliation("athlete-1", plan_id="plan-1", week_id="w1") is None
    assert client.calls("record_plan_milestone") == [
        (
            "rpc",
            (
                {
                    "p_athlete_id": "athlete-1",
                    "p_plan_id": "plan-1",
                    "p_milestone_type": "week_completed",
                    "p_milestone_key": "week:1",
                    "p_phase_label": "GPP",
                    "p_metadata": {"week": 1},
                },
            ),
        )
    ]
    assert client.calls("begin_week_lifecycle_reconciliation") == [
        ("rpc", ({"p_athlete_id": "athlete-1", "p_plan_id": "plan-1", "p_week_id": "w1"},))
    ]
    assert client.calls("complete_week_lifecycle_reconciliation") == [
        ("rpc", ({"p_athlete_id": "athlete-1", "p_plan_id": "plan-1", "p_week_id": "w1"},))
    ]


def test_feedback_reconcile_rpc_sends_its_parameters():
    client = RecordingClient(rpcs={"reconcile_feedback_xp": [{"awarded": True, "xp_delta": 3}]})

    result = _store(client).reconcile_feedback_xp("athlete-1", feedback_id="f1", target_amount=3)

    assert result == {"awarded": True, "xp_delta": 3}
    assert client.calls("reconcile_feedback_xp") == [
        ("rpc", ({"p_athlete_id": "athlete-1", "p_feedback_id": "f1", "p_target_amount": 3},))
    ]


def test_live_store_hardening_check_runs_once_after_success():
    client = RecordingClient(
        rpcs={
            "validate_xp_abuse_hardening": {
                "ok": True,
                "version": XP_ABUSE_HARDENING_VERSION,
                "rollout_ready": True,
                "open_plan_scope_ready": True,
            }
        }
    )
    store = _store(client)

    ensure_xp_abuse_hardening(store)
    ensure_xp_abuse_hardening(store)

    assert client.calls("validate_xp_abuse_hardening") == [("rpc", (None,))]
