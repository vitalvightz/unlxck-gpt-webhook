from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STYLE_BANK = REPO_ROOT / 'data' / 'style_conditioning_bank.json'
COORD_BANK = REPO_ROOT / 'data' / 'coordination_bank.json'


def test_boxing_repeatability_and_low_damage_drills_exist_in_style_bank():
    data = json.loads(STYLE_BANK.read_text(encoding='utf-8'))
    items = {item['name']: item for item in data}

    expected_names = {
        'Fixed-Output Bag Clusters',
        'Tempo Pad Rounds',
        'Punch-Reset-Repeat Intervals',
        'Footwork + 1-2 Density Rounds',
        'Round-End Flurry + Controlled Recovery',
        'Technical Bag Repeatability',
        'Tempo Shadowboxing with Output Targets',
        'Pool/Bike Repeatability Circuit',
        'Low-Impact Aerobic Boxing Support',
    }

    assert expected_names.issubset(items)
    for name in expected_names:
        tags = set(items[name]['tags'])
        assert 'boxing' in tags
        assert 'repeatability' in tags


def test_boxing_coordination_under_fatigue_drills_exist_in_coordination_bank():
    data = json.loads(COORD_BANK.read_text(encoding='utf-8'))
    bucket = data['pressure_fighter_coordination_drills']
    items = {item['name']: item for item in bucket}

    expected_names = {
        'Stance Reset After Combination',
        'Footwork + Punch + Defensive Exit',
        'Punch Accuracy Under Mild Fatigue',
        'Controlled Density Posture Rounds',
        'Burst-Reset-Burst Drill',
    }

    assert expected_names.issubset(items)
    for name in expected_names:
        tags = set(items[name]['tags'])
        assert 'boxing' in tags
        assert 'coordination' in tags
