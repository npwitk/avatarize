"""Reads and edits AvatarKit avatar descriptors with simple `key=value` assignments.

Allowed values come from the catalog of the Mac this runs on (see bridge.catalog),
so nothing Apple ships is copied into this repo.

Assignment keys:
  <category>=<preset id>          e.g. hair=curly_long_upDo_fringe
  <category>.color=<color name>   e.g. hair.color=Auburn       (also .color2 / .color3)
  <category>.shade=<-1..1>        lighter/darker shade of the main color, e.g. head.shade=0.3
"""

from __future__ import annotations

import copy
import difflib
import json
import tempfile
from pathlib import Path

from . import bridge

COLOR_KEYS = ("colors", "secondaryColors", "tertiaryColors")
COLOR_SLOTS = {"color": 0, "color2": 1, "color3": 2}


class AssignmentError(ValueError):
    pass


def _match(value: str, options: list[dict], key: str, what: str) -> str:
    """Exact id/name, else a case-insensitive match on id or label. Raises with suggestions."""
    ids = [o[key] for o in options]
    if value in ids:
        return value
    lowered = value.casefold()
    for o in options:
        if lowered in (o[key].casefold(), o["label"].casefold()):
            return o[key]
    if not ids:
        raise AssignmentError(f"{what} has no options")
    close = difflib.get_close_matches(value, ids, n=5, cutoff=0.4)
    hint = f" Did you mean: {', '.join(close)}?" if close else ""
    raise AssignmentError(f"{value!r} is not a valid {what}.{hint} See `avatarize options {what.split()[0]}`.")


def resolve_category(name: str, catalog: dict) -> str:
    if name in catalog:
        return name
    close = difflib.get_close_matches(name, list(catalog), n=3)
    hint = f" Did you mean: {', '.join(close)}?" if close else ""
    raise AssignmentError(f"Unknown category {name!r}.{hint} See `avatarize options`.")


def apply(desc: dict, assignments: list[str], catalog: dict) -> dict:
    """Returns a copy of desc with every `key=value` assignment applied, or raises AssignmentError."""
    desc = copy.deepcopy(desc)
    for assignment in assignments:
        key, sep, value = assignment.partition("=")
        if not sep or not key or not value:
            raise AssignmentError(f"Expected key=value, got {assignment!r}")
        category, _, field = key.strip().partition(".")
        category = resolve_category(category, catalog)
        value = value.strip()
        if not field:
            desc["presets"][category] = _match(value, catalog[category]["presets"], "id", f"{category} preset")
        elif field in COLOR_SLOTS:
            slot = COLOR_SLOTS[field]
            name = _match(value, catalog[category]["colors"][slot], "name", f"{category} {field}")
            entry = desc.setdefault(COLOR_KEYS[slot], {}).get(category, {})
            desc[COLOR_KEYS[slot]][category] = {"name": name, "variation": entry.get("variation", 0)}
        elif field in ("shade", "variation"):
            try:
                shade = max(-1.0, min(1.0, float(value)))
            except ValueError:
                raise AssignmentError(f"{key} must be a number from -1 (darker) to 1 (lighter), got {value!r}") from None
            if category not in desc.get("colors", {}):
                raise AssignmentError(f"Set {category}.color before {category}.shade")
            desc["colors"][category]["variation"] = shade
        else:
            raise AssignmentError(f"Unknown field {field!r} in {key!r}; use .color, .color2, .color3 or .shade")
    return desc


def summary(desc: dict) -> dict:
    """One entry per category: its preset plus any colors, e.g. {"hair": "bob (Auburn +0.3)"}."""
    out = {}
    for category in sorted({*desc.get("presets", {}), *desc.get("colors", {})}):
        parts = [desc.get("presets", {}).get(category, "-")]
        colors = [desc.get(k, {}).get(category) for k in COLOR_KEYS]
        shown = []
        for c in filter(None, colors):
            shade = c.get("variation", 0)
            shown.append(c["name"] + (f" {shade:+.2f}" if shade else ""))
        if shown:
            parts.append(f"({', '.join(shown)})")
        out[category] = " ".join(parts)
    return out


def rejected_fields(desc: dict) -> list[str]:
    """Fields AvatarKit did not accept. It replaces unknown values silently, so compare a round trip."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(desc, f)
    try:
        loaded = bridge.normalize(Path(f.name))
    finally:
        Path(f.name).unlink()
    bad = [f"presets.{k}={v!r}" for k, v in desc["presets"].items() if loaded["presets"].get(k) != v]
    # Colors are checked against the catalog instead: AvatarKit legitimately drops or swaps
    # colors an item doesn't use (e.g. a beret forces its own badge color).
    catalog = bridge.catalog()
    for slot, key in enumerate(COLOR_KEYS):
        for k, v in desc.get(key, {}).items():
            names = {c["name"] for c in catalog.get(k, {}).get("colors", [[], [], []])[slot]}
            if v["name"] not in names:
                bad.append(f"{key}.{k}={v['name']!r}")
    return bad
