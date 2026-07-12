#!/usr/bin/env python3
"""Library CLI: list / ingest / get / annotate / set-profile (spec §4 tools).

The eventual MCP `takes-server` exposes these same operations; keeping them here means the
skill/commands work today (manual file selection) and the connector is later a thin wrapper.

Usage:
  python library.py list    --takes-dir ~/VoiceTakes [--status analysed] [--tag scale-ah]
  python library.py ingest  --takes-dir ~/VoiceTakes --path /path/to/take.m4a [--when ISO]
  python library.py get     --takes-dir ~/VoiceTakes --id take-2026-07-12-0930
  python library.py annotate --takes-dir ~/VoiceTakes --id ID [--notes "..."] [--tags a b]
                             [--summary "coaching summary markdown"]
  python library.py set-profile --takes-dir ~/VoiceTakes [--voice-type tenor] [--override D4 G4]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from passaggio import store as S  # noqa: E402


def _print(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Passaggio take library operations.")
    ap.add_argument("cmd", choices=["list", "ingest", "get", "annotate", "set-profile", "init"])
    ap.add_argument("--takes-dir")
    ap.add_argument("--status")
    ap.add_argument("--tag")
    ap.add_argument("--path")
    ap.add_argument("--id")
    ap.add_argument("--when")
    ap.add_argument("--notes")
    ap.add_argument("--tags", nargs="+")
    ap.add_argument("--summary")
    ap.add_argument("--voice-type")
    ap.add_argument("--override", nargs=2, metavar=("LOW", "HIGH"))
    args = ap.parse_args(argv)

    store = S.Store(args.takes_dir).ensure()

    if args.cmd in ("init", "set-profile"):
        cfg = store.set_profile(voice_type=args.voice_type,
                                passaggio_override=args.override)
        _print({"config": cfg, "takes_dir": str(store.takes_dir)})
        return 0

    if args.cmd == "list":
        _print({"takes_dir": str(store.takes_dir),
                "profile": store.profile(),
                "takes": store.list_takes(status=args.status, tag=args.tag)})
        return 0

    if args.cmd == "ingest":
        if not args.path:
            ap.error("ingest requires --path")
        rec = store.ingest(args.path, when_iso=args.when)
        _print(rec)
        return 0

    if args.cmd == "get":
        if not args.id:
            ap.error("get requires --id")
        rec = store.get_take(args.id)
        if not rec:
            _print({"error": f"No take '{args.id}'."})
            return 2
        td = store.take_dir(args.id)
        session = td / "session.md"
        _print({"take": rec,
                "artifacts": {"dir": str(td),
                              "metrics_json": str(td / "metrics.json"),
                              "pitch_png": str(td / "pitch.png"),
                              "spectrogram_png": str(td / "spectrogram.png"),
                              "session_md": str(session) if session.exists() else None}})
        return 0

    if args.cmd == "annotate":
        if not args.id:
            ap.error("annotate requires --id")
        rec = store.annotate_take(args.id, notes=args.notes, tags=args.tags,
                                  summary=args.summary)
        _print(rec)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
