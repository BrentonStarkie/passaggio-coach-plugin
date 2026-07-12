# Voice types & the passaggio zone

The "zone" is the pitch band where this singer's register transition (secondo passaggio) is
worked. The analysis contrasts metrics **below / in / above** the zone, so getting the zone
roughly right matters more than precisely.

## Default zones (secondo passaggio, approximate, override-able)

| Voice | Zone of interest | Also note (primo) |
|---|---|---|
| Soprano | E5–F♯5 | primo ~E♭4 |
| Mezzo-soprano | D5–E5 | |
| Contralto | C♯5–D5 | |
| Tenor | D4–G4 | |
| Baritone | B3–E4 | |
| Bass | A3–D4 | |

These live in `scripts/passaggio/zones.py` (`VOICE_ZONES`). They are starting points — real
passaggi vary by ±a tone between singers and by vowel.

## How the zone is chosen (priority order)

`zones.resolve_zone()` picks, in order:

1. **`passaggio_override`** in config (`["D4","G4"]`) — an explicit manual zone. `source: override`.
2. **`voice_type`** in config → the table above. `source: voice_type`.
3. **Inferred from register events** — the default when neither is set. The zone is centred
   (±2 st) on the **median pitch of detected register events**, pooled across this take *and*
   prior analysed takes. `source: inferred`, `confidence: low` (1–2 events) → `medium` (≥3).
4. **Nominal fallback** — if there are no events at all, a ±2 st window on the middle of the
   sung range. `source: nominal`, `confidence: low`. Treat as a rough guess.

### This project's default: infer from takes
The configured default is **no fixed voice type** — the working zone emerges from where
register events actually cluster and sharpens over sessions. Consequences for coaching:

- On the **first** take with a clean crossing (no events), the zone will be `nominal`/`low` —
  say so, and lean on global metrics rather than in-vs-below contrasts.
- Once a few takes exist, inference locks onto the real seam. If the singer tells you their
  voice type, offer to set it (`library.py set-profile --voice-type …`) for a sharper zone from
  the start.
- You can always propose a manual override once you can see the cluster:
  `library.py set-profile --override E4 A4`.

## Caveats
- **Formants are unreliable above ~C5** (harmonics too sparse). `formants.segments[].reliable`
  is `false` there — don't give vowel-modification feedback from unreliable formants; fall back
  to tilt/energy metrics for high soprano work.
- One profile per takes folder (v1). Multiple singers → separate folders.
