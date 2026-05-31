"""Dependency-free process memory readout for the /health endpoint.

Render runs on Linux, so we read /proc/self/statm for current RSS and fall
back to resource.getrusage for peak RSS. No third-party deps (psutil) are
required, so this is safe to import at request time on the 512MB instance.
"""
from __future__ import annotations

import os
import resource

_PAGE_SIZE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096


def _current_rss_bytes() -> int | None:
    """Resident set size right now, via /proc/self/statm (Linux). None if unavailable."""
    try:
        with open("/proc/self/statm", "r", encoding="ascii") as handle:
            fields = handle.read().split()
        # Field 1 (index 1) is resident pages.
        resident_pages = int(fields[1])
        return resident_pages * _PAGE_SIZE
    except (OSError, ValueError, IndexError):
        return None


def _peak_rss_bytes() -> int | None:
    """Peak RSS for this process. ru_maxrss is in KiB on Linux."""
    try:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    except (ValueError, OSError):
        return None


def memory_snapshot() -> dict[str, int | float | None]:
    """Small, cheap memory readout suitable for embedding in /health."""
    current = _current_rss_bytes()
    peak = _peak_rss_bytes()

    def _mb(value: int | None) -> float | None:
        return round(value / (1024 * 1024), 1) if value is not None else None

    return {
        "rss_mb": _mb(current),
        "peak_rss_mb": _mb(peak),
    }
