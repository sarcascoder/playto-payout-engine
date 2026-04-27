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

RUN chmod +x scripts/start.sh

EXPOSE 8000

# Default command runs migrations + idempotent seed + gunicorn.
# The Celery worker and beat services override this CMD via the
# Custom Start Command in Railway service settings.
CMD ["sh", "scripts/start.sh"]
