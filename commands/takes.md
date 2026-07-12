---
description: List, tag, annotate, and configure takes in your passaggio library.
argument-hint: "[list | get <id> | tag <id> <tag> | set-voice <type>]"
---

Run the **passaggio-coach** skill's `/takes` workflow to manage the take library via
`library.py`.

Requested action: **$ARGUMENTS** (default: `list`).

- `list` → show every take: id, date, tags, status, and headline metrics.
- `get <id>` → one take's details and artifact paths (metrics.json, plots, session notes).
- `tag <id> <tag>` / notes → `library.py annotate …` to record the exercise/vowel/how it felt.
- `set-voice <type>` or a manual zone → `library.py set-profile --voice-type …` /
  `--override <low> <high>` (see `references/voice-types.md`).

If no takes folder is configured yet, offer to set one up (`library.py init --takes-dir …`).
