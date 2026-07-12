# Passaggio Coach — Plugin Specification

**Version:** 0.1 (draft)
**Date:** 2026-07-12
**Author:** Brenton Starkie (with Claude)
**Status:** Spec only — nothing built yet

---

## 1. Summary

A Claude plugin that analyses short vocal recordings (~20 s "takes") of passaggio work, gives targeted coaching feedback and exercises, supports interactive clarification, and tracks progress across takes over time.

**Why a plugin rather than a standalone skill:** a skill alone can analyse one uploaded WAV. The plugin adds (a) a connector to a watched "Takes" folder on the Mac so recordings flow in without manual upload, (b) a persistent take library so today's take can be compared with last week's, and (c) slash commands for a fast workflow. The skill remains the coaching brain; the plugin wraps it in plumbing and memory.

---

## 2. User workflow (target experience)

1. Singer records a take in Voice Memos (or any recorder) and saves/exports it to the **Takes folder** (e.g. `~/VoiceTakes`).
2. In Claude: `/coach` (or "analyse my latest take").
3. Connector finds the newest unanalysed file, converts it, runs the analysis pipeline.
4. Claude presents: what it measured, what it heard in coaching terms, 2–3 targeted exercises, and a comparison to relevant previous takes ("break is now at E4 vs F4 three takes ago; jump size down from 4 semitones to 2").
5. Claude asks one or two clarifying questions where the signal is ambiguous ("Around 0:08 the tone thins suddenly — did that feel like an intentional shift to head voice, or a flip?"). Answers refine the feedback and are stored with the take.
6. Analysis, metrics, and notes persist in the library for future comparison and progress reports (`/progress`).

---

## 3. Plugin components

```
passaggio-coach/                  (plugin root)
├── plugin.json                   # manifest: name, version, MCP server, skills
├── skills/
│   └── passaggio-coach/
│       ├── SKILL.md              # coaching workflow + interpretation rubric
│       ├── references/
│       │   ├── pedagogy.md       # passaggio pedagogy, fault→exercise map
│       │   ├── voice-types.md    # passaggio zones per voice type
│       │   └── metrics.md        # what each acoustic metric means, thresholds
│       └── scripts/
│           ├── analyze.py        # full analysis pipeline (see §5)
│           ├── compare.py        # take-vs-take / trend comparison
│           └── plot.py           # pitch/spectral plots → PNG or HTML
├── mcp/
│   └── takes-server/             # local MCP server (Node or Python, stdio)
│       └── ...                   # tools in §4
└── commands/
    ├── coach.md                  # /coach [file] — analyse latest or named take
    ├── progress.md               # /progress — trend report across library
    └── takes.md                  # /takes — list library, tag, annotate
```

### Division of labour
- **MCP connector**: file discovery, format conversion, library CRUD. No opinions about singing.
- **Scripts**: deterministic signal processing. No opinions either — they emit numbers and plots.
- **Skill (SKILL.md + references)**: turns numbers into coaching. All pedagogy lives here so it can be tuned without touching code.
- **Claude in-session**: listening context, clarifying questions, exercise selection, tone.

---

## 4. Connector (MCP server: `takes-server`)

Local stdio MCP server watching one configured folder.

### Configuration (first-run, stored in `<takes-folder>/.passaggio/config.json`)
| Key | Example | Notes |
|---|---|---|
| `takes_dir` | `~/VoiceTakes` | user creates; Voice Memos exports go here |
| `voice_type` | `tenor` | sets expected passaggio zone (see §6) |
| `passaggio_override` | `["D4","G4"]` | optional manual zone if known |
| `sample_rate` | `44100` | analysis SR after conversion |

### Tools
| Tool | Purpose |
|---|---|
| `list_takes(filter?)` | List files in takes folder + library status (analysed / new), sorted by date |
| `ingest_take(path?)` | Newest file if no arg. Converts m4a/mp3/wav → mono 16-bit WAV @ 44.1 kHz (ffmpeg), validates duration (5–60 s, warn outside 15–25 s), copies normalised WAV into library |
| `analyze_take(id)` | Runs `analyze.py`, stores metrics JSON + plots in library, returns metrics |
| `get_take(id)` | Metrics, notes, tags, coaching summary for one take |
| `compare_takes(ids \| last_n \| tag)` | Runs `compare.py`, returns deltas + trend data |
| `annotate_take(id, notes/tags)` | Store user context: exercise sung, vowel, how it felt, Claude's summary |
| `set_profile(...)` | Update voice type / passaggio override |

### Library layout (persistent)
```
~/VoiceTakes/
├── take-2026-07-12-0930.m4a          # user's raw recordings (untouched)
└── .passaggio/
    ├── config.json
    ├── library.json                  # index: id, date, file, tags, headline metrics
    └── takes/<id>/
        ├── audio.wav                 # normalised copy
        ├── metrics.json              # full analysis output
        ├── pitch.png                 # f0 contour + register-event markers
        ├── spectrogram.png
        └── session.md                # coaching summary + Q&A from that session
```

Voice Memos note: it stores sandboxed .m4a internally, so the workflow is *export/save to the Takes folder* (drag from Voice Memos, or a Shortcuts automation "save latest memo to ~/VoiceTakes" — document this in README, out of plugin scope). Connector accepts m4a, wav, mp3, aiff.

---

## 5. Analysis pipeline (`analyze.py`)

**Stack:** Python — `praat-parselmouth` (Praat metrics), `librosa` (spectral, pYIN f0), `ffmpeg` (conversion), `matplotlib` (plots). Optional: `crepe` for more robust f0 if pYIN is noisy (defer to v0.2).

**Input:** mono WAV, ~20 s, expected content: a scale, siren/slide, or sustained phrase crossing the passaggio.

### 5.1 Extracted metrics
| Group | Metrics | Coaching relevance |
|---|---|---|
| Pitch | f0 contour (10 ms hop), range, note segmentation | Where in the range the singer worked; locate events on pitch |
| Register events | abrupt f0 jumps (> ~1.5 st in < 50 ms), voicing dropouts, sudden spectral-slope discontinuities | Cracks / flips / breaks — where and how big |
| Quality | jitter, shimmer, HNR, CPPS (per note and per contour region) | Instability and pressed vs breathy phonation through the zone |
| Spectral balance | spectral tilt / H1–H2, alpha ratio, singer's-formant band energy (2.4–3.2 kHz) | Chest-weight carried too high; whether tone "turns over" |
| Vowel/formant | F1, F2 tracks on sustained segments | Vowel modification: is F1 dropping as pitch rises, or is the vowel splatting open |
| Dynamics | RMS contour, crescendo/decrescendo behaviour through the zone | Pushing (loudness spikes at the break) vs steady support |
| Vibrato | rate, extent, onset regularity on sustained notes | Free vs suppressed/straightened tone under load |
| Timing | duration, silence ratio, note durations | Enough usable signal? |

### 5.2 Passaggio-zone scoring
Using the voice-type zone (§6) or override, compute per-metric contrasts **below-zone vs in-zone vs above-zone**. The interesting number is almost always the *delta at the zone*: e.g. CPPS stable below but collapsing in-zone → instability localised to the passaggio; spectral tilt unchanged into the zone → carrying chest weight up.

### 5.3 Output
`metrics.json` (all numbers + event list with timestamps), `pitch.png` (contour with zone shaded and events flagged), `spectrogram.png`. Every claim in coaching feedback must be traceable to a timestamped metric.

### 5.4 Quality gates (fail gracefully)
- Clipping, very low SNR, < 5 s voiced audio, or no pitch material within ±4 st of the zone → say so and ask for a retake with guidance, rather than coaching noise.
- Polyphony/backing track detected (harmonic mess in f0 tracking) → request an a-cappella take.

---

## 6. Voice-type profiles (`voice-types.md`)

Default primo/secondo passaggio zones per classification (approximate, override-able):

| Voice | Zone of interest (secondo passaggio) |
|---|---|
| Soprano | E5–F♯5 (plus primo ~E♭4) |
| Mezzo | D5–E5 |
| Contralto | C♯5–D5 |
| Tenor | D4–G4 |
| Baritone | B3–E4 |
| Bass | A3–D4 |

If the user doesn't know their type, the skill infers a working zone from where register events actually cluster across takes, and refines it over time.

---

## 7. Coaching logic (the skill)

### 7.1 Interpretation rubric (`pedagogy.md`)
A fault→evidence→exercise mapping, e.g.:

| Observed pattern | Likely fault | Exercise prescriptions |
|---|---|---|
| Large f0 jump + tilt discontinuity at zone | Flip to falsetto / abrupt release of weight | Descending octave slides on ‘oo’; messa di voce just below break; slow sirens through the seam |
| Tilt flat into zone, RMS rising, shimmer up | Carrying chest weight, pushing | Lip trills/straw ascents; lighten earlier — start rebalance 3–4 st below zone |
| F1 not dropping on ascent (open vowel held) | No vowel modification | ‘ah→uh/aw’, ‘eh→ih’ shading drills; closed-vowel repertoire snippets |
| CPPS drop + HNR drop in zone only | Instability localised at passaggio | SOVT work at the exact pitches flagged; sustained mid-zone notes at mp |
| Vibrato extent collapses in zone | Tension under load (jaw/tongue/larynx) | ‘yah-yah’ jaw release, yawn-sigh onset, tongue-out sirens |
| Loudness spike at zone entry | Compensating with air pressure | Decrescendo drills into the zone; appoggio focus |

Exercises always reference the singer's actual flagged pitches ("slide E♭4→A♭4, since your event cluster is at F4").

### 7.2 Interactive clarification
Acoustics can't distinguish everything (intentional head-voice shift vs involuntary flip; stylistic straight-tone vs tension). The skill asks at most 2–3 targeted questions per take via AskUserQuestion, each anchored to a timestamp, and stores answers in `session.md`. It also asks up-front context when missing: what exercise/vowel was sung, and how it felt.

### 7.3 Comparison & progress
- **Take-vs-take:** only compare like with like (same tag/exercise where possible); report deltas on the headline metrics: event pitch & size, in-zone CPPS, tilt delta, vowel tracking.
- **`/progress`:** trend over the library — chart of break-event size over time, zone stability score, plus a short narrative ("over 9 takes the flip has moved from a 4 st crack to a 1.5 st shimmer; next milestone: eliminate the loudness spike at zone entry").
- Guard against overfitting to noise: single-take changes < measurement noise are reported as "no meaningful change".

### 7.4 Tone & safety
- Coach voice: encouraging, specific, never punitive; always something that improved.
- Standing disclaimers: this is acoustic feedback, not a substitute for a teacher's ear; stop on pain/hoarseness; hydration/warm-up reminders if takes look strained (rising jitter across a session).

---

## 8. Session flow (skill pseudocode)

```
/coach
 ├─ ingest_take()               → newest file, convert, validate
 ├─ ask context if unknown      → exercise, vowel, self-assessment
 ├─ analyze_take()              → metrics.json + plots
 ├─ quality gate                → retake guidance if failed
 ├─ interpret via rubric        → 2–4 observations, each timestamped
 ├─ compare_takes(tag, last 3)  → deltas if history exists
 ├─ clarifying questions (≤3)   → refine interpretation
 ├─ prescribe 2–3 exercises     → at the singer's flagged pitches
 └─ annotate_take()             → persist summary + Q&A
```

---

## 9. Constraints & limitations (state honestly in README)

- ~20 s mono, solo voice, quiet room, phone mic ≥ ~30 cm. No backing tracks.
- Formant tracking is unreliable above ~C5 (harmonics too sparse) — vowel-modification feedback degrades for high soprano work; fall back to tilt/energy metrics there.
- Acoustic proxies, not physiology: "consistent with carried chest weight," never "your vocal folds are…".
- Not medical advice; persistent hoarseness → see a professional.

---

## 10. Build phases

| Phase | Scope | Definition of done |
|---|---|---|
| **1 — Skill core** | SKILL.md + references + `analyze.py`/`plot.py`; manual WAV upload; no persistence | One uploaded take → correct metrics, sensible coaching, plots |
| **2 — Library** | `.passaggio/` store, `compare.py`, annotate flow | Two takes compared with meaningful deltas |
| **3 — Connector** | MCP takes-server, ingest/convert, config | `/coach` picks up latest Voice Memos export with zero manual steps |
| **4 — Polish** | `/progress` trends, quality gates hardening, Shortcuts automation doc | Multi-week progress report from real library |

Phase 1 is shippable alone as a standalone skill — a useful fallback if plugin distribution is a hassle.

---

## 11. Open questions

1. Calibration: thresholds in §5/§7 need tuning against real takes of Brenton's voice — plan a calibration session in Phase 1.
2. Should `session.md` coaching summaries feed a running "singer profile" (persistent tendencies, e.g. "habitually pushes on ascending ‘ah’")? Proposed: yes, in Phase 4.
3. HTML report per take (interactive pitch plot) vs PNG only? Proposed: PNG in Phase 1, HTML later.
4. Multiple singers per takes folder? Out of scope v1 — one profile per folder.
