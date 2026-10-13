# Notes for AI agents

`avatarize` is a plain CLI; it never calls an AI model. To build an avatar from a photo, you look at the photo and drive the CLI:

```sh
uv run avatarize guide          # full workflow and key=value syntax
uv run avatarize options hair   # valid values, with descriptions
uv run avatarize poses          # valid poses
```

Every value is validated against the Mac's AvatarKit, and bad values fail with suggestions, so explore with `options` instead of guessing. Claude Code users can also load the skill in `.claude/skills/avatarize/`.

Development: `uv run pytest` (macOS only) and `uv run ruff check . && uv run ruff format --check .`.
