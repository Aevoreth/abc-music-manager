#!/usr/bin/env python3
"""
Build cross-platform app icons from the source logo (ICO, ICNS, PNG sizes).

Requires: pip install pillow

Run from repo root: python scripts/generate_icons.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "files" / "ABC Music Manager Logo.png"
OUT_DIR = REPO_ROOT / "resources" / "icons"

ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
PNG_SIZES = [ic for ic in ICO_SIZES] + [(512, 512)]


def _remove_near_black(im: Image.Image, threshold: int) -> Image.Image:
    """Make near-black pixels transparent (logo is on a flat dark background)."""
    im = im.convert("RGBA")
    buf = bytearray(im.tobytes())
    for i in range(0, len(buf), 4):
        r, g, b = buf[i], buf[i + 1], buf[i + 2]
        if r <= threshold and g <= threshold and b <= threshold:
            buf[i + 3] = 0
    return Image.frombytes("RGBA", im.size, bytes(buf))


def _resize_high_quality(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    if im.size == size:
        return im.copy()
    return im.resize(size, Image.Resampling.LANCZOS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Source PNG (default: files/ABC Music Manager Logo.png)",
    )
    parser.add_argument(
        "--no-remove-black",
        action="store_true",
        help="Keep black/dark background pixels opaque",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=35,
        help="RGB max channel value treated as background when removing black",
    )
    args = parser.parse_args()

    if not args.source.is_file():
        raise SystemExit(f"Source not found: {args.source}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    base = Image.open(args.source)
    base = base.convert("RGBA")
    if not args.no_remove_black:
        base = _remove_near_black(base, args.threshold)

    # Master square for scaling (logo is already square)
    master = base
    if master.size[0] != master.size[1]:
        w, h = master.size
        side = max(w, h)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(master, ((side - w) // 2, (side - h) // 2))
        master = canvas

    # Multi-size ICO (Windows exe + Qt)
    ico_images = [_resize_high_quality(master, s) for s in ICO_SIZES]
    ico_path = OUT_DIR / "app.ico"
    ico_images[0].save(ico_path, format="ICO", append_images=ico_images[1:])

    # ICNS (macOS / PyInstaller on Darwin)
    icns_path = OUT_DIR / "app.icns"
    # Pillow picks embedded sizes from the image; use 512 or 1024 master for quality
    hi = _resize_high_quality(master, (1024, 1024))
    hi.save(icns_path, format="ICNS")

    # Loose PNGs for Linux .desktop / manual use / future QIcon tuning
    for size in PNG_SIZES:
        img = _resize_high_quality(master, size)
        img.save(OUT_DIR / f"app_{size[0]}.png", format="PNG")

    print(f"Wrote {ico_path}, {icns_path}, and app_*.png under {OUT_DIR}")


if __name__ == "__main__":
    main()
