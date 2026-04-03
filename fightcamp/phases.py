from __future__ import annotations

import re
from enum import Enum

try:
    from enum import StrEnum
except ImportError:  # pragma: no cover - Python < 3.11 fallback
    class StrEnum(str, Enum):
        pass


class PhaseEnum(StrEnum):
    GPP = "GPP"
    SPP = "SPP"
    TAPER = "TAPER"


PHASE_VALUES = tuple(phase.value for phase in PhaseEnum)
PHASE_REBALANCE_ORDER = (
    PhaseEnum.TAPER.value,
    PhaseEnum.GPP.value,
    PhaseEnum.SPP.value,
)
PHASE_HEADER_PATTERN = re.compile(
    rf"\b(?:{'|'.join(re.escape(phase) for phase in PHASE_VALUES)})\b",
    re.IGNORECASE,
)
