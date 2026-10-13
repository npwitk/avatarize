---
name: avatarize
description: Build a Memoji-style avatar that looks like a person in a photo, and render it as stickers (thumbs up, waving, ...) with the avatarize CLI. Use when asked to make an avatar, Memoji or sticker from a photo, or to render an existing avatar file in more poses.
---

# Making avatars with the avatarize CLI

The CLI does the work; you choose the values. Run `uv run avatarize guide` first, then follow it.

1. Look at the photo yourself (Read the image file).
2. For each feature, list the choices with `uv run avatarize options <category>`. Pick from those ids and names only; never invent values. Add `--json` if that's easier to parse.
3. `uv run avatarize new <name>.json` and then one or more `uv run avatarize set <name>.json key=value ...`. If a value is rejected, the error suggests close matches.
4. `uv run avatarize check <name>.json` must print `ok`.
5. `uv run avatarize render <name>.json --out renders/`, then Read the PNG and compare it with the photo. Adjust with `set` and re-render until hair, skin tone, glasses and facial hair match. Two or three rounds is usually enough.
6. Render the poses the user wants: `--pose thumbs_up --pose person_waving`. Use `uv run avatarize poses --search <word>` to find one.

For a folder of photos, repeat per photo with one JSON file each, then `uv run avatarize sheet renders/` for a review page.

Photos of people are personal data. Only process photos the user says they have consent to use.
