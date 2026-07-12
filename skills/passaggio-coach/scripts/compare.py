#!/usr/bin/env python3
"""Compare takes and report trends (spec §7.3). Deterministic and opinion-free: emits deltas,
series, and 'meaningful vs noise' flags; the skill turns these into coaching narrative.

Usage:
  python compare.py --takes-dir ~/VoiceTakes --ids take-A take-B [take-C ...]
  python compare.py --takes-dir ~/VoiceTakes --last-n 3 [--tag scale-ah]
  python compare.py --takes-dir ~/VoiceTakes --trend            # whole library, for /progress

Prints JSON: selected takes, pairwise deltas (first vs last), a per-metric time series, and
simple trend directions. Only compares like-with-like when --tag is given; otherwise warns if
the selection mixes exercises (tags).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from passaggio import store as S  # noqa: E402

# Per-metric measurement-noise floors: deltas smaller than this are "no meaningful change".
NOISE = {
    "biggest_event_semitones": 0.6,
    "event_count": 1,
    "in_zone_cpps_db": 1.0,
    "in_zone_hnr_db": 2.0,
    "tilt_in_minus_below": 0.6,
    "in_zone_rms_slope_db_per_s": 0.7,
    "entry_spike_db": 1.5,
    "voiced_ratio": 0.05,
}
# For these, a smaller value is generally the goal (used only to annotate direction, not judge).
LOWER_IS_TIGHTER = {"biggest_event_semitones", "event_count", "entry_spike_db"}


def _load_metrics(store, take_id):
    p = store.take_dir(take_id) / "metrics.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _features(rec, m):
    """Flatten the metrics a comparison cares about into one dict."""
    if m is None:
        m = {}
    q_in = ((m.get("quality") or {}).get("by_region") or {}).get("in") or {}
    tilt = ((m.get("spectral_by_region") or {}).get("spectral_tilt_db_per_khz") or {})
    dyn = m.get("dynamics") or {}
    head = m.get("headline") or {}
    biggest = head.get("biggest_event_semitones")
    return {
        "id": rec["id"],
        "date": rec.get("date"),
        "tags": rec.get("tags") or [],
        "biggest_event_semitones": None if biggest is None else abs(biggest),
        "biggest_event_note": head.get("biggest_event_note"),
        "event_count": head.get("event_count"),
        "in_zone_cpps_db": q_in.get("cpps_db"),
        "in_zone_hnr_db": q_in.get("hnr_db"),
        "tilt_in_minus_below": tilt.get("in_minus_below"),
        "in_zone_rms_slope_db_per_s": dyn.get("in_zone_rms_slope_db_per_s"),
        "entry_spike_db": dyn.get("entry_spike_db"),
        "voiced_ratio": head.get("voiced_ratio"),
        "zone_note_range": head.get("zone_note_range"),
    }


def _delta(name, a, b):
    if a is None or b is None:
        return {"from": a, "to": b, "delta": None, "meaningful": None}
    d = round(b - a, 3)
    floor = NOISE.get(name, 0.0)
    meaningful = abs(d) >= floor
    out = {"from": a, "to": b, "delta": d, "meaningful": meaningful}
    if name in LOWER_IS_TIGHTER and meaningful:
        out["direction"] = "tighter" if d < 0 else "looser"
    return out


def _trend(values):
    xs = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(xs) < 2:
        return {"slope_per_take": None, "first": None, "last": None, "n": len(xs)}
    n = len(xs)
    mx = sum(i for i, _ in xs) / n
    my = sum(v for _, v in xs) / n
    den = sum((i - mx) ** 2 for i, _ in xs) or 1e-9
    slope = sum((i - mx) * (v - my) for i, v in xs) / den
    return {"slope_per_take": round(slope, 3), "first": xs[0][1], "last": xs[-1][1], "n": n}


def compare(store, ids=None, last_n=None, tag=None):
    """Compare / trend over analysed takes. Returns an opinion-free result dict. Shared by the
    CLI and the takes-server MCP tool."""
    takes = store.list_takes(status="analysed", tag=tag)  # sorted by date
    if ids:
        by_id = {t["id"]: t for t in store.list_takes(status="analysed")}
        takes = [by_id[i] for i in ids if i in by_id]
    elif last_n:
        takes = takes[-last_n:]

    if len(takes) < 1:
        return {"error": "No analysed takes matched the selection."}

    feats = [_features(t, _load_metrics(store, t["id"])) for t in takes]
    metric_names = ["biggest_event_semitones", "event_count", "in_zone_cpps_db",
                    "in_zone_hnr_db", "tilt_in_minus_below", "in_zone_rms_slope_db_per_s",
                    "entry_spike_db", "voiced_ratio"]
    series = {name: [f[name] for f in feats] for name in metric_names}

    warnings = []
    tagsets = {tuple(sorted(f["tags"])) for f in feats}
    if not tag and len(tagsets) > 1:
        warnings.append("Selection mixes exercises/tags; comparisons may not be like-with-like: "
                        + str([f['tags'] for f in feats]))

    result = {
        "schema": "passaggio-compare/0.1",
        "n_takes": len(feats),
        "takes": feats,
        "series": series,
        "trends": {name: _trend(series[name]) for name in metric_names},
        "warnings": warnings,
    }
    if len(feats) >= 2:
        a, b = feats[0], feats[-1]
        result["pairwise"] = {
            "from_id": a["id"], "to_id": b["id"],
            "from_date": a["date"], "to_date": b["date"],
            "deltas": {name: _delta(name, a[name], b[name]) for name in metric_names},
        }
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="Compare takes / trend report.")
    ap.add_argument("--takes-dir")
    ap.add_argument("--ids", nargs="+")
    ap.add_argument("--last-n", type=int)
    ap.add_argument("--tag")
    ap.add_argument("--trend", action="store_true")  # trends are always included; flag kept for CLI
    args = ap.parse_args(argv)

    store = S.Store(args.takes_dir).ensure()
    result = compare(store, ids=args.ids, last_n=args.last_n, tag=args.tag)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 2 if "error" in result else 0


if __name__ == "__main__":
    raise SystemExit(main())
