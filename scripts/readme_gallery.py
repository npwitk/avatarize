"""Builds docs/gallery.png, the sample image in the README.

Generates random (but seeded, so repeatable) avatars with the CLI, renders each in a
different pose, and arranges them in a pyramid (the top half of a diamond) on a
transparent background. Run from
the repo root:

    uv run --with pillow scripts/readme_gallery.py [--seed N]
"""

from __future__ import annotations

import argparse
import random
import tempfile
from pathlib import Path

from PIL import Image

from avatarize import bridge, cli

SKIN = ["Extended 1", "Fitzpatrick 1", "Fitzpatrick 2", "Fitzpatrick 3", "Fitzpatrick 4", "Fitzpatrick 4.5", "Extended 2",
        "Fitzpatrick 5", "Extended 3"]  # fmt: skip
NATURAL_HAIR = ["Golden Blond", "Flaxen", "Maple", "Soft Black", "Black", "Golden Brown", "Auburn", "Red"]
FUN_HAIR = ["Blue", "Purple", "Pink", "Green", "Orange"]
EYES = ["Black", "Brown", "Green", "Blue", "Hazel", "Gray"]
PYRAMID_WIDTH = 11  # bottom row; rows run 1, 3, 5, ..., 11 = 36 avatars
CELL = 200  # rendered size of each avatar
GAP = 32  # empty space between neighboring avatars, in pixels
PADDING = 48  # transparent border around the whole arrangement, in pixels


def pick(rng: random.Random, catalog: dict, category: str, exclude: tuple[str, ...] = ("none",)) -> str:
    return rng.choice([p["id"] for p in catalog[category]["presets"] if p["id"] not in exclude])


def color(rng: random.Random, catalog: dict, category: str) -> str:
    return rng.choice([c["name"] for c in catalog[category]["colors"][0]])


def random_avatar(rng: random.Random, catalog: dict) -> list[str]:
    """Assignments for one plausible random person."""
    age = rng.choices(["child_50", "child_25", "adult", "olderAdult_25", "olderAdult_50", "olderAdult"], [1, 2, 8, 4, 2, 1])[0]
    older, child = age.startswith("olderAdult"), age.startswith("child")
    hair_color = "Gray" if older and rng.random() < 0.5 else rng.choice(FUN_HAIR if rng.random() < 0.1 else NATURAL_HAIR)
    a = [
        f"age={age}",
        f"head={pick(rng, catalog, 'head')}",
        f"head.color={rng.choice(SKIN)}",
        f"head.shade={rng.uniform(-0.3, 0.3):.2f}",
        f"hair={pick(rng, catalog, 'hair')}",
        f"hair.color={hair_color}",
        f"hair.shade={rng.uniform(-0.4, 0.4):.2f}",
        f"eyebrows={pick(rng, catalog, 'eyebrows')}",
        f"eyebrows.color={hair_color if hair_color in NATURAL_HAIR + ['Gray'] else 'Soft Black'}",
        f"eyes={pick(rng, catalog, 'eyes')}",
        f"eyes.color={rng.choice(EYES)}",
        f"nose={pick(rng, catalog, 'nose')}",
        f"lips={pick(rng, catalog, 'lips')}",
        f"outfit={pick(rng, catalog, 'outfit')}",
        f"outfit.color={color(rng, catalog, 'outfit')}",
    ]
    if not child and rng.random() < 0.3:
        a += [f"facialhair={pick(rng, catalog, 'facialhair')}", f"facialhair.color={hair_color}"]
    if rng.random() < 0.3:
        a += [f"eyewear={pick(rng, catalog, 'eyewear', ('none', 'monocle', 'monocle_wire', 'monocle_rimless'))}",
              f"eyewear.color={color(rng, catalog, 'eyewear')}"]  # fmt: skip
    if rng.random() < 0.15:
        a += [f"headwear={pick(rng, catalog, 'headwear')}", f"headwear.color={color(rng, catalog, 'headwear')}"]
    if rng.random() < 0.2:
        stud = pick(rng, catalog, "earrings_left")
        a += [f"earrings_left={stud}", f"earrings_right={stud}"]
    return a


def pyramid_positions() -> list[tuple[int, int]]:
    """Top-left corner of each cell, row by row from the top."""
    half = PYRAMID_WIDTH // 2
    rows = range(1, PYRAMID_WIDTH + 1, 2)
    step = CELL + GAP
    return [(round((half + j - (n - 1) / 2) * step), r * step) for r, n in enumerate(rows) for j in range(n)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    catalog = bridge.catalog()
    positions = pyramid_positions()
    # Every avatar gets a different pose: sticker poses first, then portrait poses if more are needed.
    stickers = [p["name"] for p in bridge.poses() if p["pack"] == "stickers"]
    portraits = [p["name"] for p in bridge.poses() if p["pack"] != "stickers"]
    extra = rng.sample(portraits, max(0, len(positions) - len(stickers)))
    poses = rng.sample(stickers + extra, len(positions))

    width = max(x for x, _ in positions) + CELL
    height = max(y for _, y in positions) + CELL
    sheet = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    out = Path("docs/gallery.png")
    out.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for i, ((x, y), pose) in enumerate(zip(positions, poses)):
            avatar, png = Path(tmp) / f"{i}.json", Path(tmp) / f"{i}.png"
            steps = (["new", str(avatar), *random_avatar(rng, catalog)], ["check", str(avatar)],
                     ["render", str(avatar), "--pose", pose, "-o", str(png), "--size", str(CELL)])  # fmt: skip
            for step in steps:
                if cli.main(step) != 0:
                    raise SystemExit(f"avatarize {step[0]} failed for avatar {i} ({pose})")
            sheet.alpha_composite(Image.open(png).convert("RGBA"), (x, y))
    # Crop to the avatars themselves, then add an even transparent border on every side.
    content = sheet.crop(sheet.getbbox())
    padded = Image.new("RGBA", (content.width + 2 * PADDING, content.height + 2 * PADDING), (0, 0, 0, 0))
    padded.alpha_composite(content, (PADDING, PADDING))
    padded.save(out, optimize=True)
    print(f"wrote {out} ({len(positions)} avatars, {out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
