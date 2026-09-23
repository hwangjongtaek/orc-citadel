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

# 소스를 import 가능하게 만든다. uv 는 pyproject 에 [build-system] 이 없으면
# 프로젝트를 비패키지로 보고 설치하지 않는다 — 종전 `pip install ".[dev]"` 는
# setuptools 폴백으로 설치했다. 패키징 규약을 바꾸는 대신 경로로 해결한다.
# 없으면 `python scripts/investigation_worker.py` 처럼 경로로 실행되는 진입점이
# sys.path[0]=/app/scripts 라 ModuleNotFoundError 로 죽는다 (2026-09-22 prod 실측).
ENV PYTHONPATH=/app

EXPOSE 8791
CMD ["python", "-m", "orc_citadel.viewer"]
