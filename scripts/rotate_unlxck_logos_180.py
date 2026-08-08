from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "web" / "public"
CODEX_ASSETS = PUBLIC / "brand" / "unlxck-codex-icon-upgrade" / "assets"


def unique_existing(paths: Iterable[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        path = path.resolve()
        if path.exists() and path not in seen:
            seen.add(path)
            result.append(path)
    return sorted(result)


def targets() -> list[Path]:
    candidates: list[Path] = []

    # Live app/browser assets used by Next metadata, manifest and service worker.
    candidates.extend((PUBLIC / "brand").glob("unlxck-one-angle-*.png"))
    candidates.append(PUBLIC / "favicon.ico")

    # Legacy/conventional app icon set. The Settings / Download App panel still
    # renders /icons/icon-192x192.png, so keep this whole app-icon family aligned.
    candidates.extend((PUBLIC / "icons").glob("*.png"))

    # Supplied icon package. The landing page currently renders the 120px mark
    # from this package; rotate the production-ready app/maskable/brand variants
    # as a set so future copies do not silently restore the old orientation.
    for subdir in ("app", "maskable", "brand"):
        folder = CODEX_ASSETS / subdir
        if folder.exists():
            candidates.extend(folder.glob("*.png"))
            candidates.extend(folder.glob("*.ico"))

    return unique_existing(candidates)


def rotate_png(path: Path) -> tuple[tuple[int, int], str]:
    with Image.open(path) as image:
        image.load()
        original_mode = image.mode
        original_size = image.size
        original_pixels = image.tobytes()
        rotated = image.transpose(Image.Transpose.ROTATE_180)
        rotated.save(path, format="PNG", optimize=False)

    with Image.open(path) as check:
        check.load()
        if check.size != original_size:
            raise RuntimeError(f"dimension changed for {path}: {original_size} -> {check.size}")
        if check.mode != original_mode:
            # Palette PNGs can be normalized by Pillow on save; pixels and alpha
            # are the acceptance requirement, but report unexpected mode drift.
            print(f"warning: mode changed for {path}: {original_mode} -> {check.mode}")
        restored = check.transpose(Image.Transpose.ROTATE_180)
        if restored.tobytes() != original_pixels:
            raise RuntimeError(f"180-degree pixel round-trip failed for {path}")
    return original_size, original_mode


def rotate_ico(path: Path) -> tuple[tuple[int, int], str]:
    with Image.open(path) as image:
        image.load()
        original_size = image.size
        original_mode = image.mode
        original_rgba = image.convert("RGBA")
        original_pixels = original_rgba.tobytes()
        rotated = original_rgba.transpose(Image.Transpose.ROTATE_180)
        rotated.save(path, format="ICO", sizes=[original_size])

    with Image.open(path) as check:
        check.load()
        if check.size != original_size:
            raise RuntimeError(f"ICO dimension changed for {path}: {original_size} -> {check.size}")
        restored = check.convert("RGBA").transpose(Image.Transpose.ROTATE_180)
        if restored.tobytes() != original_pixels:
            raise RuntimeError(f"180-degree ICO pixel round-trip failed for {path}")
    return original_size, original_mode


def main() -> None:
    files = targets()
    if not files:
        raise RuntimeError("No UNLXCK logo/icon assets found")

    print(f"Rotating {len(files)} UNLXCK logo/icon assets exactly 180 degrees:")
    for path in files:
        relative = path.relative_to(ROOT)
        if path.suffix.lower() == ".png":
            size, mode = rotate_png(path)
        elif path.suffix.lower() == ".ico":
            size, mode = rotate_ico(path)
        else:
            raise RuntimeError(f"Unsupported target type: {path}")
        print(f"  {relative}  {size[0]}x{size[1]}  {mode}")

    print("Rotation complete; dimensions preserved and every asset passed a 180-degree pixel round-trip check.")


if __name__ == "__main__":
    main()
