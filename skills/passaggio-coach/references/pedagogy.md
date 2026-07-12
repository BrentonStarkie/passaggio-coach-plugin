# Passaggio pedagogy — evidence → interpretation → exercise

This is the interpretation layer. It maps **what the analysis measured** (fields in
`metrics.json`) to a **likely fault** and to **exercises**. The scripts have no opinions; the
judgement lives here and can be tuned without touching code.

Two rules that override everything below:

1. **Every observation must cite a timestamped metric.** Say "at 0:07.7, F♯4, the tone dropped
   4 semitones (`events[0]`)", never "your break is bad".
2. **Acoustic proxies, not physiology.** Say "consistent with carried chest weight", never
   "your vocal folds are…". See `../references/metrics.md` and the README limitations.

Acoustics genuinely cannot distinguish some cases (an intentional head-voice shift vs an
involuntary flip; a stylistic straight tone vs tension). When it matters, ask — see
"Interactive clarification" in `SKILL.md`.

---

## Fault → evidence → exercise map

Match the strongest-evidence row(s). Usually one or two faults dominate a take; don't force all
six. Every exercise must be re-anchored to the singer's **actual** flagged pitches.

### 1. Flip / break (abrupt release of weight to falsetto)
- **Evidence:** an `events[]` entry with `type: "flip/break"`, a large `jump_semitones`
  (≥ ~3, usually downward/negative), often `evidence` includes `"dropout"`, and
  `tilt_delta_db_per_khz` goes **more negative** (spectrum steepens = tone thinned) across it.
- **Exercises:** descending octave slides on "oo"; messa di voce on the note **just below** the
  flagged pitch; slow sirens straight through the seam at mp. Goal: cross without dumping weight.

### 2. Carrying chest weight / pushing up into the zone
- **Evidence:** `spectral_by_region.spectral_tilt_db_per_khz.in_minus_below` ≈ 0 or positive
  (tilt does **not** steepen entering the zone — the tone never "turns over"); often with
  `dynamics.entry_spike_db` positive and/or `dynamics.in_zone_rms_slope_db_per_s` positive
  (getting louder into the zone), and `quality.by_region.in.shimmer_local` up vs `below`.
- **Exercises:** lip trills / straw (SOVT) ascents; start the rebalance to a lighter mix
  **3–4 semitones below** the zone, not at it; "ng"-onset scales. Goal: lighten earlier.

### 3. No vowel modification (open vowel splatting)
- **Evidence:** `formants.segments` show **F1 not dropping** as pitch rises through the zone
  (an open vowel held wide open). Only trust where `reliable: true` (below ~C5).
- **Exercises:** vowel shading drills — "ah→uh/aw", "eh→ih" — through the flagged pitches;
  short closed-vowel repertoire snippets. Goal: let F1 track down so the vowel "covers".

### 4. Instability localised at the passaggio
- **Evidence:** `quality.by_region.in.cpps_db` and/or `.hnr_db` **drop in-zone only** (stable
  `below`, collapsing `in`); jitter/shimmer rise in-zone. No large `jump` — the pitch holds but
  the tone destabilises.
- **Exercises:** SOVT (straw, lip trill) at the **exact** flagged pitches; sustained mid-zone
  notes at mp; small "sirens" spanning ±2 st around the zone. Goal: steady the seam.

### 5. Tension under load (jaw / tongue / larynx)
- **Evidence:** `vibrato.extent_semitones` collapses in the zone (a free vibrato below goes
  straight/locked in-zone), often with rising jitter. Distinguish from a deliberate straight
  tone by asking (clarification).
- **Exercises:** "yah-yah" jaw release; yawn-sigh onsets; tongue-out sirens. Goal: release the
  articulators so the tone stays free under load.

### 6. Compensating with air pressure (over-blowing the seam)
- **Evidence:** `dynamics.entry_spike_db` clearly positive — a loudness spike right at zone
  entry — with the crossing otherwise intact.
- **Exercises:** decrescendo drills **into** the zone; appoggio / suspended-breath focus;
  "hoo" onsets at mp. Goal: cross on steady support, not a pressure kick.

---

## Prescribing exercises
- **Anchor to real pitches.** "Slide E♭4→A♭4, since your event cluster is at F4" — read the
  pitch from `events[].note` (or `zone.low_note`/`high_note`).
- **2–3 exercises max.** Pick for the dominant fault; add one for a secondary if strong.
- **Always name one thing that improved** (from the comparison, if history exists), even in a
  rough take. Coach voice: encouraging, specific, never punitive.
- If `zone.confidence` is `low`/`none` or `zone.source` is `nominal`, say the zone is a best
  guess and that it will sharpen over more takes (or ask the singer's voice type).
