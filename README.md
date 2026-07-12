# Passaggio Coach

A Claude Code plugin that analyses short vocal takes (~20 s) of **passaggio** (register-break)
work, gives targeted, timestamped coaching and exercises, and tracks progress across takes.

It measures *where* and *how* your register transition happens — the pitch and size of any
crack/flip, whether you're carrying chest weight up, pushing with air, or losing vibrato under
load — then prescribes a couple of exercises at your own flagged pitches, and compares today's
take with past ones.

> **What it is / isn't.** A second pair of (acoustic) ears, not a substitute for a teacher.
> It reports acoustic proxies ("consistent with carried chest weight"), never physiology, and
> gives **no medical advice** — persistent hoarseness or pain means rest and see a professional.

---

## Contents

```
passaggio-coach-plugin/
├── .claude-plugin/plugin.json      # manifest
├── commands/                       # /passaggio-coach:coach | :progress | :takes
├── skills/passaggio-coach/
│   ├── SKILL.md                    # the coaching workflow (the brain)
│   ├── references/                 # pedagogy, voice-types, metrics (tunable, no code)
│   └── scripts/                    # deterministic analysis (Python)
├── requirements.txt
└── README.md
```

The **scripts** emit numbers, timestamped events, and plots (no opinions). The **skill +
references** turn those into coaching. Keeping pedagogy in Markdown means you can tune the
coaching without touching code.

---

## Setup

Developed on Windows; intended to run mainly on **macOS**. Everything is cross-platform.

> **Setting up on a Mac?** [**MAC-SETUP.md**](MAC-SETUP.md) is a friendly, non-technical,
> copy-paste walkthrough (Python, ffmpeg, install, first take). The steps below are the concise
> cross-platform version.

### 1. Python dependencies (once)
Requires **Python 3.10+** (verified on 3.13). A virtualenv is recommended:

```bash
# macOS / Linux
python3 -m venv .venv && source .venv/bin/activate
python3 -m pip install -r requirements.txt
```
```powershell
# Windows
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Claude runs the analysis scripts with whatever `python3` (macOS) / `python` (Windows) is on
PATH, so install the deps into **that** interpreter (activate the venv in the shell Claude uses,
or install globally).

### 2. ffmpeg — only for compressed audio
WAV / AIFF / FLAC are read directly and need **no ffmpeg**. You only need ffmpeg to convert
**Voice Memos `.m4a`** or `.mp3`:

```bash
# macOS
brew install ffmpeg
```
```powershell
# Windows
winget install Gyan.FFmpeg      # or: scoop install ffmpeg
```

### 3. Install the plugin
Simplest (development/local use) — point Claude Code at the folder:

```bash
claude --plugin-dir /path/to/passaggio-coach-plugin
```

Then in Claude Code the commands are available (namespaced by plugin):
`/passaggio-coach:coach`, `/passaggio-coach:progress`, `/passaggio-coach:takes`.

Or install it as a marketplace plugin (the repo ships `.claude-plugin/marketplace.json`, so
Claude Code can fetch it from GitHub):

```
/plugin marketplace add BrentonStarkie/passaggio-coach-plugin
/plugin install passaggio-coach@passaggio-coach-plugin
```

(The GitHub repo is public, so no sign-in is needed to install.)

### 3b. The takes-server connector (automatic library)
Installing the plugin also starts a bundled local MCP server, **`takes-server`** (declared in
`.claude-plugin/plugin.json`), that watches your takes folder and exposes the library operations
(`ingest_take`, `analyze_take`, `compare_takes`, `list_takes`, `get_take`, `annotate_take`,
`set_profile`) as tools — so `/coach` can pick up your newest recording with zero manual steps.

- **Watched folder:** `~/VoiceTakes` by default. To watch another folder, add an `env` block with
  `PASSAGGIO_TAKES_DIR` to `mcpServers.takes-server` in `.claude-plugin/plugin.json`.
- **Dependencies:** the same audio stack as the scripts **plus `mcp`** (both in `requirements.txt`),
  available to the interpreter that launches the server.
- **Interpreter (cross-platform):** the manifest launches it with **`python3`** (correct for macOS).
  On **Windows**, change `mcpServers.takes-server.command` in `.claude-plugin/plugin.json` from
  `"python3"` to `"python"` (or `"py"`). If you use a venv, point `command` at that venv's
  python so it can see the installed deps.
- Analysis runs in a short-lived subprocess (~15–25 s per take), so the async connector never
  blocks.

### 4. Verify the install (no recording needed)
Generate a synthetic take and analyse it end-to-end:

```bash
python3 skills/passaggio-coach/scripts/make_synthetic_take.py /tmp/pc_check
python3 skills/passaggio-coach/scripts/analyze.py --wav /tmp/pc_check/take_flip4.wav --out /tmp/pc_check/out
```
You should get `metrics.json` + `pitch.png` + `spectrogram.png`, with one `flip/break` event at
~F♯4, ~−4 semitones. If `analyze.py` raises `ModuleNotFoundError`, revisit step 1.

---

## Using it

### Quick, one-off (no library)
Record ~20 s crossing your break (a scale, siren/slide, or sustained phrase), export as WAV,
then:

> `/passaggio-coach:coach ~/Desktop/my-take.wav`

You'll get: what it measured (timestamped), what it means in coaching terms, 2–3 exercises at
your flagged pitches, and the pitch/spectrogram plots.

### With progress tracking (a take library)
Set up a takes folder once (default `~/VoiceTakes`):

> `/passaggio-coach:takes set-voice tenor`   *(optional — omit to infer your zone from takes)*

Drop recordings into that folder, then `/passaggio-coach:coach` picks up the newest one,
analyses it, and stores metrics + notes. Over time, `/passaggio-coach:progress` charts whether
the break is shrinking.

The library lives under `<takes-folder>/.passaggio/` (config, an index, and per-take
audio/metrics/plots/session notes). Your raw recordings are never modified.

### Voice Memos → Takes folder (macOS)
Voice Memos keeps recordings sandboxed as `.m4a`, so **export/save the memo into your takes
folder** (drag it out, or "Share → Save to Files → VoiceTakes"). To automate it, a **Shortcuts**
automation ("save latest voice memo to ~/VoiceTakes") works well — that's outside the plugin's
scope, but it's the intended fast path. (`.m4a` needs ffmpeg; see setup.)

---

## Recording for good results (constraints)
- **~20 s, mono, solo voice, quiet room, phone mic ~30 cm.** No backing tracks or harmony.
- Sing **through** the break (scale/siren/sustained phrase crossing the passaggio).
- 5–60 s is accepted; **15–25 s is the sweet spot**. Too short or too noisy → you'll be asked
  for a retake instead of coached on noise.
- **Formant/vowel feedback is unreliable above ~C5** (harmonics too sparse) — high-soprano work
  falls back to tilt/energy metrics.
- One singer per takes folder (v1).

---

## Build status

| Working & verified | Deferred |
|---|---|
| Analysis pipeline (`analyze.py`): f0, register events, jitter/shimmer/HNR/CPPS, spectral tilt/alpha/singer's-formant, formants, dynamics, vibrato, zone scoring, quality gates | More robust f0 via CREPE (pyin is octave-repaired but can still slip near the passaggio) |
| Plots (`pitch.png`, `spectrogram.png`) | Interactive HTML pitch report |
| Take library + comparison/trend (`compare.py`, `library.py`) | Running "singer profile" of persistent tendencies |
| **MCP connector** (`takes-server`): 7 stdio tools — ingest / analyze / compare / list / get / annotate / set-profile — verified end-to-end over the MCP protocol | Push/watch daemon (today it's pull: `/coach` fetches the newest recording on demand) |
| Coaching skill + references; `/coach`, `/progress`, `/takes` | |

Thresholds in `references/metrics.md` and the pedagogy in `references/pedagogy.md` are starting
points — calibrate them against real takes of your own voice.

---

## License
MIT.
