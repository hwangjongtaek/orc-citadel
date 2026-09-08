-- Grafana read-only 계정 (TS-6) — 메트릭 테이블 SELECT 한정, 그래프 SoT 접근 없음.
--
-- 적용 (1회, 메트릭 테이블 생성 이후 = 첫 flush 이후):
--   set -a; source .env; set +a
--   docker compose exec -T postgres \
--     psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
--          -v grafana_password="$GRAFANA_DB_PASSWORD" \
--     < deploy/grafana/init-readonly.sql
--
-- 재실행 안전(멱등): 역할이 있으면 비밀번호·권한만 다시 맞춘다.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'grafana_reader') THEN
        CREATE ROLE grafana_reader LOGIN;
    END IF;
END $$;

ALTER ROLE grafana_reader PASSWORD :'grafana_password';

-- GRANT CONNECT 는 DB 이름이 필요 — 현재 접속 DB 로 동적 생성.
SELECT format('GRANT CONNECT ON DATABASE %I TO grafana_reader', current_database())
\gexec

GRANT USAGE ON SCHEMA public TO grafana_reader;
GRANT SELECT ON TABLE pipeline_run_metrics, pipeline_slo_observations
    TO grafana_reader;
