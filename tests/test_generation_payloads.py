from api.generation.payloads import _stable_payload_hash


def test_stable_payload_hash_ignores_json_key_order():
    left = {
        "athlete": {"full_name": "Ari", "age": 27},
        "fight_date": "2099-04-18",
        "goals": ["strength", "conditioning"],
    }
    right = {
        "goals": ["strength", "conditioning"],
        "fight_date": "2099-04-18",
        "athlete": {"age": 27, "full_name": "Ari"},
    }

    assert _stable_payload_hash(left) == _stable_payload_hash(right)
