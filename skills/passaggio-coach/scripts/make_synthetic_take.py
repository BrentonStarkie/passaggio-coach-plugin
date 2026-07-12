#!/usr/bin/env python3
"""Generate synthetic 'passaggio take' WAVs with KNOWN ground truth.

Development / calibration tool — NOT part of the coaching flow. Uses it to:
  * verify an install works end-to-end without needing a real recording;
  * sanity-check the analysis (a planted break at a known time/pitch/size should be detected);
  * calibrate thresholds in references/metrics.md against controlled inputs.

Voice-like additive synthesis: an arched pitch glide through a passaggio zone, vowel formants
(with a floor so the fundamental is present and realistic), vibrato, jitter/shimmer, breath
noise, and a controllable register 'break' (voicing dropout + downward flip + spectral-tilt
discontinuity) at a known time and pitch.

Depends only on numpy + soundfile.

Usage:
  python make_synthetic_take.py <out_dir>          # writes flip4 / flip2 / carry + ground_truth.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100
VOWELS = {  # (centre Hz, bandwidth Hz, amplitude)
    "ah": [(700, 110, 1.0), (1220, 90, 0.6), (2600, 120, 0.25), (3300, 150, 0.2)],
    "ee": [(300, 60, 1.0), (2300, 100, 0.7), (3000, 120, 0.3), (3500, 150, 0.2)],
    "oo": [(320, 60, 1.0), (800, 90, 0.5), (2500, 120, 0.15), (3300, 150, 0.1)],
}


def formant_gain(freq, formants):
    g = np.zeros_like(freq, dtype=float)
    for fc, bw, a in formants:
        half = bw / 2.0
        g += a * (half * half) / ((freq - fc) ** 2 + half * half)
    return g


def make_take(path, crack_st=4.0, vowel="ah", break_hz=370.0, dur=20.0,
              f0_lo=196.0, f0_top_st=15.0, tilt_chest=1.0, tilt_head=2.2,
              carry_chest=False, jitter=0.004, shimmer=0.04, seed=0):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR

    half = dur / 2.0
    arch = np.where(t <= half, t / half, (dur - t) / half) * f0_top_st  # 0..top..0 semitones
    vib = 0.25 * np.sin(2 * np.pi * 5.5 * t)
    jit = np.cumsum(rng.normal(0, jitter, n))
    jit -= jit.mean()
    f0 = f0_lo * 2.0 ** ((arch + vib + jit) / 12.0)

    idx = int(np.argmin(np.abs(f0[: n // 2] - break_hz)))  # first ascending crossing
    t_break = idx / SR

    amp_gate = np.ones(n)
    f0_mod = f0.copy()
    tilt = np.full(n, tilt_chest)
    if not carry_chest:
        drop_len = int(0.04 * SR)
        crack_len = int(0.18 * SR)
        amp_gate[idx:idx + drop_len] *= 0.04                      # voicing dropout
        cs = idx + drop_len
        ce = cs + crack_len
        f0_mod[cs:ce] = f0[cs:ce] * 2.0 ** (-crack_st / 12.0)     # downward flip
        tilt[cs:] = tilt_head                                     # tilt discontinuity
    else:
        cs = idx

    phase = 2 * np.pi * np.cumsum(f0_mod) / SR
    sig = np.zeros(n)
    for h in range(1, 31):
        fh = h * f0_mod
        mask = fh < 0.45 * SR
        src = 1.0 / (h ** tilt)
        fg = np.maximum(formant_gain(fh, VOWELS[vowel]), 0.6)     # keep fundamental present
        sig += np.where(mask, src * fg * np.sin(h * phase), 0.0)

    shim = 1.0 + shimmer * np.sin(2 * np.pi * 5.5 * t + 0.7) + rng.normal(0, shimmer * 0.5, n)
    sig *= shim * amp_gate

    noise = np.convolve(rng.normal(0, 1, n), np.ones(8) / 8, mode="same")
    sig = sig + 0.01 * noise * (np.max(np.abs(sig)) / (np.std(noise) + 1e-9))

    env = np.ones(n)
    fade = int(0.15 * SR)
    env[:fade] = np.linspace(0, 1, fade)
    env[-fade:] = np.linspace(1, 0, fade)
    sig *= env

    if carry_chest:  # loudness spike entering the zone (push)
        w = np.zeros(n)
        s0, s1 = cs, min(n, cs + int(1.0 * SR))
        w[s0:s1] = np.hanning((s1 - s0) * 2)[: s1 - s0]
        sig *= (1.0 + 0.4 * w)

    sig = sig / (np.max(np.abs(sig)) + 1e-9) * 0.7
    sf.write(str(path), sig.astype(np.float32), SR, subtype="PCM_16")
    return {"path": str(path), "t_break_s": round(t_break, 3),
            "break_note_hz": round(float(f0[idx]), 1),
            "crack_st": 0.0 if carry_chest else crack_st, "vowel": vowel,
            "fault": "carry_chest" if carry_chest else "flip"}


def main(argv):
    out = Path(argv[1]) if len(argv) > 1 else Path("synthetic_takes")
    out.mkdir(parents=True, exist_ok=True)
    truth = [
        make_take(out / "take_flip4.wav", crack_st=4.0, seed=1),
        make_take(out / "take_flip2.wav", crack_st=2.0, seed=2),
        make_take(out / "take_carry.wav", carry_chest=True, seed=3),
    ]
    (out / "ground_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    print(json.dumps(truth, indent=2))


if __name__ == "__main__":
    main(sys.argv)
