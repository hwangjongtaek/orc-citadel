# prototype viewer/테스트 실행기 — data/ 는 볼륨 마운트로 주입 (docker-compose.yml).
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra dev --no-install-project

ENV PATH="/app/.venv/bin:$PATH"

COPY orc_citadel/ orc_citadel/
COPY scripts/ scripts/
COPY tests/ tests/

EXPOSE 8791
CMD ["python", "-m", "orc_citadel.viewer"]
