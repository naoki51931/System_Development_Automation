#!/bin/sh
set -eu

if [ "${APP_ENABLE_E2E_SEED:-false}" != "true" ]; then
  echo "Refusing E2E data setup: set APP_ENABLE_E2E_SEED=true" >&2
  exit 2
fi
if [ "${APP_ENV:-development}" = "production" ]; then
  echo "Refusing E2E data setup in production" >&2
  exit 2
fi

docker compose up -d --wait postgres backend worker frontend
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend python -m app.seed
docker compose run --rm -e APP_ENABLE_E2E_SEED=true backend python -m app.quality.seed_e2e
docker compose --profile e2e run --rm e2e "$@"
