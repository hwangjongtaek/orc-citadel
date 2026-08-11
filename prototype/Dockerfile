# prototype viewer/테스트 실행기 — data/ 는 볼륨 마운트로 주입 (docker-compose.yml).
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY orc_citadel/ orc_citadel/
COPY tests/ tests/

RUN pip install --no-cache-dir ".[dev]"

EXPOSE 8791
CMD ["python", "-m", "orc_citadel.viewer"]
