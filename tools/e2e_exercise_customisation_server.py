"""Seeded API for the exercise-customisation Playwright run (local only).

Serves the real app over an in-memory store holding one AI open plan whose
workout falls on today, so the browser exercises the real ranking, override
writes and effective-plan reads end to end:

    python tools/e2e_exercise_customisation_server.py --port 8765
    EXERCISE_TEST_API=http://127.0.0.1:8765 npx playwright test exercise-customisation
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def build_app():
    import fightcamp.rehab_clinical as rehab_clinical
    import api.services.today_service as today_service
    from api.app import create_app
    from tests.support import FakeAuthService, FakeStage2Automator, FakeStore, _planner, finalized_result, seed_default_profiles
    from tests.test_exercise_customisation import seed_open
    from api.auth import AuthenticatedUser

    # The fixture has no clinical policies, like the API tests.
    rehab_clinical.load_clinical_policies = lambda: ()
    today_service.load_clinical_policies = lambda: ()
    store = FakeStore()
    seed_default_profiles(store)
    seed_open(store)
    athlete = AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    app = create_app(
        store=store, auth_service=FakeAuthService({"athlete-token": athlete}), planner=_planner,
        stage2_automator=FakeStage2Automator(result=finalized_result()), enable_in_process_generation=False,
    )

    @app.post("/__e2e/reset")
    def reset():  # Each browser case starts from the generated plan alone.
        store.session_completions.clear()
        store.today_checkins.clear()
        seed_open(store)
        return {"ok": True}

    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    uvicorn.run(build_app(), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
