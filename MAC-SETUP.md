# Passaggio Coach — Mac setup & quick start

Hi! This is a little singing helper. You record a short take (about 20 seconds) singing
through your *passaggio* — the tricky spot where your voice changes gears — and it listens,
tells you in plain terms what happened (with the exact moment and pitch), and gives you a couple
of exercises. Over time it tracks whether the break is smoothing out.

Setup is a one-time thing, about 15 minutes. Copy–paste each command into **Terminal**
(press ⌘-Space, type "Terminal", Enter). If anything looks stuck or throws an error, don't
worry — paste the error to Claude or to Brenton and it's usually a quick fix.

> You'll need **Claude Code** installed and signed in first. If it isn't yet, Brenton can set
> that up — everything below assumes you can open Claude Code.

---

## Step 1 — Install Python

Download and run the official installer (it's a normal double-click `.pkg`):

**https://www.python.org/downloads/macos/** → get **Python 3.13** (the "macOS 64-bit universal2
installer"). If 3.13 isn't offered, 3.12 is fine too. Open the `.pkg` and click through.

Then check it worked — in Terminal:

```bash
python3 --version
```

You should see something like `Python 3.13.x`. (Your Mac is Apple Silicon, which everything here
fully supports.)

> Why the official installer and not Homebrew? This one puts `python3` somewhere both the
> Terminal *and* the Claude app can see, and it lets you install the audio libraries without
> extra flags. It's the smoothest path.

---

## Step 2 — Install the audio libraries

This is the engine that listens to your voice. In Terminal:

```bash
python3 -m pip install librosa praat-parselmouth soundfile matplotlib scipy numpy mcp
```

It downloads a few things and takes a couple of minutes — that's normal. These come as
ready-made packages for your Apple-Silicon Mac (nothing gets compiled), so you shouldn't see
errors. When it finishes, check it:

```bash
python3 -c "import librosa, parselmouth, mcp; print('all good')"
```

If it prints **`all good`**, you're set. (If it complains, see *If something isn't working*
at the bottom.)

---

## Step 3 — Install ffmpeg (only for Voice Memos recordings)

Voice Memos saves recordings as `.m4a`, and `ffmpeg` is the tool that converts those.

If you have **Homebrew** (`brew`):

```bash
brew install ffmpeg
```

No Homebrew? You can either install it from **https://brew.sh** first, or simply **save your
takes as WAV** instead — WAV files need no ffmpeg at all, so you can skip this step entirely.

Check (if you installed it):

```bash
ffmpeg -version
```

---

## Step 4 — Add the plugin to Claude Code

Inside **Claude Code**, type these two commands:

```
/plugin marketplace add BrentonStarkie/passaggio-coach-plugin
/plugin install passaggio-coach@passaggio-coach-plugin
```

That installs the coach and starts its background helper (the "takes-server") that watches your
recordings folder. If Claude Code asks you to restart or reload plugins, do that.

---

## Step 5 — Make your Takes folder

This is where your recordings live. In Terminal:

```bash
mkdir -p ~/VoiceTakes
```

(That's your home folder → a new folder called `VoiceTakes`.)

---

## Step 6 — Check it all works

In Claude Code, type:

```
/passaggio-coach:takes
```

It should reply with your (empty) take library at `~/VoiceTakes`. That means everything is
wired up. 🎉

---

## Recording a good take

You'll get the best feedback with a recording like this:

- **~20 seconds** (15–25 is the sweet spot).
- Sing **through your break** — a slow scale, a siren/slide, or a sustained phrase that crosses
  the tricky spot.
- **Just your voice** — no piano or backing track.
- A **quiet room**, mic about a **hand-span away** (~30 cm).

### Getting a Voice Memo into your Takes folder

1. Record in **Voice Memos** as usual.
2. Tap the take → the **•••** (or Share) button → **Save to Files** → choose **VoiceTakes**.

That's it — the coach picks up the newest one automatically.

*Optional one-tap version:* in the **Shortcuts** app you can make a shortcut that saves your
latest voice memo straight to `VoiceTakes`. Nice to have, not required — ask Claude to help you
build it if you'd like.

---

## Using it day to day

Just talk to Claude Code, or use these:

- **`/passaggio-coach:coach`** — analyses your newest take: what it heard (with timestamps), a
  couple of exercises at your own pitches, and the pitch/spectrogram pictures. It may ask you a
  quick question or two (like "was that shift on purpose?") — your answers sharpen the feedback.
- **`/passaggio-coach:progress`** — the bigger picture over many takes: is the break shrinking?
- **`/passaggio-coach:takes`** — see and label your takes.

You can also just say things like *"analyse my latest take"* or *"how's my passaggio been
lately?"* — it understands plain requests too.

---

## Optional — tell it your voice type

By default the coach figures out where your break is from your recordings. If you'd rather tell
it up front (sharper from take one):

```
/passaggio-coach:takes set-voice soprano
```

(Use `soprano`, `mezzo`, `contralto`, `tenor`, `baritone`, or `bass`.)

---

## A gentle note

This is a helpful second pair of ears, **not a replacement for a real teacher**, and it's **not
medical advice**. If singing ever hurts or you get hoarse, stop and rest. Warm up, and drink
water. 💧

---

## If something isn't working

| What you see | What to do |
|---|---|
| `ModuleNotFoundError` when analysing | The libraries aren't in the Python that Claude is using. Re-run **Step 2**. Make sure Step 1's `python3 --version` worked first. |
| A library **fails to install** in Step 2 | Run `xcode-select --install` (installs Apple's build tools), then re-run Step 2. |
| "ffmpeg not found" / `.m4a` won't open | Do **Step 3**, or save the take as **WAV** instead. If you installed ffmpeg with Homebrew but it's still not found, try running Claude Code from **Terminal** (type `claude`) rather than the app — the app sometimes can't see Homebrew tools. |
| `/passaggio-coach:...` commands aren't there | Re-check **Step 4**, then restart Claude Code (or run `/plugin` and confirm it's installed/enabled). |
| The coach says it can't find a take | Make sure the recording is saved **into `~/VoiceTakes`** (Step 2 of "Getting a Voice Memo in"), and it's a `.m4a`, `.wav`, `.mp3`, or `.aiff`. |

Still stuck? Paste the exact message to Claude, or send it to Brenton — it's almost always a
one-line fix.

---

Happy singing! 🎶
