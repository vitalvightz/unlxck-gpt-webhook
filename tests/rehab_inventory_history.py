"""Historical rollout assertions include archived IDs, never current selection."""
import json
from pathlib import Path

from tools.consolidate_rehab_exact_duplicates import reconstruct_original


def inventory_with_history():
    data = Path(__file__).resolve().parents[1] / 'data'
    bank, ledger, archive = [json.loads((data / name).read_text(encoding='utf-8')) for name in
        ['rehab_bank.json', 'rehab_metadata_review.json', 'rehab_archive/exact_duplicates.json']]
    from tools.rehab_metadata_review_lib import before_restore_expansion
    bank = before_restore_expansion('rehab_bank.json', bank)
    ledger = before_restore_expansion('rehab_metadata_review.json', ledger)
    return reconstruct_original(bank, ledger, archive)


def historical_policies(tmp_path, bank):
    """Policies exactly as composed before the RESTORE expansion, for dated audits."""
    from fightcamp.rehab_clinical import load_clinical_policies
    from tools.rehab_metadata_review_lib import before_restore_expansion
    path = Path(__file__).resolve().parents[1] / 'data' / 'rehab_pathways.json'
    raw = before_restore_expansion('rehab_pathways.json', json.loads(path.read_text(encoding='utf-8')))
    target = tmp_path / 'pre_restore_expansion_pathways.json'
    target.write_text(json.dumps(raw), encoding='utf-8')
    return load_clinical_policies(target, bank=bank)


def pre_restore_expansion_bytes(name):
    """Dated seed input/output: data exactly as it was before the RESTORE expansion."""
    from tools.rehab_metadata_review_lib import before_restore_expansion
    path = Path(__file__).resolve().parents[1] / 'data' / name
    raw = before_restore_expansion(name, json.loads(path.read_text(encoding='utf-8')))
    return (json.dumps(raw, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
