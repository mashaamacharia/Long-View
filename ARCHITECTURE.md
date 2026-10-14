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

## The agent (`backend/app/agent/`)

```
fetch_timeline -> detect -> investigate -> triage -> flag -> await_teacher -> apply -> summarise -> END
                               ^   ^__________|  (gaps)                         |
                               |_____________ more evidence (max 2 rounds) _____|
```

**Division of labour.** The model proposes; the runtime disposes.

| Step | Model | Code |
|---|---|---|
| Which tool to call next (`investigate`) | chooses among 4 read-only tools | validates every call, then guarantees minimum coverage itself |
| Which findings go to a teacher | none | `policy.select_candidates` (approvable kinds, enough evidence, not already decided) |
| What is written to a profile | none | only the approved finding's own statement, only with the teacher's `approval_id` |
| The summary | drafts prose from a fact sheet | verifier rejects it, else a deterministic template |

**Tool boundary** (`tools.py`, enforced in code, not in the prompt)
- Two MCP servers behind one router: ours (streamable HTTP) and the external
  `@modelcontextprotocol/server-filesystem` (stdio, pre-installed in the image).
- The external server also offers `write_file`, `edit_file` and `move_file`. The router exposes
  only `list_directory` and `read_text_file`, and only inside the current learner's folder; the
  server's own sandbox is a second layer.
- `learner_id` and `run_id` are injected by the runtime and hidden from the model's tool schemas;
  `approval_id` is supplied only from a teacher's decision. The model cannot target another learner,
  forge an audit identity, or touch the review gate.
- The router, not its callers, enforces the model-facing allowlist.

**Fallbacks, all logged** (`result.fallbacks`, also in the live event stream). A model that is down,
slow, wrong or hostile degrades the run but never changes what it may do:
model unreachable -> one failed call, then deterministic evidence gathering and the template summary;
invalid or forbidden tool call -> rejected and recorded, forced coverage still happens; summary fails
verification twice -> template. `make check-agent-llm` shows how your model fares at each step.

**Summary verifier** (`summary.py`). A draft is rejected for: an id not in the fact sheet, a finding
not cited by pattern id, trait or ability labels, causal or diagnostic wording, any number or term
label not present in the sheet (so the model cannot do arithmetic), or excess length. The model is
told exactly what was wrong and gets one retry. The template is tested to pass its own verifier.

**Failures are never "no data".** If reading records or running detection fails, the run fails with
the real cause. A failed evidence fetch is stated in the summary. Errors from MCP transports arrive
wrapped in anyio `ExceptionGroup`s; the runtime unwraps them so the cause is readable.

**Pause and resume** (`runtime.py`). The graph pauses at `await_teacher` (a LangGraph `interrupt`,
checkpointed to Postgres). Nothing is held in memory while a teacher decides, so a restart loses
nothing. When every review of the current round is decided the run resumes; a per-run lock stops a
duplicate or early resume. After a restart, runs that were mid-flight are marked failed and paused
runs whose decisions arrived meanwhile are resumed. Only one run executes at a time (a CPU-bound local
model cannot serve two).

**Events.** Each node, tool call, model call, rejection, interrupt and resume is an `agent_events`
row, streamed by `GET /api/runs/{id}/stream` (SSE) for the dashboard.

**Operational notes**
- A finding a teacher has approved or rejected is not re-proposed on later runs. To repeat a demo on
  the same learner, run `make seed-reset`.
- LangGraph's checkpointer creates its own tables (`checkpoints`, ...). `alembic/env.py` excludes them
  from autogenerate; without that, the next `make revision` would propose dropping them.
- Gemini is wired through its OpenAI-compatible endpoint for development only. Its request and
  response handling is unit-tested with a mock transport; it has not been run against the live API.
