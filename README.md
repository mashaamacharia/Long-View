# LongView The Long View

An agentic AI system that follows one learner across multiple years, surfaces
evidence-backed patterns, and hands them to the teacher for review.
**Profile, don't label.** The teacher decides; the agent never assigns tracks or rankings.

> Hackathon: The Long View (Education / Agentic AI). MCP + open source.

---

## Quick start

```bash
git clone <repo> && cd Long-View
cp .env.example .env    # defaults work as-is (required: .env is not committed)
make up                 # build + start postgres, ollama, backend, mcp-server, frontend
make pull-model         # first run only: downloads the Qwen model (~2.5GB)
make seed               # synthetic learners, records and docs (~10 seconds)
```

Open **http://localhost:5173** for the dashboard and **http://localhost:8000/docs** for the API.

That's it - migrations are committed and the backend applies them automatically on startup
(`entrypoint.sh` runs `alembic upgrade head`), so there is no `make revision` / `make migrate` step
on a fresh clone. The database itself is a throwaway Docker volume (`pgdata`) created by `make up`;
every clone gets its own empty database and `make seed` fills it from code.

> **First `make up` is slow** (image builds + `pip install`). Later starts take ~15s.

### Prerequisites

- Docker + Docker Compose v2
- ~4GB free RAM (the model runs CPU-only; see `.env` for `OLLAMA_*` knobs)

---

## What you get

| URL                        | What                                                                            |
| -------------------------- | ------------------------------------------------------------------------------- |
| http://localhost:5173      | Dashboard: learner directory, profiles with charts, Ask the AI, Teacher Reviews |
| http://localhost:8000/docs | FastAPI interactive API docs                                                    |
| http://localhost:11434     | Ollama (model server)                                                           |

**Dashboard pages**

- **Students** - directory of all learners (search + grade filter), driven by `GET /api/learners`
- **Profile** - identity, teacher-approved highlights, performance-over-time chart, per-subject
  breakdown with term detail and teacher observations, and an **Add / Update Record** form
  (`POST /api/learners/{id}/records`)
- **Ask the AI** - starts an agent run (`POST /api/runs`) and follows every step live over SSE
  (`GET /api/runs/{id}/stream`); a run that needs a decision pauses and links to Reviews
- **Teacher Reviews** - pending findings with the full, unredacted evidence, and
  approve / reject / more-evidence buttons (`POST /api/reviews/{id}/decision`)

The frontend is a React 18 + Vite + TypeScript SPA in `frontend/`, served by nginx in Docker.
nginx proxies `/api` to the backend (including SSE - buffering is off), so there is no CORS setup
in the default flow. Local dev without Docker: `cd frontend && npm install && npm run dev`
(Vite proxies `/api` to `localhost:8000`).

---

## Commands

| Command                                          | What it does                                                                        |
| ------------------------------------------------ | ----------------------------------------------------------------------------------- |
| `make up` / `make down` / `make logs`      | start / stop / follow logs                                                          |
| `make dev-up`                                  | compose + `docker-compose.dev.yml` overrides                                      |
| `make reset`                                   | wipe the volumes and start fresh (loses seeded data)                                |
| `make seed`                                    | load synthetic learners (skips if records already exist)                            |
| `make seed-reset`                              | wipe and reseed - use when a previous seed is stale                                 |
| `make test`                                    | full test suite in the container (in-memory SQLite, no DB needed)                   |
| `make test-pg`                                 | same suite against Postgres, including the live-stack test                          |
| `make eval`                                    | 10 eval tasks with the LLM (~20–30 min on CPU)                                     |
| `make eval-quick`                              | same 10 tasks, deterministic-only (~1 min, no model)                                |
| `make agent L=L1044 Q="Is anything drifting?"` | run the agent from the terminal (`A=approve` / `A=reject` to auto-decide)       |
| `make check-llm`                               | smoke-test Qwen tool calling                                                        |
| `make check-agent-llm`                         | check the model on the agent's three jobs (tool choice, stopping, verified summary) |
| `make pull-model`                              | download the model named in `.env`                                                |
| `make revision m="msg"`                        | Alembic autogenerate a migration (schema changes only)                              |
| `make migrate`                                 | apply migrations (normally automatic via `make up`)                               |

---

## How it works

Full detail lives in [ARCHITECTURE.md](ARCHITECTURE.md); the short version:

```
fetch_timeline -> detect -> investigate -> triage -> flag -> await_teacher -> apply -> summarise
```

1. **Deterministic analysis, not model arithmetic.** Trend detection, anomaly screening, sufficiency
   and conflict checks are plain Python in `backend/app/mcp_server/analysis/`, unit-tested and
   reproducible. The model plans, judges whether to gather more evidence, and writes the summary -
   which a verifier checks against a fact sheet before it can be shown (one retry, then a template).
2. **MCP tool safety lives in the server, not the prompt.** The agent reaches tools through two MCP
   servers behind one router: ours (learner timeline, evidence, detection, review flagging, profile
   updates) and a sandboxed filesystem server for teacher documents. Rules like "profile writes need
   a teacher-approved `approval_id`" are enforced server-side, so a wrong or talked-into model hits
   the same refusal as a hostile one.
3. **The approval gate is the product.** A run that finds something pauses at `await_teacher`
   (LangGraph interrupt, checkpointed). Nothing reaches a learner profile until a teacher approves
   that specific finding; every decision and every refusal is audited.
4. **Small open-weights model by default.** Qwen3-4B via Ollama (`hf.co/unsloth/...` in `.env`);
   Gemini is wired for development comparison only. When the model is down or wrong, the run
   degrades to deterministic evidence gathering - all fallbacks logged, never silently.

### API surface

| Endpoint                                                          | Purpose                                            |
| ----------------------------------------------------------------- | -------------------------------------------------- |
| `GET /api/health`                                               | liveness                                           |
| `GET /api/learners` · `GET /api/learners/{id}`               | directory + identity                               |
| `GET /api/learners/{id}/records`                                | records + observations (charts, subject breakdown) |
| `POST /api/learners/{id}/records`                               | teacher enters an assessment/observation           |
| `GET /api/learners/{id}/profile`                                | teacher-approved findings written to the profile   |
| `POST /api/runs` · `GET /api/runs` · `GET /api/runs/{id}` | start / list / inspect agent runs                  |
| `GET /api/runs/{id}/events` · `GET /api/runs/{id}/stream`    | step history / live SSE stream                     |
| `GET /api/reviews` · `GET /api/reviews/{id}`                 | review queue / full evidence for a decision        |
| `POST /api/reviews/{id}/decision`                               | approve, reject, or ask for more evidence          |

---

## Evals

Ten tasks with known right answers - the data is synthetic and the patterns are planted.
Specs live in `backend/evals/tasks/`, ground truth in `backend/data_gen/personas/`.
Details and the judging methodology: [EVALS.md](EVALS.md).

```bash
make eval-quick   # deterministic checks only, ~1 minute, no model
make eval         # full run against Qwen, ~20–30 minutes on CPU
```

Both write `backend/evals/results/latest*.json` and refresh the Results section of `EVALS.md`
(bind-mounted into the container - results land in your repo, not inside the image).
`eval-quick` and `eval` share the same results block, so run `make eval` **last** if you want
`EVALS.md` to reflect the real-model run.

Current status: **10/10 deterministic, 10/10 with the model.**

---

## Tests

```bash
make test      # 209 tests, in-memory SQLite, runs entirely in the backend container
make test-pg   # same tests against a real Postgres (longview_test DB), incl. live-stack
```

Coverage includes the analysis engine, the approval gate (mutation-tested guarantees), the MCP
tool contracts, the HTTP API (runs, reviews, records), the agent graph with a scripted model, and
the eval runner. Two live-LLM tests are skipped unless the model is reachable.

---

## Project layout

```
backend/
  app/agent/         graph, runtime (pause/resume), policy, summary verifier, LLM adapters
  app/api/           FastAPI routers: learners, runs, reviews
  app/mcp_server/    MCP server: tools + deterministic analysis/ engine
  app/services/      review workflow, evidence building
  app/db/            models, alembic migrations, seeder
  data_gen/          synthetic personas + record generator (also powers evals)
  evals/             10 eval tasks, runner, checks
  tests/             full suite (pytest)
frontend/            React + Vite dashboard (nginx in Docker)
data/docs/           teacher documents per learner (mounted into containers)
docs/                demo script, submission notes
ARCHITECTURE.md      design decisions: analysis pipeline, MCP safety, approval gate, agent
EVALS.md             eval methodology + latest results
```

---

## Demo notes & troubleshooting

- **Seeded data.** `make seed` loads 8 learners, 580 records, 34 observations and writes teacher
  documents to `data/docs/`. It skips if records already exist - use `make seed-reset` to wipe and
  reseed (also how you reset between demo runs, since decided findings are not re-proposed).
- **Containers exited with code 255** (everything unreachable at once): the Docker/WSL VM stopped.
  `make up` restarts it in ~15s - no rebuild needed.
- **Backend won't start:** `docker compose logs backend`. Schema problems are usually a stale
  volume: `make reset` then `make seed`.
- **Model seems slow/unavailable:** `make pull-model`, then `make check-llm`. CPU-only inference
  means ~1–4 min per agent run; `make eval-quick` never needs the model.
- **New schema change:** edit the models, then `make revision m="describe it"` and `make migrate`.
  Commit the generated file under `backend/alembic/versions/`.

## License

See [LICENSE](LICENSE).
