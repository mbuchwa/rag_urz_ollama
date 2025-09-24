#!/bin/sh
set -e

RUN_MIGRATIONS=${RUN_MIGRATIONS:-1}

if [ "$RUN_MIGRATIONS" = "1" ]; then
  echo "Running database migrations..."
  alembic -c backend/alembic.ini upgrade head
else
  echo "Skipping database migrations (RUN_MIGRATIONS=$RUN_MIGRATIONS)."
fi

echo "Starting: $*"
exec "$@"
