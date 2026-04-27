#!/bin/sh
# Container entrypoint. Migrates the DB, seeds demo data if empty, then
# starts gunicorn. Idempotent — safe to run on every container start.
set -e

echo "=== Running migrations ==="
uv run python manage.py migrate --noinput

echo "=== Running seed (idempotent) ==="
uv run python manage.py shell -c "exec(open('scripts/seed.py').read())"

echo "=== Starting gunicorn on port ${PORT:-8000} ==="
exec uv run gunicorn config.wsgi:application \
  --bind 0.0.0.0:${PORT:-8000} \
  --workers 3 \
  --access-logfile -
