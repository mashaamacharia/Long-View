#!/bin/sh
set -e

# Backend owns migrations; other services set SKIP_MIGRATIONS=1.
if [ "${SKIP_MIGRATIONS:-0}" != "1" ]; then
  echo "Running migrations..."
  alembic upgrade head
fi

exec "$@"
