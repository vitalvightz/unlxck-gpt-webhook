from __future__ import annotations

from pathlib import Path

BANNED_MARKERS = {
    "Demo" + "AuthService",
    "Demo" + "Store",
    "demo" + "-admin",
    "demo" + "-athlete",
    "NEXT_PUBLIC_" + "DEMO_MODE",
    "UNLXCK_" + "DEMO_MODE",
    "UNLXCK_" + "DEV_AUTH_BYPASS",
    "signIn" + "Demo",
}

EXCLUDED_PARTS = {"node_modules", ".git", "__pycache__", ".next", ".app_data"}


def test_demo_auth_markers_removed_from_repo():
    root = Path(__file__).resolve().parents[1]
    hits: list[str] = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        if path == Path(__file__).resolve():
            continue
        if path.suffix in {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".lock"}:
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue

        for marker in BANNED_MARKERS:
            if marker in text:
                hits.append(f"{path.relative_to(root)}::{marker}")

    assert hits == [], "Demo auth markers found:\n" + "\n".join(sorted(hits))
