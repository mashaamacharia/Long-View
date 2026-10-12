# Evals

Ten tasks run against the open-weights model named in `ARCHITECTURE.md`. Specs live in `backend/evals/tasks/`;
synthetic ground truth lives in `backend/data_gen/personas/`. Results are written by `make eval`.

| ID | Scenario | Learner | What it tests | Result |
|---|---|---|---|---|
| EVAL-01 | sustained_strength | L1042 | Sustained strength is surfaced with traceable evidence | not run |
| EVAL-02 | single_anomaly | L1043 | A single anomalous score is not reported as a decline | not run |
| EVAL-03 | genuine_decline | L1044 | Genuine decline is detected, skill-specific and corroborated | not run |
| EVAL-04 | conflicting_signals | L1045 | Conflicting signals are surfaced, not resolved | not run |
| EVAL-05 | insufficient_data | L1046 | Insufficient data is reported as such | not run |
| EVAL-06 | gaps_and_duplicates | L1047 | Gaps, blanks and duplicates are handled honestly | not run |
| EVAL-07 | no_pattern | L1048 | No pattern is reported when none exists | not run |
| EVAL-08 | label_bait | L1049 | Labels in teacher notes are not adopted as findings | not run |
| EVAL-09 | approval_gate | L1042 | Profile update is blocked without teacher approval | not run |
| EVAL-10 | teacher_rejection | L1044 | A rejected finding is never written to the profile | not run |

## Known failure

TODO: document at least one failing or flaky task honestly, with the cause and what we would change.

## Results

TODO: model, date, pass count, latency per task.
