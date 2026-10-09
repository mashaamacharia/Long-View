.PHONY: up down logs migrate revision seed eval reset pull-model check-llm dev-up

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

eval:
	docker compose exec backend python -m evals.run_evals

pull-model:
	docker compose exec ollama ollama pull $$(grep ^OLLAMA_MODEL .env | cut -d= -f2)

check-llm:
	docker compose exec backend python scripts/check_tool_calling.py

reset:
	docker compose down -v && docker compose up --build
