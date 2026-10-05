"""Historical duplicate metadata, deliberately outside selectable rehab inventory."""
from copy import deepcopy
from functools import lru_cache
import json

from .config import DATA_DIR


@lru_cache(maxsize=1)
def _archived_drills():
    archive = json.loads((DATA_DIR / 'rehab_archive' / 'exact_duplicates.json').read_text(encoding='utf-8'))
    if archive.get('schema_version') != 1:
        raise ValueError('Unsupported rehab duplicate archive')
    index = {}
    for record in archive['records']:
        identifier = record['retired_id']
        drill = record['drill']
        if drill.get('id') != identifier or identifier in index:
            raise ValueError('Ambiguous historical rehab identity: ' + identifier)
        index[identifier] = drill
    return index


def archived_rehab_drill_by_id(identifier: str | None) -> dict | None:
    """Recover the original ID/content for historical evidence; never remap an ID.

    Selection and current-prescription callers must use the active bank lookup.
    A copy prevents completion annotations from mutating the archival source.
    """
    drill = _archived_drills().get(str(identifier or '').strip())
    return deepcopy(drill) if drill is not None else None
