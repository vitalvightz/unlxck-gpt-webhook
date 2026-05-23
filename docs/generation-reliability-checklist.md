# Generation reliability checklist

Before merging generation-related changes, verify all of these are green:

- Run backend quality checks: `ruff check api fightcamp tests tools`.
- Run focused generation/runtime regressions: `pytest -q tests/test_api_generation_flows.py tests/test_generation_runtime.py`.
- Run backend suite: `pytest tests/ -q` (or the repository’s configured full backend equivalent).
- Run frontend checks from `web/`: `npm run typecheck` and `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run build`.
- If JSON bank validation is in scope, run: `python tools/validate_banks.py`.
- Confirm active generation states never route to `/generate`; they only reconnect and refresh status.
- Confirm `review_required` routes with `?review_required=1` when a plan id exists.
- Confirm stale running jobs cannot remain running forever and are recovered/failed safely.
- Confirm retry cannot create duplicate active jobs for the same athlete.
- Confirm localStorage pending state cannot override backend active-job truth.
