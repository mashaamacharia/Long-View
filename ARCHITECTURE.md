# Architecture

> Work in progress. Sections are added as each layer lands.

## Pattern detection (`detect_patterns`)

The model never does arithmetic. Everything below is deterministic Python in
`backend/app/mcp_server/analysis/`, unit-tested, and reproducible. The LLM plans, judges whether to
gather more evidence, and writes the teacher-facing summary.

**Pipeline per learner and skill**

1. **Normalise and de-duplicate.** Scores become percentages of their own maximum, so a quiz out of
   10 and a project out of 100 compare. Rows repeated by two imports count once. Blank scores are
   counted, never filled in.
2. **Screen single anomalous scores.** Quizzes and coursework are screened separately (different
   conditions). Each group is detrended with a Theil-Sen line; a point is flagged only if it is
   extreme by robust z-score (MAD) **and** at least 20 points off the learner's own line. Flagged
   scores are excluded from the trend and reported as an `anomaly`, together with same-term teacher
   observations and any attendance dip. The engine flags; it does not explain.
3. **Trend.** Average within each term, then Theil-Sen slope, Mann-Kendall significance
   (p < 0.05), and an early-vs-late change of at least 8 points. Both gates are required: a
   statistically significant but tiny drift is not reported, and a large swing in an erratic series
   is not reported. Term positions are real calendar positions, so missing terms are never
   interpolated.
4. **Sufficiency.** At least 4 terms and 8 scored records, otherwise the output is an
   `insufficient` pattern that lists what is missing.
5. **Conflicts.** (a) Quiz vs coursework averages in the same skill differing by 20+ points,
   consistently across terms. (b) Teacher notes containing trait or ability labels, set against the
   measured record. Conflicts are surfaced for the teacher, never resolved.

**Evidence strength** describes the data, not the learner: `high` needs 6+ terms, 15+ records, 2+
independent channels (scores, teacher observations, attendance) and no missing terms inside the
span; `medium` is reportable but short, single-channel or gapped; `none` is below the minimum.

**Output discipline.** Every pattern stores its evidence rows (`evidence` table) and a caveats list
(gaps, excluded outliers, removed duplicates). Statements describe measured change only: no
causes, no labels. Label words found in teacher notes are never repeated in a statement. Patterns
a teacher has already reviewed are not overwritten by later runs. The tool response is compact
(counts and term averages, not row dumps) to fit a small local model's context window.
