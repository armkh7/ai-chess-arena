FROM python:3.13-slim

# Stockfish is used for move analysis (Phase 2).
RUN apt-get update \
  && apt-get install -y --no-install-recommends stockfish \
  && rm -rf /var/lib/apt/lists/*
ENV PATH="/usr/games:${PATH}"

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY alembic.ini public_models.toml ./
COPY migrations ./migrations
RUN uv sync --frozen --no-dev

EXPOSE 8000
# Bring the database schema up to date, then start the API.
CMD ["sh", "-c", "uv run --no-dev alembic upgrade head && uv run --no-dev uvicorn app.main:app --host 0.0.0.0 --port 8000"]
