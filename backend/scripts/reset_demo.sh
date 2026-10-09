#!/bin/sh
set -e
docker compose down -v
docker compose up -d --build
sleep 10
docker compose exec backend python -m app.db.seed
