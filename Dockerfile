FROM python:3.13-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /uvx /bin/
RUN useradd --create-home app
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY --chown=app:app *.py ./
USER app
ENV PYTHONUNBUFFERED=1
CMD ["uv", "run", "--no-sync", "agent.py"]
