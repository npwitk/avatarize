"""avatarize: build Memoji-style avatars from the command line and render them in any sticker pose."""

from __future__ import annotations

import argparse
import html
import json
import sys
from functools import cache
from pathlib import Path

from . import bridge, descriptor

LOOKS = Path(__file__).resolve().parent / "looks.json"

DEFAULT_POSE = "pleasant_neutral"

GUIDE = """\
avatarize builds an avatar as a small JSON file, then renders it in any sticker pose.
Every value is validated against what this Mac's AvatarKit supports.

Workflow (works the same for a person or an AI agent):

  1. Discover what can be set
       avatarize options                  list categories (hair, head, eyes, eyewear, outfit, ...)
       avatarize options hair             allowed presets and colors for one category, with what each one looks like
       avatarize poses                    list poses (thumbs_up, person_waving, yearbook, ...)
     Add --json to any of these for machine-readable output.

  2. Create and edit an avatar
       avatarize new alex.json
       avatarize set alex.json hair=curly_long_upDo_fringe hair.color=Auburn hair.shade=0.3
       avatarize set alex.json head.color="Fitzpatrick 2" eyes.color=Green eyewear=rectangle eyewear.color=Black
     Keys:  <category>=<preset>   <category>.color=<name> (.color2 / .color3)   <category>.shade=<-1..1>
     shade is darker (-1) to lighter (1), except head.shade, which shifts skin undertone (golden to rosy).
     Values match an id, or a description from `options` (case-insensitive). Bad values fail with suggestions.

  3. Check and render
       avatarize show alex.json           current choices
       avatarize check alex.json          confirms AvatarKit accepts every value (exit 1 if not)
       avatarize render alex.json                             default pose -> alex-pleasant_neutral.png
       avatarize render alex.json --pose thumbs_up --pose yearbook --out renders/
       avatarize render alex.json --all-poses --out renders/
       avatarize sheet renders/           HTML page showing every rendered PNG

Matching a photo: look at the photo, then set at least: age, head (+ head.color for skin tone, head.shade),
hair (+ hair.color, hair.shade), eyebrows (+ color), eyes (+ eyes.color), nose, lips, facialhair, eyewear,
headwear, earrings_left/right, outfit (+ outfit.color). In `options`, the `# ...` line explains how a
category's ids are built and the `looks:` notes describe each rendered preset and color, so choose from
those instead of the names alone (several names mislead, e.g. hair.color=Golden Brown is ginger). Then render
the default pose, compare with the photo, and adjust with `set` only where it still differs.

Renders are square transparent PNGs, trimmed to the avatar and centered, so nothing is clipped.
"""


def _load(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"error: {path} does not exist. Create it with `avatarize new {path}`.")
    return json.loads(path.read_text())


def _save(path: Path, desc: dict) -> None:
    path.write_text(json.dumps(desc, indent=2, sort_keys=True) + "\n")


def _print_summary(desc: dict) -> None:
    for category, value in descriptor.summary(desc).items():
        print(f"{category:<22} {value}")


def cmd_guide(args) -> int:
    print(GUIDE)
    return 0


@cache
def looks() -> dict:
    """What presets and colors actually look like, written from renders (scripts/render_catalog.py).

    {category: {"about": str, "presets": {id: str}, "colors": {name: str}}}; any part may be missing.
    """
    return json.loads(LOOKS.read_text()) if LOOKS.exists() else {}


def cmd_options(args) -> int:
    catalog = bridge.catalog()
    if not args.category:
        if args.json:
            print(json.dumps(sorted(catalog)))
        else:
            for name, entry in sorted(catalog.items()):
                colors = sum(1 for slot in entry["colors"] if slot)
                print(f"{name:<22} {len(entry['presets']):>3} presets  {colors} color slot(s)")
        return 0
    try:
        category = descriptor.resolve_category(args.category, catalog)
    except descriptor.AssignmentError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    entry = catalog[category]
    # Left/right pairs share one set of descriptions, written for the left side.
    notes = looks().get(category) or looks().get(category.replace("_right", "_left"), {})
    preset_looks, color_looks = notes.get("presets", {}), notes.get("colors", {})
    if args.json:
        entry = {
            **entry,
            "about": notes.get("about", ""),
            "presets": [{**p, "looks": preset_looks.get(p["id"], "")} for p in entry["presets"]],
            "colors": [[{**c, "looks": color_looks.get(c["name"], "")} for c in slot] for slot in entry["colors"]],
        }
        print(json.dumps(entry, indent=2))
        return 0
    if notes.get("about"):
        print(f"# {notes['about']}")
    for p in entry["presets"]:
        look = preset_looks.get(p["id"])
        print(f"{category}={p['id']:<45} {p['label']}" + (f" | looks: {look}" if look else ""))
    for field, slot in descriptor.COLOR_SLOTS.items():
        for c in entry["colors"][slot]:
            look = color_looks.get(c["name"]) if slot == 0 else None
            print(f"{category}.{field}={c['name']:<37} {c['label']}" + (f" | looks: {look}" if look else ""))
    return 0


def cmd_poses(args) -> int:
    poses = bridge.poses()
    if args.search:
        needle = args.search.casefold()
        poses = [p for p in poses if needle in p["name"].casefold() or needle in p["label"].casefold()]
    if args.json:
        print(json.dumps(poses, indent=2, ensure_ascii=False))
    else:
        for p in poses:
            print(f"{p['emoji'] or ' ':<2} {p['name']:<50} {p['label']}")
    return 0


def cmd_new(args) -> int:
    if args.file.exists() and not args.force:
        print(f"error: {args.file} already exists (use --force to replace it)", file=sys.stderr)
        return 1
    desc = descriptor.apply(bridge.neutral(), args.assignments, bridge.catalog())
    _save(args.file, desc)
    print(f"created {args.file}")
    return 0


def cmd_set(args) -> int:
    desc = descriptor.apply(_load(args.file), args.assignments, bridge.catalog())
    _save(args.file, desc)
    touched = {a.partition("=")[0].partition(".")[0] for a in args.assignments}
    for category, value in descriptor.summary(desc).items():
        if category in touched:
            print(f"{category:<22} {value}")
    return 0


def cmd_show(args) -> int:
    desc = _load(args.file)
    if args.json:
        print(json.dumps(descriptor.summary(desc), indent=2))
    else:
        _print_summary(desc)
    return 0


def cmd_check(args) -> int:
    rejected = descriptor.rejected_fields(_load(args.file))
    if args.json:
        print(json.dumps({"ok": not rejected, "rejected": rejected}))
    elif rejected:
        print("AvatarKit rejected: " + ", ".join(rejected))
    else:
        print("ok")
    return 1 if rejected else 0


def cmd_render(args) -> int:
    known = {p["name"] for p in bridge.poses()}
    poses = sorted(known) if args.all_poses else (args.pose or [DEFAULT_POSE])
    unknown = [p for p in poses if p not in known]
    if unknown:
        print(f"error: unknown pose(s): {', '.join(unknown)}. See `avatarize poses`.", file=sys.stderr)
        return 2
    _load(args.file)
    if args.output:
        if len(poses) != 1:
            print("error: -o/--output takes a single pose; use --out DIR for several", file=sys.stderr)
            return 2
        outputs = {poses[0]: args.output}
    else:
        out_dir = args.out or args.file.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        outputs = {pose: out_dir / f"{args.file.stem}-{pose}.png" for pose in poses}
    bridge.render(args.file, outputs, args.size, args.margin)
    for path in outputs.values():
        print(path)
    return 0


def cmd_sheet(args) -> int:
    pngs = sorted(args.folder.glob("*.png"))
    cards = "".join(
        f'<figure><img src="{html.escape(p.name)}" alt="{html.escape(p.stem)}"><figcaption>{html.escape(p.stem)}</figcaption></figure>'
        for p in pngs
    )
    sheet = args.folder / "index.html"
    sheet.write_text(f"""<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Avatar sheet</title>
<style>
:root {{ --bg:#f6f6f7; --card:#fff; --text:#1d1d1f; --muted:#6e6e73; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#1c1c1e; --card:#2c2c2e; --text:#f5f5f7; --muted:#a1a1a6; }} }}
body {{ margin:0; padding:24px 16px; background:var(--bg); color:var(--text); font:14px/1.4 -apple-system,system-ui,sans-serif; }}
h1 {{ font-size:20px; margin:0 0 16px; }}
main {{ display:grid; gap:12px; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); }}
figure {{ margin:0; background:var(--card); border-radius:12px; padding:8px; }}
img {{ width:100%; aspect-ratio:1; object-fit:contain; }}
figcaption {{ color:var(--muted); font-size:12px; text-align:center; overflow-wrap:anywhere; }}
</style>
<h1>{len(pngs)} renders</h1>
<main>{cards}</main>
""")
    print(sheet)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="avatarize",
        description=__doc__,
        epilog="Run `avatarize guide` for the full workflow.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("guide", help="how to use avatarize, step by step (start here)").set_defaults(func=cmd_guide)

    p = sub.add_parser("options", help="list categories, or the allowed values for one category")
    p.add_argument("category", nargs="?")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_options)

    p = sub.add_parser("poses", help="list sticker poses (thumbs_up, person_waving, ...)")
    p.add_argument("--search", help="filter by name or description, e.g. --search thumb")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_poses)

    p = sub.add_parser("new", help="create an avatar file from the neutral avatar, optionally with key=value settings")
    p.add_argument("file", type=Path)
    p.add_argument("assignments", nargs="*", metavar="key=value")
    p.add_argument("--force", action="store_true", help="replace an existing file")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("set", help="change features: hair=<preset> hair.color=<name> hair.shade=<-1..1>")
    p.add_argument("file", type=Path)
    p.add_argument("assignments", nargs="+", metavar="key=value")
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("show", help="print an avatar's current choices")
    p.add_argument("file", type=Path)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("check", help="confirm AvatarKit accepts every value (exit 1 if not)")
    p.add_argument("file", type=Path)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("render", help="render square, uncropped PNGs in one or more poses")
    p.add_argument("file", type=Path)
    p.add_argument("--pose", action="append", help=f"pose name, repeatable (default: {DEFAULT_POSE})")
    p.add_argument("--all-poses", action="store_true", help="render every pose")
    p.add_argument("--out", type=Path, help="output folder (default: next to the avatar file)")
    p.add_argument("-o", "--output", type=Path, help="exact output path, for a single pose")
    p.add_argument("--size", type=int, default=512, help="PNG width and height in pixels (default: 512)")
    p.add_argument("--margin", type=float, default=0.04, help="empty border as a fraction of the size (default: 0.04)")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("sheet", help="write an HTML page showing every PNG in a folder")
    p.add_argument("folder", type=Path)
    p.set_defaults(func=cmd_sheet)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except descriptor.AssignmentError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except bridge.BridgeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
