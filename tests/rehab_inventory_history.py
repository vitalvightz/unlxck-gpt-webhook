"""Historical rollout assertions include archived IDs, never current selection."""
import json
from pathlib import Path

from tools.consolidate_rehab_exact_duplicates import reconstruct_original


def inventory_with_history():
    data = Path(__file__).resolve().parents[1] / 'data'
    bank, ledger, archive = [json.loads((data / name).read_text(encoding='utf-8')) for name in
        ['rehab_bank.json', 'rehab_metadata_review.json', 'rehab_archive/exact_duplicates.json']]
    return reconstruct_original(bank, ledger, archive)
