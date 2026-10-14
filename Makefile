.PHONY: up down logs migrate revision seed seed-reset test test-pg eval eval-quick reset pull-model check-llm check-agent-llm agent dev-up

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

dev-up:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

migrate:
	docker compose exec backend alembic upgrade head

# usage: make revision m="add learner_patterns"
revision:
	docker compose exec backend alembic revision --autogenerate -m "$(m)"

seed:
	docker compose exec backend python -m app.db.seed

seed-reset:
	docker compose exec backend python -m app.db.seed --reset

test:
	docker compose exec backend pytest -q

# all tasks against your real model (about 30 min on CPU); subset: make eval ONLY=EVAL-03,EVAL-05
eval:
	docker compose exec backend python -m evals.run_evals --yes $(if $(ONLY),--only $(ONLY),)

# no model at all: proves the deterministic floor and the pipeline in about a minute
eval-quick:
	docker compose exec backend python -m evals.run_evals --yes --llm none

pull-model:
	docker compose exec ollama ollama pull $$(grep ^OLLAMA_MODEL .env | cut -d= -f2)

check-llm:
	docker compose exec backend python scripts/check_tool_calling.py

# multi-turn tool use + summary verification against the configured model
check-agent-llm:
	docker compose exec backend python -m scripts.check_agent_llm

# run the agent from the terminal: make agent L=L1044 Q="Look at Cynthia's English results" [A=approve|reject]
agent:
	docker compose exec backend python -m scripts.run_agent $(L) "$(Q)" $(if $(A),--$(A),)

# whole suite on Postgres (including the live-stack test), using a scratch database
test-pg:
	-docker compose exec postgres createdb -U longview longview_test
	docker compose exec -e TEST_DB_URL=postgresql+psycopg://longview:longview@postgres:5432/longview_test backend pytest -q

reset:
	docker compose down -v && docker compose up --build
