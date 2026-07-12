#!/usr/bin/env python3
"""Analyse one take: metrics + plots (spec §5).

Usage:
  # Manual (Phase 1): analyse any WAV/AIFF/FLAC/m4a directly
  python analyze.py --wav path/to/take.wav [--voice-type tenor] [--override D4 G4] [--out DIR]

  # Library: analyse a stored take by id
  python analyze.py --id take-2026-07-12-0930 --takes-dir ~/VoiceTakes

Writes metrics.json + pitch.png + spectrogram.png into the output/take dir and prints a
compact metrics summary (without the raw per-frame series) as JSON on stdout.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # make `passaggio` importable

from passaggio import audio, metrics as M, plot, store as S  # noqa: E402


def _prior_event_midis(store):
    midis = []
    for t in store.list_takes(status="analysed"):
        mpath = store.take_dir(t["id"]) / "metrics.json"
        if mpath.exists():
            try:
                data = json.loads(mpath.read_text(encoding="utf-8"))
                midis += [e["midi"] for e in data.get("events", []) if e.get("midi") is not None]
            except Exception:
                pass
    return midis


def analyze_file(wav, out_dir, profile, prior=None, plots=True, title="take"):
    """Core analysis: load audio, run metrics, write metrics.json (+ plots). Returns the full
    result dict (including `_series`). Shared by the CLI and the takes-server MCP tool."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    y, sr = audio.load_audio(wav)
    result = M.analyze_signal(y, sr, profile=profile, prior_event_midis=prior)
    (out_dir / "metrics.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if plots:
        try:
            plot.plot_pitch(result, str(out_dir / "pitch.png"), title=title)
            plot.plot_spectrogram(y, sr, result, str(out_dir / "spectrogram.png"), title=title)
        except Exception as e:
            result.setdefault("errors", []).append(f"plotting: {e}")
    return result


def compact_result(result, out_dir):
    """Strip the heavy per-frame `_series` and attach artifact paths, for returning to a caller."""
    out_dir = Path(out_dir)
    compact = copy.deepcopy(result)
    compact.pop("_series", None)
    compact["_artifacts"] = {
        "dir": str(out_dir),
        "metrics_json": str(out_dir / "metrics.json"),
        "pitch_png": str(out_dir / "pitch.png"),
        "spectrogram_png": str(out_dir / "spectrogram.png"),
    }
    return compact


def main(argv=None):
    ap = argparse.ArgumentParser(description="Analyse a passaggio take.")
    ap.add_argument("--wav", help="Path to an audio file (wav/aiff/flac/m4a/mp3).")
    ap.add_argument("--id", help="Take id in the library (with --takes-dir).")
    ap.add_argument("--takes-dir", help="Takes folder holding .passaggio/ (default ~/VoiceTakes).")
    ap.add_argument("--out", help="Output dir for metrics/plots (default: alongside input).")
    ap.add_argument("--voice-type", help="Override voice type for this run (else use config/infer).")
    ap.add_argument("--override", nargs=2, metavar=("LOW", "HIGH"),
                    help="Manual passaggio zone, e.g. --override D4 G4.")
    ap.add_argument("--title", help="Label for plot titles.")
    ap.add_argument("--no-plots", action="store_true")
    args = ap.parse_args(argv)

    store = None
    prior = None
    profile = {"voice_type": None, "passaggio_override": None}

    if args.id:
        store = S.Store(args.takes_dir).ensure()
        rec = store.get_take(args.id)
        if not rec:
            print(json.dumps({"error": f"No take '{args.id}' in library."}))
            return 2
        wav = store.pdir / rec["audio"]
        out_dir = store.take_dir(args.id)
        profile = store.profile()
        prior = _prior_event_midis(store)
        title = args.title or args.id
    elif args.wav:
        wav = Path(args.wav).expanduser()
        out_dir = Path(args.out).expanduser() if args.out else wav.parent / f"{wav.stem}_analysis"
        title = args.title or wav.stem
    else:
        ap.error("Provide --wav PATH or --id ID.")
        return 2

    # per-run profile overrides
    if args.voice_type:
        profile["voice_type"] = args.voice_type
    if args.override:
        profile["passaggio_override"] = list(args.override)

    result = analyze_file(wav, out_dir, profile, prior=prior,
                          plots=not args.no_plots, title=title)
    if store is not None:
        store.register_analysis(args.id, result)

    print(json.dumps(compact_result(result, out_dir), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
