# Service-role authorization checklist (FastAPI backend)

This backend intentionally uses `SUPABASE_SERVICE_ROLE_KEY` server-side in `api/auth.py` and `api/store.py`.
Because service-role bypasses Supabase RLS, every route must enforce access in Python.

## Route checklist for `api/app.py`

- Athlete routes must depend on `require_profile`.
- Admin routes must depend on `require_admin`.
- Plan/intake/job lookup routes must check ownership (`row.athlete_id == profile.athlete_id`) unless admin.
- Nutrition routes must read/update only the authenticated profile's `athlete_id` unless admin endpoint.
- Frontend/public env vars must never include `SUPABASE_SERVICE_ROLE_KEY`.

## Regression expectations

- User A cannot fetch User B plan by `plan_id`.
- User A cannot rename/delete User B plan.
- User A cannot fetch User B generation job by `job_id`.
- User A cannot retry User B generation job.
- User A cannot access admin routes.
- User A cannot update User B nutrition/profile/intake data through indirect IDs.
