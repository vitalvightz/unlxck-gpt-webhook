"""Deterministic mental-calendar audit; run unchanged on Main and PR #2879.

Usage: python tools/audit_mental_training.py /tmp/mental-audit.json
No live model calls, database reads or production writes. Uses the anonymised
intake for plan fdf2fc9d and fixed creation time/seeds. Compare `physical` lists
between revisions to check complete appointments, selections and prescriptions.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]

from api.models import PlanRequest  # noqa: E402
from api.structured_plan_deterministic_fallback import build_deterministic_structured_plan  # noqa: E402
from fightcamp import input_parsing, stage2_planning_brief  # noqa: E402
from fightcamp.main import generate_plan_sync  # noqa: E402
from fightcamp.physical_session_frequency import is_physical_session_role, role_countdown_offset  # noqa: E402
from support import _build_request  # noqa: E402

NOW = datetime(2026, 10, 14, 3, 40)
MENTAL = {'fight_visualization', 'neural_visualization', 'tactical_watch', 'tactical_cue_card', 'self_review'}


def scenarios():
    intake = json.loads((ROOT / 'tests/fixtures/programme_fidelity/affected_intake.json').read_text())
    intake['random_seed'] = 1
    yield 'affected_boxer', PlanRequest(**intake).to_payload()
    for sport in ['boxing', 'kickboxing', 'muay_thai', 'mma']:
        for priority in [False, True]:
            for days in [49, 18, 6]:
                payload = _build_request({
                    'athlete': {'technical_style': [sport]},
                    'fight_date': (NOW.date() + timedelta(days=days)).isoformat(),
                    'key_goals': ['mental preparation'] if priority else ['strength'],
                }).to_payload()
                payload['random_seed'] = 3
                yield f'{sport}_{days}_{"priority" if priority else "default"}', payload


def audit(payload):
    with patch.object(input_parsing, '_utc_now', lambda: NOW), patch.object(stage2_planning_brief, '_utc_now', lambda: NOW):
        brief = generate_plan_sync(payload)['planning_brief']
    roles = [r for w in brief['weekly_role_map']['weeks'] for r in w.get('session_roles', [])
             if role_countdown_offset(r) is not None]
    mental = [r for r in roles if r.get('role_key') in MENTAL]
    physical = [r for r in roles if is_physical_session_role(r)]
    counts = Counter(role_countdown_offset(r) for r in mental)

    def dose(role):
        value = role.get('prescribed_duration_min') or role.get('duration_min') or 0
        return value[-1] if isinstance(value, (list, tuple)) else value

    card = build_deterministic_structured_plan(brief)
    hard = []
    for week in card['weeks']:
        for day in week['days']:
            view = day.get('today_card') or {}
            if 'hard sparring' in f"{view.get('headline', '')} {view.get('coach_led_contact', '')}".lower():
                hard.append(day['countdown_label'])
    return {
        'sport': brief['athlete_snapshot']['sport'],
        'mental_tasks': len(mental), 'mental_minutes': sum(dose(r) for r in mental),
        'frequencies': {k: sorted([role_countdown_offset(r) for r in mental if r['role_key'] == k], reverse=True)
                        for k in sorted(MENTAL)},
        'stacked_days': sum(n > 1 for n in counts.values()),
        'mental_only_days': sorted(set(counts) - {role_countdown_offset(r) for r in physical}),
        'physical_appointments': len(physical), 'hard_sparring': hard,
        'physical': physical,
    }


def main():
    output = Path(sys.argv[1])
    results = {}
    for name, payload in scenarios():
        results[name] = audit(payload)
        output.write_text(json.dumps(results, indent=2, default=str))
        print(name, json.dumps({k: v for k, v in results[name].items() if k != 'physical'}), flush=True)


if __name__ == '__main__':
    main()
