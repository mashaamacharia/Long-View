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

## Tool contracts and safety rules (`learner-intelligence-mcp`)

| Tool | Reads / writes | Rules enforced server-side |
|---|---|---|
| `get_learner_timeline` | reads | compact, term-ordered records and observations |
| `detect_patterns` | writes candidate patterns + evidence | deterministic; patterns a teacher has decided are never overwritten |
| `get_evidence` | reads | counts plus an earliest/latest sample; label-bearing teacher notes are withheld and flagged |
| `flag_for_teacher_review` | writes a pending review | refuses `insufficient` findings, other learners' patterns, already-decided patterns and empty reasons; idempotent while pending; changes no learner data |
| `update_learner_profile` | the only write to the profile | requires a teacher-approved `approval_id` (checked in the server, not the model) |

**Why the rules live in the server.** The model can be wrong or be talked into things; the server
cannot. A teacher request to "skip the review" reaches the same refusal as a model mistake.

**Withheld notes.** Teacher notes containing trait or ability labels are returned to the agent as
"characterising language withheld", so the agent can report that such notes exist and conflict with
the measured record without repeating them as findings. Teachers read the original in the dashboard.

**Audit.** Every call, including refusals (`ok: false`) and calls with an unknown `run_id`, writes a
`tool_calls` row. Audit failures are logged and never break the tool.

## Approval flow (the human gate)

```
agent                          teacher (dashboard / API)                 server
-----                          -------------------------                 ------
detect_patterns ───────────────────────────────────────────────────────► candidate patterns + evidence
flag_for_teacher_review ───────────────────────────────────────────────► review: pending, pattern: in_review
        (run pauses)           GET  /api/reviews               ◄── pending queue
                               GET  /api/reviews/{id}          ◄── full evidence, original notes
                               POST /api/reviews/{id}/decision ──────► approvals row (one per decision)
                                    approved       → pattern: approved   ┐
                                    rejected       → pattern: rejected   ├ recorded, audited
                                    more_evidence  → pattern: proposed   ┘ (agent may refresh and re-flag)
update_learner_profile(approval_id) ───────────────────────────────────► writes ONLY if the approval is
                                                                         'approved', for this pattern and
                                                                         this learner; else refuses
```

**What the gate guarantees (each is covered by a test, and each check was mutation-tested):**
an approval must exist and say `approved`; it unlocks only the pattern and learner its review was
about; the pattern must be in the `approved` state; one approval is applied once (replays are
reported, never duplicated); a summary containing trait or ability labels is refused without
burning the approval; every decision and every refusal is on the audit trail. Rejected and
"more evidence" decisions are stored but unlock nothing.

**What it does not do (demo scope).** There is no login: the dashboard supplies `teacher_id`.
In production the decision endpoint would sit behind authentication and the approval would carry
the authenticated identity. Decisions use `SELECT ... FOR UPDATE` to prevent double-deciding; that
path is exercised on SQLite in tests and should be checked once against Postgres.

**Two views of the same evidence.** The agent's `get_evidence` is sampled and withholds notes
that contain labels; the teacher's review view (`app/services/evidence.py`, same code, different
arguments) is complete and shows the original notes, marked `characterising_language`.
