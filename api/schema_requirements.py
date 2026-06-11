"""Centralized definition of the Supabase schema the backend depends on.

This module is intentionally dependency-light (standard library only) so it can
be imported by:

* ``api.store`` (the live runtime store) to share required column constants, and
* ``tools/check_supabase_runtime_schema.py`` (the deploy-gate checker), and
* the unit tests, *without* pulling in ``supabase``/``fastapi`` or requiring
  live credentials.

It contains two things:

1. The canonical *requirements* (tables, columns, functions, indexes, RLS).
2. Pure comparison helpers that diff those requirements against a catalog
   snapshot (a plain ``dict``). The helpers never touch the network and never
   read user row data, which keeps them trivially unit-testable and safe to use
   as a production deploy gate.

Note on the intakes table: the application stores athlete intake records in the
``public.athlete_intakes`` table (see ``api/store.py``). There is no table named
``intakes``; ``athlete_intakes`` is the canonical name the backend depends on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# Canonical table names
# ---------------------------------------------------------------------------

INTAKES_TABLE = "athlete_intakes"

REQUIRED_TABLES: tuple[str, ...] = (
    "profiles",
    "plans",
    "generation_jobs",
    INTAKES_TABLE,
    "plan_generation_rate_limits",
    # Accountability trail for admin role changes (api/store.py::set_profile_role).
    # Required so the deploy gate catches an environment where the migration has
    # not been applied and admin changes would silently lose their audit record.
    "admin_role_audit",
    # Live athlete daily tracking (api/routes/daily.py + api/store.py). The
    # dashboard, check-in, session-log, and admin review-queue endpoints all
    # read/write these tables, so a missing migration must fail the deploy gate.
    "daily_checkins",
    "session_logs",
    "injury_flags",
    "adaptation_notes",
    "admin_reviews",
)

# ---------------------------------------------------------------------------
# Required columns
# ---------------------------------------------------------------------------

# The Stage 1/Stage 2 plan runtime columns. This is the canonical source of
# truth shared with ``api.store`` (imported there as PLAN_RUNTIME_REQUIRED_COLUMNS)
# so the live store and the deploy-gate checker can never drift apart.
PLAN_RUNTIME_REQUIRED_COLUMNS: tuple[str, ...] = (
    "draft_plan_text",
    "final_plan_text",
    "planning_brief",
    "stage2_payload",
    "stage2_handoff_text",
    "stage2_retry_text",
    "stage2_validator_report",
    "stage2_status",
    "stage2_attempt_count",
    "parsing_metadata",
)

REQUIRED_PLANS_COLUMNS: tuple[str, ...] = (
    "id",
    "athlete_id",
    "intake_id",
    "plan_text",
    *PLAN_RUNTIME_REQUIRED_COLUMNS,
    # Non-runtime columns the backend reads/writes in create_plan() and
    # list_user_plans() (PLAN_SUMMARY_SELECT) — see api/store.py.
    "fight_date",
    "technical_style",
    "full_name",
    "plan_name",
    "coach_notes",
    "pdf_url",
    "why_log",
    "status",
    "created_at",
)

# Stage 2 token/cost telemetry written to generation_jobs after finalization
# (see api/store.py::record_stage2_cost). These let an admin/dev audit cost per
# athlete/job straight from the database instead of scraping logs. All columns
# are nullable: a row predating the feature, or a Stage 2 call where the OpenAI
# response omitted usage, simply leaves them NULL. The runtime write is
# best-effort and degrades gracefully if the columns are absent, but they are
# listed here so the deploy gate (tools/check_supabase_runtime_schema.py)
# guarantees the migration is applied in production where the audit is relied on.
GENERATION_JOB_STAGE2_COST_COLUMNS: tuple[str, ...] = (
    "stage2_model",
    "stage2_input_tokens",
    "stage2_output_tokens",
    "stage2_total_tokens",
    "stage2_estimated_cost_usd",
    "stage2_attempt_count",
    "stage2_response_id",
    "stage2_cost_recorded_at",
)

REQUIRED_GENERATION_JOBS_COLUMNS: tuple[str, ...] = (
    "id",
    "athlete_id",
    "client_request_id",
    "source",
    "status",
    "attempt_count",
    "heartbeat_at",
    "started_at",
    "completed_at",
    "failed_at",
    # Worker ownership for the running attempt (claim_generation_job writes
    # them; the terminal RPCs enforce them).
    "claimed_by",
    "claimed_at",
    "created_at",
    "updated_at",
    "error",
    "intake_id",
    "plan_id",
    "progress_milestones",
    "request_payload",
    "payload_hash",
    "stage1_result",
    "final_result",
    *GENERATION_JOB_STAGE2_COST_COLUMNS,
)

REQUIRED_PROFILES_COLUMNS: tuple[str, ...] = (
    "id",
    "email",
    "full_name",
    "role",
    "username",
    "username_change_history",
    "avatar_url",
    "onboarding_draft",
    "created_at",
    "updated_at",
    # Additional columns written by profile bootstrap in
    # _build_profile_payload() — see api/store.py.
    "technical_style",
    "tactical_style",
    "stance",
    "professional_status",
    "record_summary",
    "athlete_timezone",
    "athlete_locale",
    "appearance_mode",
)

REQUIRED_ADMIN_ROLE_AUDIT_COLUMNS: tuple[str, ...] = (
    "id",
    "target_athlete_id",
    "target_email",
    "previous_role",
    "new_role",
    "action",
    "actor",
    "reason",
    "created_at",
)

REQUIRED_DAILY_CHECKINS_COLUMNS: tuple[str, ...] = (
    "id",
    "athlete_id",
    "checkin_date",
    "readiness",
    "fatigue",
    "soreness",
    "sleep_quality",
    "sleep_hours",
    "injury_note",
    "notes",
    "readiness_state",
    "created_at",
    "updated_at",
)

REQUIRED_SESSION_LOGS_COLUMNS: tuple[str, ...] = (
    "id",
    "athlete_id",
    "plan_id",
    "session_date",
    "session_type",
    "completed",
    "rpe",
    "duration_minutes",
    "notes",
    "created_at",
    "updated_at",
)

REQUIRED_INJURY_FLAGS_COLUMNS: tuple[str, ...] = (
    "id",
    "athlete_id",
    "plan_id",
    "source",
    "body_area",
    "description",
    "severity",
    "status",
    "resolved_at",
    "created_at",
    "updated_at",
)

REQUIRED_ADAPTATION_NOTES_COLUMNS: tuple[str, ...] = (
    "id",
    "athlete_id",
    "plan_id",
    "checkin_id",
    "session_log_id",
    "rule_code",
    "decision",
    "summary",
    "details",
    "created_at",
)

REQUIRED_ADMIN_REVIEWS_COLUMNS: tuple[str, ...] = (
    "id",
    "athlete_id",
    "adaptation_note_id",
    "injury_flag_id",
    "reason",
    "status",
    "resolution_notes",
    "resolved_by",
    "resolved_at",
    "created_at",
    "updated_at",
)

# Map of table -> required columns, used by the checker.
REQUIRED_COLUMNS: Mapping[str, tuple[str, ...]] = {
    "plans": REQUIRED_PLANS_COLUMNS,
    "generation_jobs": REQUIRED_GENERATION_JOBS_COLUMNS,
    "profiles": REQUIRED_PROFILES_COLUMNS,
    "admin_role_audit": REQUIRED_ADMIN_ROLE_AUDIT_COLUMNS,
    "daily_checkins": REQUIRED_DAILY_CHECKINS_COLUMNS,
    "session_logs": REQUIRED_SESSION_LOGS_COLUMNS,
    "injury_flags": REQUIRED_INJURY_FLAGS_COLUMNS,
    "adaptation_notes": REQUIRED_ADAPTATION_NOTES_COLUMNS,
    "admin_reviews": REQUIRED_ADMIN_REVIEWS_COLUMNS,
}

# ---------------------------------------------------------------------------
# Required functions / RPCs
# ---------------------------------------------------------------------------

# Stored schema-qualified for clear reporting; comparison is done on the bare
# proname within the ``public`` schema.
REQUIRED_FUNCTIONS: tuple[str, ...] = (
    "public.change_profile_username",
    "public.try_parse_timestamptz",
    "public.check_plan_generation_short_window_limit",
    "public.create_generation_job_with_daily_limit",
    "public.claim_generation_job",
    "public.complete_generation_job",
    "public.fail_generation_job",
    "public.prevent_self_role_escalation",
    "public.prevent_username_policy_bypass",
    # Atomic role change + audit write (api/store.py::set_profile_role); a
    # missing function would silently break the only sanctioned role-change
    # path, so the deploy gate must catch it.
    "public.set_profile_role_with_audit",
    "public.is_admin",
    # Invoked during AppStore.validate_runtime_schema() at backend startup
    # (api/store.py); a missing lock RPC must fail this check too.
    "public.validate_generation_job_active_lock",
)

# ---------------------------------------------------------------------------
# Required indexes / constraints
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndexRequirement:
    """A structural requirement satisfied by any one of ``accepted_names``.

    A requirement is met when *any* of ``accepted_names`` is present among the
    database's indexes or constraints. Several requirements can legitimately be
    served by either an index or a uniqueness constraint, so the checker unions
    both name sources before testing.
    """

    label: str
    accepted_names: tuple[str, ...]

    def is_satisfied(self, present_names: Iterable[str]) -> bool:
        present = set(present_names)
        return any(name in present for name in self.accepted_names)


INDEX_REQUIREMENTS: tuple[IndexRequirement, ...] = (
    IndexRequirement(
        label="generation_jobs active job uniqueness/lock",
        accepted_names=("generation_jobs_one_active_job_per_athlete",),
    ),
    IndexRequirement(
        label="generation_jobs athlete/client request uniqueness",
        accepted_names=(
            "generation_jobs_athlete_client_request_uidx",
            "generation_jobs_athlete_client_request_key",
        ),
    ),
    IndexRequirement(
        label="plan_generation_rate_limits athlete/created index",
        accepted_names=("plan_generation_rate_limits_athlete_created_idx",),
    ),
    IndexRequirement(
        label="profiles username uniqueness",
        accepted_names=("profiles_username_key", "profiles_username_idx"),
    ),
    # One check-in per athlete per day; the store's upsert path
    # (api/store.py::upsert_daily_checkin) depends on this conflict target.
    IndexRequirement(
        label="daily_checkins athlete/date uniqueness",
        accepted_names=("daily_checkins_athlete_date_key",),
    ),
)

# ---------------------------------------------------------------------------
# RLS requirements
# ---------------------------------------------------------------------------

RLS_REQUIRED_TABLES: tuple[str, ...] = (
    "profiles",
    "plans",
    INTAKES_TABLE,
    "generation_jobs",
    "plan_generation_rate_limits",
    "admin_role_audit",
    "daily_checkins",
    "session_logs",
    "injury_flags",
    "adaptation_notes",
    "admin_reviews",
)


# ---------------------------------------------------------------------------
# Introspection snapshot + comparison
# ---------------------------------------------------------------------------


class SchemaIntrospectionError(ValueError):
    """Raised when the catalog snapshot payload is malformed."""


@dataclass(frozen=True)
class SchemaIntrospection:
    """A normalized, network-free snapshot of the live database catalog.

    All names are bare object names within the ``public`` schema. No row data is
    ever captured here — only catalog metadata (table/column/function/index
    names and per-table RLS flags).
    """

    tables: frozenset[str]
    columns_by_table: Mapping[str, frozenset[str]]
    functions: frozenset[str]
    index_constraint_names: frozenset[str]
    rls_by_table: Mapping[str, bool]

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "SchemaIntrospection":
        """Build a snapshot from the ``runtime_schema_introspection`` RPC payload."""
        if not isinstance(payload, Mapping):
            raise SchemaIntrospectionError("introspection payload must be an object")

        def _str_set(key: str) -> frozenset[str]:
            raw = payload.get(key) or []
            if not isinstance(raw, (list, tuple)):
                raise SchemaIntrospectionError(f"'{key}' must be a list")
            return frozenset(str(item) for item in raw if item is not None)

        columns_raw = payload.get("columns") or {}
        if not isinstance(columns_raw, Mapping):
            raise SchemaIntrospectionError("'columns' must be an object")
        columns_by_table: dict[str, frozenset[str]] = {}
        for table, cols in columns_raw.items():
            if cols is not None and not isinstance(cols, (list, tuple)):
                raise SchemaIntrospectionError(f"columns for table '{table}' must be a list")
            columns_by_table[str(table)] = frozenset(
                str(c) for c in (cols or []) if c is not None
            )

        rls_raw = payload.get("rls") or {}
        if not isinstance(rls_raw, Mapping):
            raise SchemaIntrospectionError("'rls' must be an object")
        rls_by_table = {str(table): bool(enabled) for table, enabled in rls_raw.items()}

        # Indexes and constraints are unioned: a requirement may be served by
        # either an index or a uniqueness constraint of the same logical intent.
        index_constraint_names = _str_set("indexes") | _str_set("constraints")

        return cls(
            tables=_str_set("tables"),
            columns_by_table=columns_by_table,
            functions=_str_set("functions"),
            index_constraint_names=index_constraint_names,
            rls_by_table=rls_by_table,
        )


@dataclass
class SchemaCheckResult:
    """Outcome of comparing requirements against an introspection snapshot."""

    missing_tables: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    missing_functions: list[str] = field(default_factory=list)
    missing_indexes: list[str] = field(default_factory=list)
    rls_issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (
            self.missing_tables
            or self.missing_columns
            or self.missing_functions
            or self.missing_indexes
            or self.rls_issues
        )

    def format_report(self) -> str:
        if self.ok:
            return "✅ Supabase runtime schema check passed."

        lines = ["❌ Supabase runtime schema check failed."]
        sections = (
            ("Missing tables:", self.missing_tables),
            ("Missing columns:", self.missing_columns),
            ("Missing functions:", self.missing_functions),
            ("Missing indexes/constraints:", self.missing_indexes),
            ("RLS issues:", self.rls_issues),
        )
        for header, items in sections:
            if not items:
                continue
            lines.append(header)
            lines.extend(f"- {item}" for item in items)
        return "\n".join(lines)


# --- individual diff helpers (small + unit-testable) -----------------------


def find_missing_tables(present_tables: Iterable[str]) -> list[str]:
    present = set(present_tables)
    return [table for table in REQUIRED_TABLES if table not in present]


def find_missing_columns(columns_by_table: Mapping[str, Iterable[str]]) -> list[str]:
    """Return ``table.column`` entries for every required-but-absent column.

    A required table that is entirely absent reports each of its columns as
    missing so the operator gets a complete picture in a single run.
    """
    missing: list[str] = []
    for table, required in REQUIRED_COLUMNS.items():
        present = set(columns_by_table.get(table, ()) or ())
        missing.extend(f"{table}.{column}" for column in required if column not in present)
    return missing


def find_missing_functions(present_functions: Iterable[str]) -> list[str]:
    present = set(present_functions)
    missing: list[str] = []
    for qualified in REQUIRED_FUNCTIONS:
        bare = qualified.split(".", 1)[-1]
        if bare not in present:
            missing.append(qualified)
    return missing


def find_missing_index_constraints(present_names: Iterable[str]) -> list[str]:
    present = set(present_names)
    return [req.label for req in INDEX_REQUIREMENTS if not req.is_satisfied(present)]


def find_rls_issues(rls_by_table: Mapping[str, bool]) -> list[str]:
    issues: list[str] = []
    for table in RLS_REQUIRED_TABLES:
        if not rls_by_table.get(table, False):
            issues.append(f"{table} RLS is not enabled")
    return issues


def evaluate_schema(introspection: SchemaIntrospection) -> SchemaCheckResult:
    """Compare a normalized snapshot against all requirements."""
    return SchemaCheckResult(
        missing_tables=find_missing_tables(introspection.tables),
        missing_columns=find_missing_columns(introspection.columns_by_table),
        missing_functions=find_missing_functions(introspection.functions),
        missing_indexes=find_missing_index_constraints(introspection.index_constraint_names),
        rls_issues=find_rls_issues(introspection.rls_by_table),
    )


def evaluate_payload(payload: Mapping[str, object]) -> SchemaCheckResult:
    """Convenience: parse a raw RPC payload and evaluate it in one step."""
    return evaluate_schema(SchemaIntrospection.from_payload(payload))


__all__: Sequence[str] = (
    "INTAKES_TABLE",
    "REQUIRED_TABLES",
    "PLAN_RUNTIME_REQUIRED_COLUMNS",
    "REQUIRED_PLANS_COLUMNS",
    "GENERATION_JOB_STAGE2_COST_COLUMNS",
    "REQUIRED_GENERATION_JOBS_COLUMNS",
    "REQUIRED_PROFILES_COLUMNS",
    "REQUIRED_COLUMNS",
    "REQUIRED_FUNCTIONS",
    "IndexRequirement",
    "INDEX_REQUIREMENTS",
    "RLS_REQUIRED_TABLES",
    "SchemaIntrospection",
    "SchemaIntrospectionError",
    "SchemaCheckResult",
    "find_missing_tables",
    "find_missing_columns",
    "find_missing_functions",
    "find_missing_index_constraints",
    "find_rls_issues",
    "evaluate_schema",
    "evaluate_payload",
)
