from __future__ import annotations

import base64
import io
import json
import re
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path.cwd()
REQUESTED_SIZES = (24, 32, 48, 120)
APP_SIZES = (180, 192, 512)


def find_frontend() -> Path:
    candidates: list[tuple[int, int, Path]] = []
    for package_file in ROOT.rglob("package.json"):
        if any(part in {"node_modules", ".next", "dist", "build"} for part in package_file.parts):
            continue
        try:
            package = json.loads(package_file.read_text())
        except Exception:
            continue
        dependencies = {
            **package.get("dependencies", {}),
            **package.get("devDependencies", {}),
        }
        score = 0
        if "next" in dependencies:
            score += 100
        if (package_file.parent / "src" / "app").exists() or (package_file.parent / "app").exists():
            score += 20
        if (package_file.parent / "public").exists():
            score += 10
        candidates.append((score, len(package_file.parts), package_file.parent))

    if not candidates:
        raise RuntimeError("Could not identify the frontend package")

    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]


def root_page(frontend: Path) -> Path | None:
    candidates = (
        frontend / "src" / "app" / "page.tsx",
        frontend / "src" / "app" / "page.jsx",
        frontend / "src" / "app" / "page.js",
        frontend / "app" / "page.tsx",
        frontend / "app" / "page.jsx",
        frontend / "app" / "page.js",
        frontend / "src" / "pages" / "index.tsx",
        frontend / "src" / "pages" / "index.jsx",
        frontend / "src" / "pages" / "index.js",
        frontend / "pages" / "index.tsx",
        frontend / "pages" / "index.jsx",
        frontend / "pages" / "index.js",
    )
    return next((candidate for candidate in candidates if candidate.exists()), None)


def app_directory(frontend: Path) -> Path | None:
    candidates = (frontend / "src" / "app", frontend / "app")
    return next((candidate for candidate in candidates if candidate.exists()), None)


def resolve_public_reference(frontend: Path, reference: str) -> Path | None:
    if not reference.startswith("/"):
        return None
    candidate = frontend / "public" / reference.lstrip("/")
    return candidate if candidate.exists() else None


def image_references(text: str) -> list[str]:
    matches = re.findall(
        r"[\"']([^\"']*(?:unlxck|logo|brand|mark|icon)[^\"']*\.(?:png|webp|jpg|jpeg|svg))[\"']",
        text,
        flags=re.IGNORECASE,
    )
    return list(dict.fromkeys(matches))


def imported_files(page: Path, frontend: Path) -> list[Path]:
    text = page.read_text(errors="ignore")
    imports = re.findall(r"from\s+[\"']([^\"']+)[\"']", text)
    files: list[Path] = []
    for imported in imports:
        if imported.startswith("@/"):
            base = frontend / "src" / imported[2:]
        elif imported.startswith("./") or imported.startswith("../"):
            base = (page.parent / imported).resolve()
        else:
            continue
        for candidate in (
            base,
            base.with_suffix(".tsx"),
            base.with_suffix(".jsx"),
            base.with_suffix(".ts"),
            base.with_suffix(".js"),
            base / "index.tsx",
            base / "index.jsx",
            base / "index.ts",
            base / "index.js",
        ):
            if candidate.exists() and candidate.is_file():
                files.append(candidate)
                break
    return files


def load_image(path: Path) -> Image.Image | None:
    try:
        if path.suffix.lower() == ".svg":
            try:
                import cairosvg
            except ImportError:
                return None
            png = cairosvg.svg2png(bytestring=path.read_bytes(), output_width=1024)
            return Image.open(io.BytesIO(png)).convert("RGBA")
        return Image.open(path).convert("RGBA")
    except Exception:
        return None


def source_candidates(frontend: Path, page: Path | None) -> list[Path]:
    candidates: list[Path] = []

    # Prefer the mark already used by the public landing surface.
    if page:
        related = [page, *imported_files(page, frontend)]
        for source_file in related:
            text = source_file.read_text(errors="ignore")
            for reference in image_references(text):
                resolved = resolve_public_reference(frontend, reference)
                if resolved:
                    candidates.append(resolved)
                else:
                    local = (source_file.parent / reference).resolve()
                    if local.exists():
                        candidates.append(local)

    app_dir = app_directory(frontend)
    if app_dir:
        for name in ("icon.png", "icon.jpg", "icon.jpeg", "icon.svg", "apple-icon.png"):
            candidate = app_dir / name
            if candidate.exists():
                candidates.append(candidate)

    for relative in (
        "public/unlxck-logo.png",
        "public/unlxck-logo.svg",
        "public/logo.png",
        "public/logo.svg",
        "public/brand/logo.png",
        "public/brand/logo.svg",
        "public/icon.png",
    ):
        candidate = frontend / relative
        if candidate.exists():
            candidates.append(candidate)

    for extension in ("*.png", "*.webp", "*.jpg", "*.jpeg", "*.svg"):
        for candidate in frontend.rglob(extension):
            if any(part in {"node_modules", ".next", "dist", "build"} for part in candidate.parts):
                continue
            lowered = candidate.name.lower()
            if any(token in lowered for token in ("unlxck", "logo", "brand", "mark", "icon")):
                candidates.append(candidate)

    return list(dict.fromkeys(candidates))


def candidate_score(path: Path, image: Image.Image, preferred: set[Path]) -> float:
    width, height = image.size
    name = path.name.lower()
    score = 0.0
    if path in preferred:
        score += 1000
    if "unlxck" in name:
        score += 250
    if "logo" in name or "mark" in name:
        score += 120
    if "icon" in name:
        score += 80
    if max(width, height) >= 256:
        score += 50
    if height >= width:
        score += 35
    if height > 0:
        ratio = width / height
        if 0.35 <= ratio <= 0.95:
            score += 35
    if min(width, height) <= 48:
        score -= 100
    return score


def choose_source(frontend: Path, page: Path | None) -> tuple[Path, Image.Image]:
    candidates = source_candidates(frontend, page)
    preferred = set(candidates[:8])
    scored: list[tuple[float, Path, Image.Image]] = []
    for candidate in candidates:
        image = load_image(candidate)
        if image is None:
            continue
        scored.append((candidate_score(candidate, image, preferred), candidate, image))

    if not scored:
        raise RuntimeError("Could not find an existing UNLXCK mark to use as the geometry source")

    scored.sort(key=lambda item: item[0], reverse=True)
    _, source_path, source_image = scored[0]
    print(f"Using source logo: {source_path.relative_to(ROOT)}")
    return source_path, source_image


def extract_alpha(image: Image.Image) -> Image.Image:
    red, green, blue, existing_alpha = image.split()
    alpha_extrema = existing_alpha.getextrema()

    if alpha_extrema[0] < 250:
        alpha = existing_alpha
    else:
        luminance = ImageChops.lighter(ImageChops.lighter(red, green), blue)
        border_values: list[int] = []
        width, height = luminance.size
        sample = max(1, min(width, height) // 50)
        border_values.extend(luminance.crop((0, 0, width, sample)).getdata())
        border_values.extend(luminance.crop((0, height - sample, width, height)).getdata())
        border_values.extend(luminance.crop((0, 0, sample, height)).getdata())
        border_values.extend(luminance.crop((width - sample, 0, width, height)).getdata())
        border_average = sum(border_values) / max(1, len(border_values))

        if border_average < 128:
            # White logo on a dark background.
            alpha = luminance.point(lambda value: 0 if value <= 8 else 255 if value >= 245 else round((value - 8) * 255 / 237))
        else:
            # Dark logo on a light background.
            alpha = luminance.point(lambda value: 255 if value <= 10 else 0 if value >= 247 else round((247 - value) * 255 / 237))

    bounding_box = alpha.getbbox()
    if not bounding_box:
        raise RuntimeError("The selected logo source contains no visible mark")
    return alpha.crop(bounding_box)


def widen_exactly_ten_percent(alpha: Image.Image) -> Image.Image:
    return alpha.resize((round(alpha.width * 1.10), alpha.height), Image.Resampling.LANCZOS)


def render_square(alpha: Image.Image, size: int, occupancy: float = 0.86) -> Image.Image:
    target_height = max(1, round(size * occupancy))
    scale = target_height / alpha.height
    target_width = max(1, round(alpha.width * scale))
    resized_alpha = alpha.resize((target_width, target_height), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mark = Image.new("RGBA", resized_alpha.size, (255, 255, 255, 255))
    mark.putalpha(resized_alpha)
    canvas.alpha_composite(mark, ((size - target_width) // 2, (size - target_height) // 2))
    return canvas


def write_assets(frontend: Path, widened_alpha: Image.Image) -> dict[int, Path]:
    brand_directory = frontend / "public" / "brand"
    brand_directory.mkdir(parents=True, exist_ok=True)
    outputs: dict[int, Path] = {}
    for size in (*REQUESTED_SIZES, *APP_SIZES):
        output = brand_directory / f"unlxck-one-angle-{size}.png"
        render_square(widened_alpha, size).save(output, "PNG", optimize=True)
        outputs[size] = output

    # Preserve a scalable copy with the exact same raster geometry embedded transparently.
    raw_mark = Image.new("RGBA", widened_alpha.size, (255, 255, 255, 255))
    raw_mark.putalpha(widened_alpha)
    buffer = io.BytesIO()
    raw_mark.save(buffer, "PNG", optimize=True)
    data = base64.b64encode(buffer.getvalue()).decode("ascii")
    (brand_directory / "unlxck-one-angle.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {widened_alpha.width} {widened_alpha.height}" role="img" aria-label="UNLXCK">\n'
        f'  <image width="{widened_alpha.width}" height="{widened_alpha.height}" href="data:image/png;base64,{data}"/>\n'
        '</svg>\n'
    )
    return outputs


def replace_app_icons(frontend: Path, assets: dict[int, Path], widened_alpha: Image.Image) -> list[Path]:
    changed: list[Path] = []
    public = frontend / "public"
    public.mkdir(parents=True, exist_ok=True)

    # Multi-size browser favicon based on the requested 24/32/48 assets.
    favicon = public / "favicon.ico"
    render_square(widened_alpha, 48).save(favicon, "ICO", sizes=[(24, 24), (32, 32), (48, 48)])
    changed.append(favicon)

    app_dir = app_directory(frontend)
    if app_dir:
        app_icon = app_dir / "icon.png"
        apple_icon = app_dir / "apple-icon.png"
        render_square(widened_alpha, 512).save(app_icon, "PNG", optimize=True)
        render_square(widened_alpha, 180).save(apple_icon, "PNG", optimize=True)
        changed.extend((app_icon, apple_icon))
    else:
        icon_192 = public / "icon-192.png"
        icon_512 = public / "icon-512.png"
        render_square(widened_alpha, 192).save(icon_192, "PNG", optimize=True)
        render_square(widened_alpha, 512).save(icon_512, "PNG", optimize=True)
        changed.extend((icon_192, icon_512))

    for manifest in (public / "manifest.json", public / "manifest.webmanifest"):
        if not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text())
        except Exception:
            continue
        data["icons"] = [
            {
                "src": "/brand/unlxck-one-angle-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": "/brand/unlxck-one-angle-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
        ]
        manifest.write_text(json.dumps(data, indent=2) + "\n")
        changed.append(manifest)
        break

    return changed


def replace_logo_string(path: Path) -> bool:
    text = path.read_text(errors="ignore")
    pattern = re.compile(
        r"([\"'])([^\"']*(?:unlxck|logo|brand|mark|icon)[^\"']*\.(?:png|webp|jpg|jpeg|svg))\1",
        flags=re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return False
    replacement = '"/brand/unlxck-one-angle-120.png"'
    path.write_text(text[: match.start()] + replacement + text[match.end() :])
    return True


def update_landing_page(frontend: Path, page: Path | None) -> Path:
    if page is None:
        raise RuntimeError("Could not find the root landing page")

    # First update the concrete logo reference on the page itself.
    if replace_logo_string(page):
        return page

    # Then inspect components imported by the landing page, prioritising brand-like names.
    imports = imported_files(page, frontend)
    imports.sort(
        key=lambda path: (
            0 if any(token in path.name.lower() for token in ("logo", "brand", "mark", "header", "nav")) else 1,
            len(path.parts),
        )
    )
    for imported in imports:
        if replace_logo_string(imported):
            return imported

    # If the existing mark is an inline Logo/BrandMark component, replace that component call.
    text = page.read_text(errors="ignore")
    component_match = re.search(r"<(?:Logo|BrandLogo|BrandMark|UnlxckLogo)\b[^>]*/>", text)
    if component_match:
        replacement = (
            '<img src="/brand/unlxck-one-angle-120.png" alt="UNLXCK" '
            'width={120} height={120} className="h-12 w-auto" />'
        )
        page.write_text(text[: component_match.start()] + replacement + text[component_match.end() :])
        return page

    # Safe fallback: add the mark once at the beginning of the landing page main element.
    main_match = re.search(r"<main(?P<attributes>[^>]*)>", text)
    if not main_match:
        raise RuntimeError("No safe landing-page logo replacement point was found")
    insertion = (
        '\n        <img\n'
        '          src="/brand/unlxck-one-angle-120.png"\n'
        '          alt="UNLXCK"\n'
        '          width={120}\n'
        '          height={120}\n'
        '          className="h-12 w-auto"\n'
        '        />'
    )
    page.write_text(text[: main_match.end()] + insertion + text[main_match.end() :])
    return page


def update_metadata_references(frontend: Path) -> list[Path]:
    changed: list[Path] = []
    app_dir = app_directory(frontend)
    if not app_dir:
        return changed

    for name in ("layout.tsx", "layout.jsx", "layout.js", "metadata.ts", "metadata.js"):
        path = app_dir / name
        if not path.exists():
            continue
        text = path.read_text(errors="ignore")
        updated = re.sub(
            r"([\"'])/[^\"']*(?:favicon|app-icon|logo|icon)[^\"']*\.(?:png|ico|svg)\1",
            '"/brand/unlxck-one-angle-48.png"',
            text,
            flags=re.IGNORECASE,
        )
        if updated != text:
            path.write_text(updated)
            changed.append(path)
    return changed


def main() -> None:
    frontend = find_frontend()
    page = root_page(frontend)
    source_path, source_image = choose_source(frontend, page)
    alpha = extract_alpha(source_image)
    widened_alpha = widen_exactly_ten_percent(alpha)

    assets = write_assets(frontend, widened_alpha)
    app_changes = replace_app_icons(frontend, assets, widened_alpha)
    landing_change = update_landing_page(frontend, page)
    metadata_changes = update_metadata_references(frontend)

    print("Saved requested icon sizes:")
    for size in REQUESTED_SIZES:
        print(f"- {assets[size].relative_to(ROOT)}")
    print("App icon changes:")
    for path in app_changes:
        print(f"- {path.relative_to(ROOT)}")
    print(f"Landing-page change: {landing_change.relative_to(ROOT)}")
    for path in metadata_changes:
        print(f"Metadata change: {path.relative_to(ROOT)}")
    print(f"Geometry source: {source_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
