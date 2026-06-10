"""Promote, revoke, and list UNLXCK admin roles.

UNLXCK_ADMIN_EMAILS only *seeds* a profile's role the first time the profile is
created. After that, ``profiles.role`` is authoritative and editing the env var
has no effect — removing an email does NOT demote an existing admin. This is the
sanctioned operational tool for granting and revoking admin access after first
sign-in. Every change is written to ``public.admin_role_audit``.

Requires service-role credentials (the same ones the backend uses):

    SUPABASE_URL=...
    SUPABASE_SERVICE_ROLE_KEY=...

Usage:
    python tools/manage_admin.py list
    python tools/manage_admin.py promote athlete@example.com --reason "new coach"
    python tools/manage_admin.py revoke former-admin@example.com --reason "offboarded"

Exit codes: 0 success / 2 usage or operational error.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

# Allow running as a standalone script (``python tools/...``) from the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from api.store import LastAdminError, SupabaseAppStore  # noqa: E402  (after sys.path setup)


def _actor() -> str:
    # Identify who ran the change for the audit trail. Prefer an explicit env
    # override (useful in CI/runbooks), fall back to the OS user.
    explicit = os.getenv("UNLXCK_ADMIN_ACTOR", "").strip()
    if explicit:
        return explicit
    try:
        return f"cli:{getpass.getuser()}"
    except Exception:  # pragma: no cover - getuser can fail in odd environments
        return "cli:unknown"


def _build_store() -> SupabaseAppStore:
    try:
        return SupabaseAppStore.from_env()
    except RuntimeError as exc:
        raise SystemExit(
            f"error: {exc}\n"
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY before running this tool."
        ) from exc


def _cmd_list(store: SupabaseAppStore) -> int:
    admins = store.list_admin_profiles()
    if not admins:
        print("No admins found. WARNING: nobody can access the admin surface.")
        return 0
    print(f"{len(admins)} admin(s):")
    for row in sorted(admins, key=lambda r: str(r.get("email") or "")):
        print(f"  - {row.get('email')}  ({row.get('id')})")
    return 0


def _cmd_set_role(
    store: SupabaseAppStore,
    *,
    email: str,
    new_role: str,
    reason: str | None,
    allow_last_admin: bool = False,
) -> int:
    try:
        result = store.set_profile_role(
            email=email,
            new_role=new_role,
            actor=_actor(),
            reason=reason,
            allow_last_admin=allow_last_admin,
        )
    except LastAdminError as exc:
        print(f"error: {exc}")
        print("Re-run with --force-last-admin if you really intend to leave zero admins.")
        return 2
    except (LookupError, ValueError) as exc:
        print(f"error: {exc}")
        return 2
    except RuntimeError as exc:
        # Atomic role+audit transaction failed: nothing was committed.
        print(f"error: {exc}")
        return 2

    if not result.get("changed"):
        print(f"No change: {result['email']} is already '{result['new_role']}'.")
        return 0

    print(
        f"{result['action']}d {result['email']}: "
        f"{result['previous_role']} -> {result['new_role']}"
    )
    remaining = store.count_admin_profiles()
    if remaining == 0:
        print("WARNING: there are now 0 admins — nobody can access the admin surface.")
    else:
        print(f"Admins remaining: {remaining}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage UNLXCK admin roles.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List current admins.")

    promote = sub.add_parser("promote", help="Grant admin to an email.")
    promote.add_argument("email")
    promote.add_argument("--reason", default=None, help="Recorded in the audit trail.")

    revoke = sub.add_parser("revoke", help="Revoke admin from an email (demote to athlete).")
    revoke.add_argument("email")
    revoke.add_argument("--reason", default=None, help="Recorded in the audit trail.")
    revoke.add_argument(
        "--force-last-admin",
        action="store_true",
        help="Allow revoking the only remaining admin (leaves zero admins).",
    )

    args = parser.parse_args(argv)
    store = _build_store()

    if args.command == "list":
        return _cmd_list(store)
    if args.command == "promote":
        return _cmd_set_role(store, email=args.email, new_role="admin", reason=args.reason)
    if args.command == "revoke":
        return _cmd_set_role(
            store,
            email=args.email,
            new_role="athlete",
            reason=args.reason,
            allow_last_admin=args.force_last_admin,
        )
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
