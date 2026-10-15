"""Keep bank-authored drill explanations separate from a short coach cue."""
from collections import defaultdict
from copy import deepcopy
from functools import lru_cache
import json
import re

from .config import DATA_DIR


def _identity(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")


@lru_cache(maxsize=1)
def _bank_instructions():
    candidates = defaultdict(set)

    def visit(value):
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            description = value.get("description")
            if value.get("name") and isinstance(description, str) and description.strip():
                candidates[_identity(value["name"])].add(description.strip())
            for item in value.values():
                if isinstance(item, (dict, list)):
                    visit(item)

    for filename in ("conditioning_bank.json", "style_conditioning_bank.json",
                     "style_taper_conditioning.json", "technical_footwork_bank.json",
                     "coordination_bank.json"):
        path = DATA_DIR / filename
        if path.is_file():
            visit(json.loads(path.read_text(encoding="utf-8")))
    # Ambiguous bank variants must not borrow each other's instructions.
    return {key: next(iter(values)) for key, values in candidates.items() if len(values) == 1}


def exercise_instructions(assignment):
    explicit = assignment.get("execution_instructions") or assignment.get("description")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    return _bank_instructions().get(_identity(assignment.get("exercise_key") or assignment.get("name")))


def recover_execution_instructions(plan):
    """Recover descriptions for every saved card, including cards without a brief."""
    result = plan
    for wi, week in enumerate(plan.get("weeks") or []):
        for di, day in enumerate(week.get("days") or []):
            for si, session in enumerate(day.get("sessions") or []):
                for bi, block in enumerate(session.get("blocks") or []):
                    if block.get("execution_instructions") or block.get("athlete_change") or block.get("prescription_source") == "athlete":
                        continue
                    explanation = exercise_instructions({**block, "name": block.get("display_name")})
                    if explanation:
                        if result is plan:
                            result = deepcopy(plan)
                        result["weeks"][wi]["days"][di]["sessions"][si]["blocks"][bi]["execution_instructions"] = explanation
    return result
