# LongView

An agentic AI system that follows one learner across multiple years, surfaces
evidence-backed patterns, and hands them to the teacher for review.
**Profile, don't label.** The teacher decides; the agent never assigns tracks or rankings.

> Hackathon: The Long View (Education / Agentic AI). MCP + open source.

## Quick start

```bash
cp .env.example .env      # defaults work as-is
make up                   # postgres, ollama, backend, mcp-server, frontend
make pull-model           # first run only: downloads the Qwen model
make revision m="init"    # first run only, until a migration is committed
make migrate
make seed                 # load synthetic learners
```

Open http://localhost:5173 (UI) and http://localhost:8000/docs (API).

## Common commands

| Command | What it does |
|---|---|
| `make up` / `make down` | start / stop everything |
| `make revision m="msg"` | Alembic autogenerate a migration |
| `make migrate` | apply migrations |
| `make seed` | load synthetic data |
| `make eval` | run the evaluation suite |
| `make check-llm` | smoke-test Qwen tool calling |

TODO: architecture summary, demo link, evals summary.
