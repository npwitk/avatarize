"""Renders every preset of every category as labeled contact sheets, for writing avatarize/looks.json.

Each preset is shown on the same plain base avatar, front-on and three-quarter, so presets in a
category can be compared side by side. Run from the repo root:

    uv run --with pillow scripts/render_catalog.py [--out catalog/] [--only hair,head]
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from avatarize import bridge, descriptor

FACE_POSES = ["happy", "pleasant_neutral"]  # front-on, then three-quarter
BODY_POSES = ["hands_on_hips"]
BODY_CATEGORIES = {"armthickness", "chest", "shoulderwidth", "waist", "outfit"}
BASE = [
    "age=adult", "head=round_medium", "head.color=Fitzpatrick 2", "hair=none", "eyebrows=even_rounded_medium",
    "eyebrows.color=Black", "eyes.color=Brown", "facialhair.color=Black", "outfit=crewNeckTshirt", "outfit.color=White",
]  # fmt: skip
# Extra settings per category so its presets are visible: contrasting colors show which slot paints which part.
CONTEXT = {
    "hair": ["hair.color=Golden Brown"],
    "highlights": ["hair=straight_medium_down_sidePart", "hair.color=Black", "highlights.color=Golden Blond"],
    "headwear": [
        "hair=straight_short_down_sidePart",
        "hair.color=Black",
        "headwear.color=Blue",
        "headwear.color2=Red",
        "headwear.color3=Yellow",
    ],
    "outfit": ["outfit.color=Blue", "outfit.color2=Red", "outfit.color3=Yellow"],
    "eyewear": ["eyewear.color=Black"],
    "facewear": ["facewear.color=Blue"],
    "sideburns": ["hair=buzzed", "hair.color=Black", "sideburns.color=Black"],
    "facialhairhighlights": ["facialhair=basic_full", "facialhairhighlights.color=Golden Blond"],
    "eyelashes": ["eyelashes.color=Black"],
}
TILE = 220
COLUMNS = 6
PER_SHEET = 36
LABEL_H = 34


def tile(images: list[Path], label: str, font) -> Image.Image:
    cell = Image.new("RGBA", (TILE * len(images), TILE + LABEL_H), "white")
    for i, path in enumerate(images):
        cell.alpha_composite(Image.open(path).convert("RGBA").resize((TILE, TILE)), (i * TILE, 0))
    ImageDraw.Draw(cell).text((6, TILE + 6), label, fill="black", font=font)
    return cell


def sheets(cells: list[Image.Image], out: Path, name: str) -> list[Path]:
    paths = []
    for n, start in enumerate(range(0, len(cells), PER_SHEET)):
        chunk = cells[start : start + PER_SHEET]
        w, h = chunk[0].size
        cols = max(1, min(COLUMNS * TILE // w, len(chunk)))
        rows = -(-len(chunk) // cols)
        sheet = Image.new("RGB", (cols * w + (cols - 1) * 4, rows * h + (rows - 1) * 4), (200, 200, 200))
        for i, cell in enumerate(chunk):
            sheet.paste(cell, ((i % cols) * (w + 4), (i // cols) * (h + 4)), cell)
        path = out / f"{name}-{n + 1}.png"
        sheet.save(path)
        paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("catalog"))
    parser.add_argument("--only", help="comma-separated categories")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default(size=15)
    catalog = bridge.catalog()
    only = set(args.only.split(",")) if args.only else None
    base = descriptor.apply(bridge.neutral(), BASE, catalog)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for category in sorted(catalog):
            presets = catalog[category]["presets"]
            if not presets or category.endswith("_right") or (only and category not in only):
                continue
            poses = BODY_POSES if category in BODY_CATEGORIES else FACE_POSES
            start = descriptor.apply(base, CONTEXT.get(category, []), catalog)
            cells = []
            for p in presets:
                desc = descriptor.apply(start, [f"{category}={p['id']}"], catalog)
                if category.endswith("_left"):  # show the pair, so the ear facing the camera has it too
                    desc = descriptor.apply(desc, [f"{category[:-5]}_right={p['id']}"], catalog)
                src = tmp / "a.json"
                src.write_text(json.dumps(desc))
                outputs = {pose: tmp / f"{pose}.png" for pose in poses}
                bridge.render(src, outputs, 256, 0.04)
                cells.append(tile(list(outputs.values()), f"{category}={p['id']}", font))
            for path in sheets(cells, args.out, category):
                print(path)


if __name__ == "__main__":
    main()
