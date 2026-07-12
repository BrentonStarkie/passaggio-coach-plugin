"""Pitch math, voice-type passaggio zones, and infer-from-takes zone logic.

All frequencies in Hz, pitches in MIDI note numbers internally. Note names use sharps
(e.g. "F#4"); flats are accepted on input.
"""
from __future__ import annotations

import math
from typing import Optional

A4_HZ = 440.0
A4_MIDI = 69
_NAMES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_NAME_TO_PC = {
    "C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "FB": 4,
    "F": 5, "F#": 6, "GB": 6, "G": 7, "G#": 8, "AB": 8, "A": 9, "A#": 10,
    "BB": 10, "B": 11, "CB": 11,
}

# Secondo passaggio zones per voice type (spec §6). Approximate, override-able.
VOICE_ZONES = {
    "soprano":  ("E5", "F#5"),
    "mezzo":    ("D5", "E5"),
    "contralto": ("C#5", "D5"),
    "tenor":    ("D4", "G4"),
    "baritone": ("B3", "E4"),
    "bass":     ("A3", "D4"),
}
# Optional primo passaggio hints (informational).
PRIMO_HINTS = {"soprano": "Eb4"}


def hz_to_midi(hz: float) -> float:
    return A4_MIDI + 12.0 * math.log2(hz / A4_HZ)


def midi_to_hz(m: float) -> float:
    return A4_HZ * (2.0 ** ((m - A4_MIDI) / 12.0))


def note_name_to_midi(name: str) -> int:
    name = name.strip()
    letter = name[0].upper()
    accidental = ""
    if len(name) > 1 and name[1] in "#bB":
        accidental = "#" if name[1] == "#" else "B"
    octave = int(name[len(letter) + len(accidental):])
    key = (letter + accidental).upper()
    pc = _NAME_TO_PC[key]
    return (octave + 1) * 12 + pc


def midi_to_note_name(m: float) -> str:
    m = int(round(m))
    return f"{_NAMES_SHARP[m % 12]}{m // 12 - 1}"


def hz_to_note_name(hz: float) -> str:
    return midi_to_note_name(hz_to_midi(hz))


def _zone_from_notes(low_note: str, high_note: str, source: str, confidence: str) -> dict:
    lo_m = note_name_to_midi(low_note)
    hi_m = note_name_to_midi(high_note)
    return {
        "low_hz": round(midi_to_hz(lo_m), 2),
        "high_hz": round(midi_to_hz(hi_m), 2),
        "low_midi": lo_m,
        "high_midi": hi_m,
        "low_note": midi_to_note_name(lo_m),
        "high_note": midi_to_note_name(hi_m),
        "source": source,
        "confidence": confidence,
    }


def zone_for_voice_type(voice_type: str) -> Optional[dict]:
    vt = (voice_type or "").strip().lower()
    if vt in VOICE_ZONES:
        lo, hi = VOICE_ZONES[vt]
        return _zone_from_notes(lo, hi, source="voice_type", confidence="high")
    return None


def resolve_zone(profile: dict, events: list, f0_midi_values, prior_event_midis=None) -> dict:
    """Determine the working passaggio zone for this take.

    Priority: explicit override > known voice_type > infer from register-event cluster
    (this take + any prior events) > nominal window centred on the middle of the sung range.

    profile: {"voice_type": str|None, "passaggio_override": ["D4","G4"]|None}
    events: list of event dicts from metrics (each has "midi").
    f0_midi_values: array-like of voiced f0 in MIDI (for the nominal fallback).
    prior_event_midis: optional list of event pitches (MIDI) from earlier takes.
    """
    override = (profile or {}).get("passaggio_override")
    if override and len(override) == 2:
        return _zone_from_notes(override[0], override[1], source="override", confidence="high")

    vt_zone = zone_for_voice_type((profile or {}).get("voice_type") or "")
    if vt_zone:
        return vt_zone

    # Infer from where register events cluster (this take + prior history).
    pitches = [e["midi"] for e in (events or []) if e.get("midi") is not None]
    if prior_event_midis:
        pitches = pitches + list(prior_event_midis)
    pitches = [p for p in pitches if p is not None]

    if len(pitches) >= 1:
        pitches_sorted = sorted(pitches)
        mid = pitches_sorted[len(pitches_sorted) // 2]  # median
        pad = 2.0  # semitones each side of the cluster
        conf = "medium" if len(pitches) >= 3 else "low"
        return {
            "low_hz": round(midi_to_hz(mid - pad), 2),
            "high_hz": round(midi_to_hz(mid + pad), 2),
            "low_midi": mid - pad,
            "high_midi": mid + pad,
            "low_note": midi_to_note_name(mid - pad),
            "high_note": midi_to_note_name(mid + pad),
            "source": "inferred",
            "confidence": conf,
            "n_events_used": len(pitches),
        }

    # Nominal fallback: centre a 4-st window on the middle of the sung range.
    vals = [float(v) for v in f0_midi_values if v == v]  # drop NaN
    if vals:
        vals_sorted = sorted(vals)
        centre = vals_sorted[len(vals_sorted) // 2]
        return {
            "low_hz": round(midi_to_hz(centre - 2), 2),
            "high_hz": round(midi_to_hz(centre + 2), 2),
            "low_midi": centre - 2,
            "high_midi": centre + 2,
            "low_note": midi_to_note_name(centre - 2),
            "high_note": midi_to_note_name(centre + 2),
            "source": "nominal",
            "confidence": "low",
        }
    return {
        "low_hz": None, "high_hz": None, "low_midi": None, "high_midi": None,
        "low_note": None, "high_note": None, "source": "unknown", "confidence": "none",
    }
