from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
RENDER_BACKEND_URL = "https://unlxck-gpt-webhook.onrender.com"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import patterns that mean a test module exercises the spaCy/negspacy injury
# parser (which lazily loads the en_core_web_sm model). Tests touching any of
# these are auto-tagged with the `spacy` marker so the heavy lane can be
# selected/deselected with `-m spacy` / `-m "not spacy"` without hand-editing
# every test file.
_SPACY_IMPORT_HINTS = (
    "injury_synonyms",
    "injury_negation",
    "canonicalize_injury",
    "canonicalize_location",
    "structured_injury",
    "injury_triage",
    "negation_detection",
    "get_nlp",
)

# Cache the per-file decision so each module's source is read at most once.
_module_uses_spacy: dict[str, bool] = {}


def _file_uses_spacy(path: Path) -> bool:
    key = str(path)
    cached = _module_uses_spacy.get(key)
    if cached is not None:
        return cached
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        source = ""
    result = any(hint in source for hint in _SPACY_IMPORT_HINTS)
    _module_uses_spacy[key] = result
    return result


def pytest_collection_modifyitems(config, items):
    """Auto-apply the `spacy` marker to tests that hit the spaCy injury path."""
    for item in items:
        path = getattr(item, "path", None)
        if _file_uses_spacy(path):
            item.add_marker("spacy")


@pytest.fixture(scope="session")
def nlp():
    """Session-scoped spaCy pipeline, warmed once per (xdist) worker.

    The production code already memoizes the model in a module-level cache, so
    this fixture mostly exists to give spaCy-dependent tests a clean, explicit
    handle and to keep the (slow) load out of individual test timings.
    """
    from fightcamp.injury_synonyms import get_nlp

    nlp_obj = get_nlp()
    if nlp_obj is None:
        pytest.skip("spaCy or the en_core_web_sm model is not available")
    return nlp_obj
