#!/usr/bin/env python3
"""takes-server — local stdio MCP server for the Passaggio Coach take library (spec §4).

A THIN wrapper: every tool delegates to the already-tested `passaggio` package and the
`analyze`/`compare` cores. No signal-processing or library logic lives here.

Watched folder: `PASSAGGIO_TAKES_DIR` env var, else `~/VoiceTakes` (store.default_takes_dir).
Run: `python server.py` (stdio). Requires the same deps as the scripts, plus `mcp`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Make the analysis package + CLI cores importable (…/skills/passaggio-coach/scripts).
SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "passaggio-coach" / "scripts"
ANALYZE_PY = SCRIPTS / "analyze.py"
sys.path.insert(0, str(SCRIPTS))

import compare  # noqa: E402  (pure-Python trend/deltas; safe to run in-process)
from passaggio import store as S  # noqa: E402

import anyio  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("takes-server")

ACCEPTED = {".wav", ".m4a", ".mp3", ".aiff", ".aif", ".flac"}


def _dbg(msg):
    if os.environ.get("PASSAGGIO_DEBUG"):
        print(f"[takes-server] {msg}", file=sys.stderr, flush=True)


def _store() -> S.Store:
    return S.Store(os.environ.get("PASSAGGIO_TAKES_DIR") or None).ensure()


def _audio_files(store):
    return [p for p in store.takes_dir.iterdir()
            if p.is_file() and p.suffix.lower() in ACCEPTED]


def _ingested_sources(store):
    out = set()
    for t in store.library().get("takes", []):
        sf = t.get("source_file")
        if sf:
            try:
                out.add(str(Path(sf).resolve()))
            except Exception:
                out.add(sf)
    return out


def _newest_new_file(store):
    ing = _ingested_sources(store)
    fresh = [p for p in _audio_files(store) if str(p.resolve()) not in ing]
    return max(fresh, key=lambda p: p.stat().st_mtime) if fresh else None


# ---------------------------------------------------------------------------
# Tools (spec §4)
# ---------------------------------------------------------------------------
@mcp.tool()
def list_takes(status: str | None = None, tag: str | None = None) -> dict:
    """List takes in the library (id, date, tags, status, headline metrics), sorted by date.
    Optional filter by status ('ingested'|'analysed') or tag. Also reports the newest raw
    recording that has not been ingested yet, if any."""
    st = _store()
    newest_new = _newest_new_file(st)
    return {
        "takes_dir": str(st.takes_dir),
        "profile": st.profile(),
        "takes": st.list_takes(status=status, tag=tag),
        "newest_uningested_file": str(newest_new) if newest_new else None,
    }


@mcp.tool()
async def ingest_take(path: str | None = None) -> dict:
    """Ingest a recording into the library: convert to normalised mono 16-bit WAV @44.1 kHz,
    validate duration, copy in, and index it. With no `path`, ingests the newest not-yet-ingested
    recording in the takes folder. Returns the take record (with any duration warnings)."""
    st = _store()
    if path:
        src = Path(path).expanduser()
    else:
        src = _newest_new_file(st)
        if src is None:
            files = _audio_files(st)
            if not files:
                return {"error": f"No audio files found in {st.takes_dir}."}
            newest = max(files, key=lambda p: p.stat().st_mtime)
            for t in st.library().get("takes", []):
                if str(Path(t.get("source_file", "")).resolve()) == str(newest.resolve()):
                    return {"already_ingested": t["id"], "take": t,
                            "note": "Newest recording is already in the library."}
            src = newest
    # conversion may shell out to ffmpeg — offload so it can't block the stdio event loop
    return await anyio.to_thread.run_sync(lambda: st.ingest(src))


@mcp.tool()
async def analyze_take(id: str, voice_type: str | None = None,
                       override_low: str | None = None, override_high: str | None = None) -> dict:
    """Run the acoustic analysis on a stored take: writes metrics.json + pitch/spectrogram PNGs
    into the take folder and returns the metrics (without the heavy per-frame series). Optional
    per-run zone hints: voice_type, or a manual override (override_low + override_high, e.g. D4 G4).

    The heavy DSP (librosa/numba/matplotlib) is run as a clean subprocess offloaded to a worker
    thread, so it never blocks the async stdio event loop (running it in-loop deadlocks)."""
    st = _store()
    if not st.get_take(id):
        return {"error": f"No take '{id}' in the library."}
    cmd = [sys.executable, str(ANALYZE_PY), "--id", id, "--takes-dir", str(st.takes_dir)]
    if voice_type:
        cmd += ["--voice-type", voice_type]
    if override_low and override_high:
        cmd += ["--override", override_low, override_high]

    _dbg(f"analyze: launching subprocess for {id}")
    # stdin=DEVNULL so the child never inherits the MCP stdio pipe (that deadlocks on Windows).
    proc = await anyio.to_thread.run_sync(
        lambda: subprocess.run(cmd, capture_output=True, text=True,
                               stdin=subprocess.DEVNULL))
    _dbg(f"analyze: subprocess done rc={proc.returncode}")
    if proc.returncode != 0:
        return {"error": "analysis subprocess failed", "stderr": (proc.stderr or "")[-1500:]}
    try:
        return json.loads(proc.stdout)
    except Exception as e:
        return {"error": f"could not parse analysis output: {e}",
                "stdout_tail": (proc.stdout or "")[-500:], "stderr_tail": (proc.stderr or "")[-500:]}


@mcp.tool()
def get_take(id: str) -> dict:
    """Return one take's record (notes, tags, headline), its full metrics (minus the raw series),
    and artifact paths (metrics.json, plots, session.md)."""
    st = _store()
    rec = st.get_take(id)
    if not rec:
        return {"error": f"No take '{id}' in the library."}
    td = st.take_dir(id)
    mpath = td / "metrics.json"
    metrics = None
    if mpath.exists():
        metrics = json.loads(mpath.read_text(encoding="utf-8"))
        metrics.pop("_series", None)
    session = td / "session.md"
    return {
        "take": rec,
        "metrics": metrics,
        "artifacts": {
            "dir": str(td),
            "metrics_json": str(mpath) if mpath.exists() else None,
            "pitch_png": str(td / "pitch.png") if (td / "pitch.png").exists() else None,
            "spectrogram_png": str(td / "spectrogram.png") if (td / "spectrogram.png").exists() else None,
            "session_md": str(session) if session.exists() else None,
        },
    }


@mcp.tool()
def compare_takes(ids: list[str] | None = None, last_n: int | None = None,
                  tag: str | None = None) -> dict:
    """Compare takes and report trends (deltas with 'meaningful vs noise' flags + time series).
    Provide explicit `ids`, or `last_n` most-recent, and/or a `tag` to keep it like-with-like."""
    return compare.compare(_store(), ids=ids, last_n=last_n, tag=tag)


@mcp.tool()
def annotate_take(id: str, notes: str | None = None, tags: list[str] | None = None,
                  summary: str | None = None) -> dict:
    """Store context on a take: free-text `notes` (vowel, how it felt), `tags` (e.g. the
    exercise), and/or a coaching `summary` markdown (appended to the take's session.md)."""
    return _store().annotate_take(id, notes=notes, tags=tags, summary=summary)


@mcp.tool()
def set_profile(voice_type: str | None = None,
                override_low: str | None = None, override_high: str | None = None) -> dict:
    """Set the singer's voice type and/or a manual passaggio zone override for this takes folder.
    Leave all unset to keep the default 'infer the zone from takes'."""
    override = [override_low, override_high] if (override_low and override_high) else None
    return {"config": _store().set_profile(voice_type=voice_type, passaggio_override=override)}


if __name__ == "__main__":
    mcp.run()  # stdio transport by default
