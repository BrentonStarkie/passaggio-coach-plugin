"""Plots: f0 contour (zone shaded, register events flagged) and spectrogram.

Uses the Agg backend so it runs headless on macOS and Windows with no display.
Every claim in coaching feedback should be traceable to a marker on these plots (spec §5.3).
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from . import zones  # noqa: E402


def _note_yticks(lo_hz, hi_hz):
    import math
    lo_m = int(math.floor(zones.hz_to_midi(lo_hz)))
    hi_m = int(math.ceil(zones.hz_to_midi(hi_hz)))
    ticks, labels = [], []
    for m in range(lo_m, hi_m + 1):
        if m % 12 in (0, 2, 4, 5, 7, 9, 11):  # natural notes only, keep it readable
            ticks.append(zones.midi_to_hz(m))
            labels.append(zones.midi_to_note_name(m))
    return ticks, labels


def plot_pitch(metrics, out_path, title="take"):
    series = metrics.get("_series", {})
    t = np.asarray(series.get("times", []), dtype=float)
    f0 = np.asarray([np.nan if v is None else v for v in series.get("f0_hz", [])], dtype=float)
    rms = np.asarray(series.get("rms_db", []), dtype=float)
    zone = metrics.get("zone", {})

    fig, ax = plt.subplots(figsize=(11, 4.5))
    if np.isfinite(f0).any():
        ax.plot(t, f0, color="#1f77b4", lw=1.6, label="f0")
        ax.set_yscale("log")
        finite = f0[np.isfinite(f0)]
        lo_hz, hi_hz = float(np.nanmin(finite)) * 0.9, float(np.nanmax(finite)) * 1.1
        ticks, labels = _note_yticks(lo_hz, hi_hz)
        ax.set_yticks(ticks)
        ax.set_yticklabels(labels)
        ax.set_ylim(lo_hz, hi_hz)

    if zone.get("low_hz"):
        ax.axhspan(zone["low_hz"], zone["high_hz"], color="#ffcc66", alpha=0.30,
                   label=f"passaggio zone ({zone.get('low_note')}–{zone.get('high_note')}, {zone.get('source')})")

    for ev in metrics.get("events", []):
        if ev.get("time_s") is None:
            continue
        ax.axvline(ev["time_s"], color="#d62728", ls="--", lw=1.1, alpha=0.8)
        label = f"{ev.get('note','?')}  {ev.get('jump_semitones','?')} st\n{ev.get('type','')}"
        yv = ev.get("hz") or (float(np.nanmedian(f0[np.isfinite(f0)])) if np.isfinite(f0).any() else 200)
        ax.annotate(label, xy=(ev["time_s"], yv), xytext=(4, 8),
                    textcoords="offset points", fontsize=8, color="#d62728")

    if rms.size:
        ax2 = ax.twinx()
        ax2.plot(t[:len(rms)], rms, color="#2ca02c", lw=0.9, alpha=0.5)
        ax2.set_ylabel("RMS (dB)", color="#2ca02c", fontsize=9)
        ax2.tick_params(axis="y", labelcolor="#2ca02c", labelsize=8)

    ax.set_xlabel("time (s)")
    ax.set_ylabel("pitch")
    ax.set_title(f"Pitch contour — {title}")
    ax.legend(loc="upper right", fontsize=8, framealpha=0.9)
    ax.grid(True, which="both", axis="x", alpha=0.2)
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    return out_path


def plot_spectrogram(y, sr, metrics, out_path, title="take"):
    import librosa
    import librosa.display
    S = librosa.amplitude_to_db(np.abs(librosa.stft(y, n_fft=2048, hop_length=int(sr * 0.01))),
                                ref=np.max)
    fig, ax = plt.subplots(figsize=(11, 4.5))
    img = librosa.display.specshow(S, sr=sr, hop_length=int(sr * 0.01),
                                   x_axis="time", y_axis="log", ax=ax, cmap="magma")
    fig.colorbar(img, ax=ax, format="%+2.0f dB")
    ax.set_ylim(80, 6000)

    zone = metrics.get("zone", {})
    if zone.get("low_hz"):
        ax.axhline(zone["low_hz"], color="#66ccff", ls="-", lw=1.0, alpha=0.8)
        ax.axhline(zone["high_hz"], color="#66ccff", ls="-", lw=1.0, alpha=0.8)
    for ev in metrics.get("events", []):
        if ev.get("time_s") is not None:
            ax.axvline(ev["time_s"], color="#ffffff", ls="--", lw=1.0, alpha=0.7)
    ax.set_title(f"Spectrogram — {title}")
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    return out_path
