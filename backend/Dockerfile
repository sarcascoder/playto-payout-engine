FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv (we use the same package manager that built the project locally)
RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# collectstatic is required for /admin/ to render correctly with whitenoise
RUN uv run python manage.py collectstatic --noinput || true

EXPOSE 8000

# Default command is the web server. Migrations run on every container start
# (no-op if already applied). Seed runs idempotently — only creates the demo
# merchants if none exist, so it's safe to repeat.
# The Celery worker and beat services override this CMD via their start command
# in the Railway service settings.
CMD ["sh", "-c", "uv run python manage.py migrate --noinput && uv run python manage.py shell -c \"exec(open('scripts/seed.py').read())\" && uv run gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3 --access-logfile -"]
