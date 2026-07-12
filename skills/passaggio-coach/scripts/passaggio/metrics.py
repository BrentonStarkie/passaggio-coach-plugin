"""Deterministic acoustic analysis of a passaggio take.

Emits numbers, timestamped register events, and per-zone contrasts (spec §5). No coaching
opinions. Every section degrades gracefully: a failing metric records an error and returns
None rather than aborting the whole analysis.

Main entry point: analyze_signal(y, sr, profile, prior_event_midis) -> dict.
"""
from __future__ import annotations

import math
import warnings as _warnings

import numpy as np

from . import zones

_warnings.filterwarnings("ignore")

HOP_S = 0.01           # 10 ms frame hop
N_FFT = 2048
FMIN_HZ = 65.0         # C2 — covers bass..soprano
FMAX_HZ = 1200.0       # ~D6
EPS = 1e-10


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def _nanmean(a):
    a = np.asarray(a, dtype=float)
    m = a[~np.isnan(a)]
    return float(np.mean(m)) if m.size else None


def _round(x, n=2):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), n)


def _hz_to_midi_arr(f0):
    out = np.full(len(f0), np.nan)
    ok = ~np.isnan(f0) & (f0 > 0)
    out[ok] = 69.0 + 12.0 * np.log2(f0[ok] / 440.0)
    return out


# ----------------------------------------------------------------------------
# pitch
# ----------------------------------------------------------------------------
def extract_pitch(y, sr):
    import librosa
    hop = int(sr * HOP_S)
    f0, vflag, vprob = librosa.pyin(
        y, fmin=FMIN_HZ, fmax=FMAX_HZ, sr=sr,
        frame_length=N_FFT, hop_length=hop, fill_na=np.nan,
    )
    times = librosa.times_like(f0, sr=sr, hop_length=hop)
    return times, f0, np.asarray(vflag, dtype=bool), np.asarray(vprob), hop


def pitch_summary(f0, f0_midi):
    voiced = f0_midi[~np.isnan(f0_midi)]
    if voiced.size == 0:
        return {"voiced_frames": 0}
    lo, hi = float(np.min(voiced)), float(np.max(voiced))
    return {
        "voiced_frames": int(voiced.size),
        "f0_median_hz": _round(float(np.nanmedian(f0)), 1),
        "range_semitones": _round(hi - lo, 1),
        "low_note": zones.midi_to_note_name(lo),
        "high_note": zones.midi_to_note_name(hi),
        "low_hz": _round(zones.midi_to_hz(lo), 1),
        "high_hz": _round(zones.midi_to_hz(hi), 1),
    }


# ----------------------------------------------------------------------------
# sustained-segment detection (for formants + vibrato)
# ----------------------------------------------------------------------------
def find_sustained(times, f0_midi, max_slope_st_s=3.0, min_dur_s=0.3):
    n = len(f0_midi)
    if n < 3:
        return []
    dt = times[1] - times[0]
    slope = np.full(n, np.nan)
    slope[1:-1] = (f0_midi[2:] - f0_midi[:-2]) / (2 * dt)
    sustained = np.abs(slope) < max_slope_st_s
    sustained &= ~np.isnan(f0_midi)
    segs = []
    i = 0
    min_frames = int(min_dur_s / dt)
    while i < n:
        if sustained[i]:
            j = i
            while j < n and sustained[j]:
                j += 1
            if j - i >= min_frames:
                seg_mid = float(np.nanmedian(f0_midi[i:j]))
                segs.append((i, j, float(times[i]), float(times[j - 1]), seg_mid))
            i = j
        else:
            i += 1
    return segs


# ----------------------------------------------------------------------------
# register events (spec §5.1: jumps, voicing dropouts, tilt discontinuities)
# ----------------------------------------------------------------------------
def clean_contour(times, f0_midi, vflag):
    """Return (repaired_midi, trend_midi): the octave-repaired f0 contour and its intended
    melodic line (a ~450 ms running median). Unvoiced frames stay NaN in `repaired`.

    Octave-doubling/halving errors (common in pyin on real voices) are folded back toward
    the trend so they don't masquerade as register events."""
    from scipy.ndimage import median_filter
    n = len(f0_midi)
    dt = times[1] - times[0] if n > 1 else HOP_S
    voiced = ~np.isnan(f0_midi)
    trend = np.full(n, np.nan)
    if voiced.sum() < 5:
        return f0_midi.copy(), trend
    idx = np.arange(n)
    filled = np.interp(idx, idx[voiced], f0_midi[voiced])
    sm3 = median_filter(filled, size=3, mode="nearest")   # kill 1-frame spikes
    k = int(round(0.45 / dt))
    if k % 2 == 0:
        k += 1
    k = max(3, k)
    trend = median_filter(sm3, size=k, mode="nearest")
    rep = sm3.copy()
    r = rep - trend
    rep[r > 9] -= 12
    rep[r < -9] += 12
    trend = median_filter(rep, size=k, mode="nearest")
    repaired = np.where(voiced, rep, np.nan)
    return repaired, trend


def _dropouts(times, vflag, f0_midi, dt):
    """Short unvoiced gaps bounded by voiced audio (a catch/break in phonation)."""
    n = len(vflag)
    out = []
    i = 0
    while i < n:
        if not vflag[i]:
            j = i
            while j < n and not vflag[j]:
                j += 1
            gap = (j - i) * dt
            before = i > 0 and vflag[i - 1]
            after = j < n and vflag[j]
            if before and after and 0.03 <= gap <= 0.4:
                pb = f0_midi[i - 1]
                pa = f0_midi[j] if j < n else np.nan
                # octave-invariant: an octave-sized "jump" across a gap is almost always a
                # pyin octave slip, not a real register break — don't count it as a break.
                d = abs(pa - pb) if (not np.isnan(pb) and not np.isnan(pa)) else 0.0
                octave_artifact = abs(d - 12) <= 1.5 or abs(d - 24) <= 1.5
                disc = d >= 1.5 and not octave_artifact
                out.append({"time": float(times[i]), "gap_s": gap,
                            "pitch": None if np.isnan(pb) else float(pb),
                            "disc": disc, "used": False})
            i = j
        else:
            i += 1
    return out


def detect_events(times, f0_midi, vflag, tilt_series, thresh_st=1.5, merge_gap_s=0.25):
    """Register events = fast excursions of the octave-repaired f0 away from its intended
    melodic trend (cracks, flips, sudden shifts), optionally corroborated by a voicing
    dropout and/or a spectral-tilt discontinuity. Lone momentary tracking dropouts are NOT
    treated as breaks — only audible gaps (>=120 ms) or gaps with a pitch discontinuity."""
    n = len(f0_midi)
    if n < 3:
        return []
    dt = times[1] - times[0]
    repaired, trend = clean_contour(times, f0_midi, vflag)
    resid = repaired - trend                       # NaN where unvoiced
    flagged = (np.abs(resid) >= thresh_st) & ~np.isnan(resid)

    clusters = []
    i = 0
    while i < n:
        if flagged[i]:
            j = i
            while j < n and flagged[j]:
                j += 1
            clusters.append([i, j])
            i = j
        else:
            i += 1
    merged = []
    for c in clusters:
        if merged and (c[0] - merged[-1][1]) * dt <= merge_gap_s:
            merged[-1][1] = c[1]
        else:
            merged.append(c[:])

    drops = _dropouts(times, vflag, f0_midi, dt)
    events = []
    for a, b in merged:
        seg = np.abs(resid[a:b])
        k = a + int(np.nanargmax(seg))      # deepest point of the excursion
        mag = float(resid[k])
        # pitch/time of the break = the intended line just BEFORE the excursion begins
        # (sampling at the dip would bias the pitch by the excursion depth itself).
        onset = max(0, a - 1)
        pitch = float(trend[onset]) if not np.isnan(trend[onset]) else (
            float(trend[k]) if not np.isnan(trend[k]) else None)
        evidence = ["excursion"]
        for d in drops:
            if abs(d["time"] - times[a]) <= merge_gap_s:
                evidence.append("dropout")
                d["used"] = True
        events.append(_make_event(times[a], pitch, mag, evidence, tilt_series, k, dt))

    for d in drops:  # standalone audible voicing breaks
        if not d["used"] and (d["disc"] or d["gap_s"] >= 0.12):
            events.append(_make_event(d["time"], d["pitch"], 0.0, ["dropout"],
                                      tilt_series, int(d["time"] / dt), dt,
                                      force_type="voicing_break"))
    events.sort(key=lambda e: (e["time_s"] if e["time_s"] is not None else 0.0))
    return events


def _make_event(t, pitch_midi, mag, evidence, tilt_series, k, dt, force_type=None):
    if force_type:
        etype = force_type
    elif "dropout" in evidence or abs(mag) >= 3.0:
        etype = "flip/break"          # phonation actually broke, or a large excursion
    elif abs(mag) >= 1.5:
        etype = "register_shift"
    else:
        etype = "instability"

    # spectral-tilt change across the event (dB/kHz), if a tilt series is available
    tilt_delta = None
    if tilt_series is not None and 0 <= k < len(tilt_series):
        span = max(3, int(0.08 / dt))
        before = _nanmean(tilt_series[max(0, k - 2 * span):max(0, k - span)])
        after = _nanmean(tilt_series[min(len(tilt_series), k + span):
                                     min(len(tilt_series), k + 2 * span)])
        if before is not None and after is not None:
            tilt_delta = after - before

    return {
        "time_s": _round(float(t), 3),
        "midi": None if pitch_midi is None else round(pitch_midi, 1),
        "note": None if pitch_midi is None else zones.midi_to_note_name(pitch_midi),
        "hz": None if pitch_midi is None else _round(zones.midi_to_hz(pitch_midi), 1),
        "type": etype,
        "evidence": sorted(set(evidence)),
        "jump_semitones": _round(mag, 2),
        "tilt_delta_db_per_khz": _round(tilt_delta, 2),
    }


# ----------------------------------------------------------------------------
# spectral series (per frame, aligned to the f0 grid)
# ----------------------------------------------------------------------------
def spectral_series(y, sr, hop, f0):
    import librosa
    S = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=hop)) + EPS
    freqs = librosa.fft_frequencies(sr=sr, n_fft=N_FFT)
    nfr = S.shape[1]
    m = min(nfr, len(f0))
    S = S[:, :m]
    P = 20.0 * np.log10(S)  # dB power per bin

    band = (freqs >= 50) & (freqs <= 5000)
    fb = freqs[band]
    # spectral tilt: slope of dB vs freq (dB per kHz) via least squares per frame
    x = fb - fb.mean()
    denom = np.sum(x * x) + EPS
    tilt = ((x[:, None] * (P[band, :] - P[band, :].mean(axis=0))).sum(axis=0) / denom) * 1000.0

    low = freqs < 1000
    high = (freqs >= 1000) & (freqs <= 5000)
    e_low = (S[low, :] ** 2).sum(axis=0) + EPS
    e_high = (S[high, :] ** 2).sum(axis=0) + EPS
    alpha = 10.0 * np.log10(e_high / e_low)

    sf_band = (freqs >= 2400) & (freqs <= 3200)
    e_sf = (S[sf_band, :] ** 2).sum(axis=0) + EPS
    e_tot = (S ** 2).sum(axis=0) + EPS
    singer_formant = 10.0 * np.log10(e_sf / e_tot)

    # H1-H2 on voiced frames
    h1h2 = np.full(m, np.nan)
    for i in range(m):
        if not np.isnan(f0[i]) and f0[i] > 0:
            b1 = int(round(f0[i] / (sr / N_FFT)))
            b2 = int(round(2 * f0[i] / (sr / N_FFT)))
            if 0 < b1 < S.shape[0] and 0 < b2 < S.shape[0]:
                h1h2[i] = 20 * np.log10(S[b1, i]) - 20 * np.log10(S[b2, i])

    return {"tilt": tilt, "alpha": alpha, "singer_formant": singer_formant, "h1h2": h1h2}, m


# ----------------------------------------------------------------------------
# dynamics
# ----------------------------------------------------------------------------
def dynamics_series(y, hop, m):
    import librosa
    rms = librosa.feature.rms(y=y, frame_length=N_FFT, hop_length=hop)[0]
    rms = rms[:m]
    rms_db = 20.0 * np.log10(rms + EPS)
    return rms_db


# ----------------------------------------------------------------------------
# zone partition + per-region contrasts
# ----------------------------------------------------------------------------
def zone_masks(f0_midi, zone, m):
    f = f0_midi[:m]
    lo, hi = zone.get("low_midi"), zone.get("high_midi")
    voiced = ~np.isnan(f)
    if lo is None:
        return {"below": voiced & False, "in": voiced, "above": voiced & False}
    return {
        "below": voiced & (f < lo),
        "in": voiced & (f >= lo) & (f <= hi),
        "above": voiced & (f > hi),
    }


def region_stats(series_map, masks):
    out = {}
    for name, s in series_map.items():
        s = np.asarray(s, dtype=float)
        rec = {}
        for region, mask in masks.items():
            vals = s[mask[:len(s)]]
            rec[region] = _round(_nanmean(vals), 2)
        if rec.get("in") is not None and rec.get("below") is not None:
            rec["in_minus_below"] = _round(rec["in"] - rec["below"], 2)
        out[name] = rec
    return out


# ----------------------------------------------------------------------------
# vibrato (per sustained segment)
# ----------------------------------------------------------------------------
def vibrato(times, f0_midi, sustained):
    if not sustained:
        return {"detected": False}
    dt = times[1] - times[0]
    rates, extents = [], []
    for (i, j, _t0, _t1, _mid) in sustained:
        seg = f0_midi[i:j]
        seg = seg[~np.isnan(seg)]
        if len(seg) < int(0.3 / dt):
            continue
        seg = seg - np.polyval(np.polyfit(np.arange(len(seg)), seg, 1), np.arange(len(seg)))
        sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        fr = np.fft.rfftfreq(len(seg), dt)
        band = (fr >= 4.0) & (fr <= 8.0)
        if not band.any():
            continue
        pk = np.argmax(sp[band])
        rates.append(float(fr[band][pk]))
        extents.append(float(2.0 * np.std(seg)))
    if not rates:
        return {"detected": False}
    return {
        "detected": True,
        "rate_hz": _round(float(np.median(rates)), 2),
        "extent_semitones": _round(float(np.median(extents)), 2),
        "n_segments": len(rates),
    }


# ----------------------------------------------------------------------------
# Praat quality metrics (jitter, shimmer, HNR, CPPS) — global + per region
# ----------------------------------------------------------------------------
def praat_quality(y, sr, f0_midi, zone, times):
    result = {"global": {}, "by_region": {}, "errors": []}
    try:
        import parselmouth
        from parselmouth.praat import call
    except Exception as e:  # pragma: no cover
        result["errors"].append(f"parselmouth unavailable: {e}")
        return result

    def measure(snd):
        out = {}
        try:
            out["hnr_db"] = _round(call(snd.to_harmonicity_cc(), "Get mean", 0, 0), 2)
        except Exception as e:
            out["hnr_db"] = None
            result["errors"].append(f"hnr: {e}")
        try:
            pp = call(snd, "To PointProcess (periodic, cc)", FMIN_HZ, FMAX_HZ)
            out["jitter_local"] = _round(call(pp, "Get jitter (local)", 0, 0, 1e-4, 0.02, 1.3), 5)
            out["shimmer_local"] = _round(
                call([snd, pp], "Get shimmer (local)", 0, 0, 1e-4, 0.02, 1.3, 1.6), 5)
        except Exception as e:
            out["jitter_local"] = out.get("jitter_local")
            result["errors"].append(f"jitter/shimmer: {e}")
        try:
            pc = call(snd, "To PowerCepstrogram", 60, 0.002, 5000, 50)
            out["cpps_db"] = _round(call(
                pc, "Get CPPS", "yes", 0.02, 0.0005, 60, 330, 0.05,
                "parabolic", 0.001, 0.05, "Straight", "Robust"), 2)
        except Exception as e:
            out["cpps_db"] = None
            result["errors"].append(f"cpps: {e}")
        return out

    snd = parselmouth.Sound(np.ascontiguousarray(y, dtype=np.float64), sampling_frequency=sr)
    result["global"] = measure(snd)

    # per region: longest contiguous voiced span within each band
    masks = zone_masks(f0_midi, zone, len(f0_midi))
    for region, mask in masks.items():
        span = _longest_true_span(mask)
        if span is None:
            continue
        i, j = span
        t0, t1 = float(times[i]), float(times[min(j, len(times) - 1)])
        if t1 - t0 < 0.25:
            continue
        try:
            sub = snd.extract_part(from_time=t0, to_time=t1, preserve_times=False)
            result["by_region"][region] = measure(sub)
        except Exception as e:
            result["errors"].append(f"region {region}: {e}")
    return result


def _longest_true_span(mask):
    best = None
    i = 0
    n = len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            if best is None or (j - i) > (best[1] - best[0]):
                best = (i, j - 1)
            i = j
        else:
            i += 1
    return best


# ----------------------------------------------------------------------------
# formants (Praat Burg) on sustained segments
# ----------------------------------------------------------------------------
def formants(y, sr, sustained):
    if not sustained:
        return {"segments": [], "note": "no sustained segments for formant tracking"}
    try:
        import parselmouth
        from parselmouth.praat import call
        snd = parselmouth.Sound(np.ascontiguousarray(y, dtype=np.float64), sampling_frequency=sr)
        fm = snd.to_formant_burg(time_step=0.01, max_number_of_formants=5,
                                 maximum_formant=5500)
    except Exception as e:
        return {"segments": [], "error": str(e)}
    segs = []
    for (_i, _j, t0, t1, mid) in sustained:
        f1s, f2s = [], []
        t = t0
        while t <= t1:
            f1 = call(fm, "Get value at time", 1, t, "hertz", "linear")
            f2 = call(fm, "Get value at time", 2, t, "hertz", "linear")
            if f1 == f1:
                f1s.append(f1)
            if f2 == f2:
                f2s.append(f2)
            t += 0.02
        segs.append({
            "t0": _round(t0, 2), "t1": _round(t1, 2),
            "note": zones.midi_to_note_name(mid),
            "F1_hz": _round(float(np.median(f1s)), 0) if f1s else None,
            "F2_hz": _round(float(np.median(f2s)), 0) if f2s else None,
            "reliable": mid < zones.note_name_to_midi("C5"),
        })
    return {"segments": segs}


# ----------------------------------------------------------------------------
# quality gates (spec §5.4)
# ----------------------------------------------------------------------------
def quality_gates(y, sr, f0_midi, vflag, zone, hnr_db):
    gates = []
    clip_frac = float(np.mean(np.abs(y) > 0.99))
    if clip_frac > 0.005:
        gates.append({"code": "clipping", "severity": "warn",
                      "message": f"{clip_frac*100:.1f}% of samples near full-scale — recording may be clipped."})
    voiced_s = float(np.sum(vflag)) * HOP_S
    if voiced_s < 5.0:
        gates.append({"code": "insufficient_voiced", "severity": "fail",
                      "message": f"Only {voiced_s:.1f}s of voiced audio (<5s). Ask for a longer take."})
    if hnr_db is not None and hnr_db < 3.0:
        gates.append({"code": "low_snr", "severity": "warn",
                      "message": f"Low harmonics-to-noise ratio ({hnr_db:.1f} dB) — noisy room or distant mic."})
    lo, hi = zone.get("low_midi"), zone.get("high_midi")
    if lo is not None:
        f = f0_midi[~np.isnan(f0_midi)]
        near = np.sum((f >= lo - 4) & (f <= hi + 4)) * HOP_S
        if near < 0.3:
            gates.append({"code": "no_zone_material", "severity": "warn",
                          "message": "Little or no pitch material within ±4 semitones of the passaggio zone."})
    return gates


# ----------------------------------------------------------------------------
# orchestrator
# ----------------------------------------------------------------------------
def analyze_signal(y, sr, profile=None, prior_event_midis=None):
    profile = profile or {}
    errors = []
    y = np.ascontiguousarray(y, dtype=np.float64)
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > 0:
        y_norm = y / peak * 0.98
    else:
        y_norm = y

    times, f0, vflag, vprob, hop = extract_pitch(y_norm, sr)
    f0_midi = _hz_to_midi_arr(f0)

    spec, m = spectral_series(y_norm, sr, hop, f0)
    rms_db = dynamics_series(y_norm, hop, m)
    tilt = spec["tilt"]

    events = detect_events(times[:m], f0_midi[:m], vflag[:m], tilt)
    zone = zones.resolve_zone(profile, events, f0_midi[:m], prior_event_midis)

    sustained = find_sustained(times[:m], f0_midi[:m])
    masks = zone_masks(f0_midi, zone, m)

    series_map = {
        "spectral_tilt_db_per_khz": tilt,
        "alpha_ratio_db": spec["alpha"],
        "singer_formant_db": spec["singer_formant"],
        "h1_h2_db": spec["h1h2"],
        "rms_db": rms_db,
    }
    regions = region_stats(series_map, masks)

    quality = praat_quality(y_norm, sr, f0_midi[:m], zone, times[:m])
    errors += quality.get("errors", [])
    hnr_global = quality.get("global", {}).get("hnr_db")

    vib = vibrato(times[:m], f0_midi[:m], sustained)
    form = formants(y_norm, sr, sustained)
    gates = quality_gates(y_norm, sr, f0_midi[:m], vflag[:m], zone, hnr_global)

    # dynamics through the zone: RMS slope across the in-zone span + entry spike
    dyn = _dynamics_through_zone(rms_db, masks)

    pitch = pitch_summary(f0[:m], f0_midi[:m])
    duration = round(len(y) / sr, 2)
    voiced_ratio = _round(float(np.mean(vflag)), 3)

    biggest = max(events, key=lambda e: abs(e.get("jump_semitones") or 0), default=None)
    headline = {
        "duration_s": duration,
        "voiced_ratio": voiced_ratio,
        "event_count": len(events),
        "biggest_event_semitones": (biggest or {}).get("jump_semitones"),
        "biggest_event_note": (biggest or {}).get("note"),
        "biggest_event_time_s": (biggest or {}).get("time_s"),
        "in_zone_cpps_db": (quality.get("by_region", {}).get("in", {}) or {}).get("cpps_db"),
        "tilt_delta_in_minus_below": regions.get("spectral_tilt_db_per_khz", {}).get("in_minus_below"),
        "zone_source": zone.get("source"),
        "zone_note_range": None if zone.get("low_note") is None
        else f"{zone['low_note']}-{zone['high_note']}",
    }

    return {
        "schema": "passaggio-metrics/0.1",
        "meta": {"sr": sr, "hop_s": HOP_S, "peak_pre_norm": _round(peak, 4)},
        "timing": {"duration_s": duration, "voiced_ratio": voiced_ratio,
                   "voiced_seconds": _round(float(np.sum(vflag)) * HOP_S, 1),
                   "sustained_segments": len(sustained)},
        "pitch": pitch,
        "zone": zone,
        "events": events,
        "quality": quality,
        "spectral_by_region": regions,
        "dynamics": dyn,
        "vibrato": vib,
        "formants": form,
        "quality_gates": gates,
        "headline": headline,
        "errors": errors,
        "_series": {  # kept for plotting; stripped before returning to the model if large
            "times": [round(float(t), 4) for t in times[:m]],
            "f0_hz": [None if np.isnan(v) else round(float(v), 2) for v in f0[:m]],
            "rms_db": [round(float(v), 2) for v in rms_db],
        },
    }


def _dynamics_through_zone(rms_db, masks):
    in_mask = masks["in"]
    idx = np.where(in_mask[:len(rms_db)])[0]
    if idx.size < 3:
        return {"in_zone_rms_slope_db_per_s": None, "entry_spike_db": None}
    seg = rms_db[idx]
    x = np.arange(len(seg)) * HOP_S
    slope = float(np.polyfit(x, seg, 1)[0])
    below = masks["below"]
    below_idx = np.where(below[:len(rms_db)])[0]
    baseline = float(np.nanmedian(rms_db[below_idx])) if below_idx.size else float(np.nanmedian(rms_db))
    entry_spike = float(np.nanmax(seg)) - baseline
    return {"in_zone_rms_slope_db_per_s": _round(slope, 2),
            "entry_spike_db": _round(entry_spike, 2)}
