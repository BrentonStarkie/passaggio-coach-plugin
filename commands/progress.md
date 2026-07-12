---
description: Trend report across your passaggio take library (is the break improving?).
argument-hint: "[exercise-tag]"
---

Run the **passaggio-coach** skill's `/progress` workflow.

Optional exercise tag to keep the comparison like-with-like: **$ARGUMENTS**

Produce a trend report:
- Run `compare.py --trend` (add `--tag $ARGUMENTS` if a tag was given) over the take library.
- Narrate the arc of the headline metrics — especially crack size (`biggest_event_semitones`),
  in-zone stability (`cpps`/`hnr`), and the loudness spike at zone entry (`entry_spike_db`).
- State the next milestone concretely.
- **Guard against noise**: don't celebrate single-take wiggles below the noise floors in
  `references/metrics.md`; prefer trends over ≥3 like-tagged takes. If there isn't enough
  history yet, say so and suggest recording a few more like-tagged takes.
