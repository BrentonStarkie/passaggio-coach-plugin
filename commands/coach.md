---
description: Analyse your latest (or a named) passaggio take and give targeted coaching.
argument-hint: "[audio-file-or-take-id]"
---

Run the **passaggio-coach** skill's `/coach` workflow.

Target take: **$ARGUMENTS**
(If empty: the newest unanalysed take in the configured takes folder — or, if no library is set
up, ask the user for the audio file.)

Follow the skill's `/coach` flow exactly:
1. Find / ingest the take.
2. Analyse it with `analyze.py`; `Read` the pitch plot to sanity-check before coaching.
3. Honour any `fail` quality gate — give retake guidance instead of coaching noise.
4. Interpret via `references/pedagogy.md`: 2–4 **timestamped** observations, dominant fault first.
5. Compare against history (like-with-like) if takes exist; lead with what improved.
6. Ask ≤3 clarifying questions where the acoustics are genuinely ambiguous (anchor each to a timestamp).
7. Prescribe 2–3 exercises **at the singer's flagged pitches**.
8. Persist the summary + Q&A (library mode).

Keep the voice encouraging and specific; cite the metric behind every claim; never give medical advice.
