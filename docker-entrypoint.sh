#!/bin/sh
set -eu

if [ "${1:-}" = "pytest" ]; then
  export DATABASE_URL="sqlite+aiosqlite:////tmp/wpopapi-test.db"
fi

alembic upgrade head
exec "$@"
