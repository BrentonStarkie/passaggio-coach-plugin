# Metrics reference — what each number means

Field paths below are into `metrics.json` (written by `analyze.py`). The core idea (spec §5.2)
is the **delta at the zone**: most fields are reported `below` / `in` / `above` the passaggio
zone, plus `in_minus_below`. The interesting signal is almost always how a metric *changes*
entering the zone, not its absolute value.

Interpretation heuristics are proxies. Ranges are rough guides for a healthy adult voice on a
phone mic in a quiet room — calibrate against the singer's own baseline over takes.

## Pitch & events
- `pitch.*` — sung range, median f0, low/high notes.
- `events[]` — register events, each `{time_s, note, hz, midi, type, evidence, jump_semitones,
  tilt_delta_db_per_khz}`.
  - `type`: `flip/break` (phonation broke or a ≥3 st excursion), `register_shift` (1.5–3 st
    excursion), `instability` (smaller), `voicing_break` (an audible catch with a pitch
    discontinuity).
  - `jump_semitones` — signed excursion depth from the intended line. Negative = dropped
    (typical flip to a lighter register). This is the number to trend for "is the crack
    shrinking?".
  - `evidence`: `excursion` (pitch deviated) and/or `dropout` (phonation cut out briefly).
  - Detection is robust to pyin octave errors (contour is octave-repaired first). It flags
    **deviations from the intended melodic line**, so smooth slides/glides do not fire.

## Quality (Praat, via parselmouth) — `quality.global`, `quality.by_region.{below,in,above}`
- `hnr_db` — harmonics-to-noise ratio. Higher = clearer/less breathy. ~>20 dB is clean; a
  drop **in-zone only** suggests instability at the seam. (<3 dB globally → low-SNR gate.)
- `cpps_db` — smoothed cepstral peak prominence; a robust overall "clarity/periodicity" index.
  Higher = more stable phonation. A localized in-zone drop is the classic "passaggio wobble".
- `jitter_local`, `shimmer_local` — cycle-to-cycle pitch/amplitude perturbation. Lower = steadier.
  Rough clean speech: jitter <~0.01, shimmer <~0.05; rising in-zone = pressed/unstable there.

## Spectral balance — `spectral_by_region.<metric>.{below,in,above,in_minus_below}`
- `spectral_tilt_db_per_khz` — overall spectral slope (negative = energy falls with frequency).
  **Steepening (more negative) into the zone = the tone "turned over"** (good passaggio).
  `in_minus_below` ≈ 0 or positive = chest weight carried up (tone stayed bright/heavy).
- `alpha_ratio_db` — high-band vs low-band energy. More negative = darker; a big drop can mean
  over-covering.
- `singer_formant_db` — 2.4–3.2 kHz energy vs total. Higher = more "ring"/carrying power.
- `h1_h2_db` — first vs second harmonic level. Larger = more open/relaxed; small/negative =
  pressed. Watch its in-vs-below change.

## Dynamics — `dynamics`
- `entry_spike_db` — loudest in-zone RMS minus the below-zone baseline. A clear positive spike
  = pushing/over-blowing at zone entry.
- `in_zone_rms_slope_db_per_s` — getting louder (+) or backing off (−) through the zone.

## Vibrato — `vibrato`
- `rate_hz` (~5–7 typical), `extent_semitones` (~0.3–1.0 typical), measured on sustained
  segments. Extent collapsing in-zone (free below, straight in) suggests tension under load —
  but confirm it isn't a deliberate straight tone.

## Formants — `formants.segments[]`
- `F1_hz`, `F2_hz` medians on sustained notes; `reliable` is `false` above ~C5. Track whether
  F1 **drops** as pitch rises (vowel modification) vs stays wide (open-vowel splat).

## Quality gates — `quality_gates[]`
Each `{code, severity, message}`. `fail` = don't coach on noise, ask for a retake:
`insufficient_voiced` (<5 s voiced). `warn` = caveat but proceed: `clipping`, `low_snr`,
`no_zone_material`. Always surface `fail` gates before any coaching.

## What counts as a *meaningful* change (comparison noise floors)
From `compare.py` (`NOISE`). Deltas smaller than these are "no meaningful change" — do not
coach on them:

| Metric | Floor |
|---|---|
| `biggest_event_semitones` | 0.6 st |
| `event_count` | 1 |
| `in_zone_cpps_db` | 1.0 dB |
| `in_zone_hnr_db` | 2.0 dB |
| `tilt_in_minus_below` | 0.6 dB/kHz |
| `in_zone_rms_slope_db_per_s` | 0.7 |
| `entry_spike_db` | 1.5 dB |
| `voiced_ratio` | 0.05 |
