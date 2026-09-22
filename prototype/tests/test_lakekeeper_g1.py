"""G1 Lakekeeper catalog deployment and smoke contracts."""

from __future__ import annotations

import importlib.util
import re
import tomllib
from types import SimpleNamespace
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def _compose(name: str = "docker-compose.yml") -> str:
    return (REPO / name).read_text(encoding="utf-8")


def _service_block(compose: str, name: str) -> str:
    match = re.search(rf"^  {re.escape(name)}:\n((?:    .*\n|\n)+)", compose, re.M)
    assert match, f"{name} service is missing"
    return match.group(1)


def test_lakekeeper_uses_pinned_image_and_native_healthcheck() -> None:
    service = _service_block(_compose(), "lakekeeper")
    assert "image: quay.io/lakekeeper/catalog:v0.13.4" in service
    assert '["CMD", "/home/nonroot/lakekeeper", "healthcheck"]' in service
    assert '127.0.0.1:8181:8181' in service


def test_local_catalog_and_object_store_ports_bind_loopback() -> None:
    compose = _compose()
    assert '"127.0.0.1:8181:8181"' in _service_block(compose, "lakekeeper")
    minio = _service_block(compose, "minio")
    assert '"127.0.0.1:9000:9000"' in minio
    assert '"127.0.0.1:9001:9001"' in minio


def test_prod_lakekeeper_is_unpublished_and_restarts() -> None:
    service = _service_block(_compose("docker-compose.prod.yml"), "lakekeeper")
    assert "ports: !override []" in service
    assert "restart: unless-stopped" in service


def test_catalog_settings_are_explicit_and_secrets_are_interpolated() -> None:
    service = _service_block(_compose(), "lakekeeper")
    for name in (
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "LAKEKEEPER_PG_ENCRYPTION_KEY",
    ):
        assert re.search(rf":\s*\$\{{{name}:\?\}}", service)

    required = {
        "LAKEKEEPER_PG_ENCRYPTION_KEY",
        "LAKEKEEPER_WAREHOUSE_BUCKET",
        "ICEBERG_CATALOG_URI",
        "ICEBERG_WAREHOUSE",
        "ICEBERG_S3_ENDPOINT",
        "ICEBERG_S3_REGION",
    }
    for template in (".env.example", ".env.production.example"):
        text = (REPO / template).read_text(encoding="utf-8")
        assert required <= set(re.findall(r"^([A-Z0-9_]+)=", text, re.M))


def test_application_gets_catalog_endpoint_credentials_and_health_dependency() -> None:
    service = _service_block(_compose(), "prototype")
    for name in (
        "ICEBERG_CATALOG_URI",
        "ICEBERG_WAREHOUSE",
        "ICEBERG_S3_ENDPOINT",
        "ICEBERG_S3_REGION",
        "LAKEKEEPER_WAREHOUSE_BUCKET",
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
    ):
        assert re.search(rf"{name}:\s*\$\{{{name}:\?\}}", service)
    assert re.search(
        r"lakekeeper:\n\s+condition: service_healthy", service
    )
    assert re.search(r"minio:\n\s+condition: service_healthy", service)


def test_prod_scheduler_gets_catalog_client_settings() -> None:
    service = _service_block(_compose("docker-compose.prod.yml"), "scheduler")
    for name in (
        "ICEBERG_CATALOG_URI",
        "ICEBERG_WAREHOUSE",
        "ICEBERG_S3_ENDPOINT",
        "ICEBERG_S3_REGION",
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
    ):
        assert re.search(rf"{name}:\s*\$\{{{name}:\?\}}", service)


def test_iceberg_dependencies_and_container_use_the_lockfile() -> None:
    project = tomllib.loads(
        (REPO / "prototype" / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    dependencies = project["dependencies"]
    assert any(dep.startswith("pyarrow") for dep in dependencies)
    assert any(
        dep.startswith("pyiceberg") and "s3fs" in dep and "sql-sqlite" in dep
        for dep in dependencies
    )
    dockerfile = (REPO / "prototype" / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY pyproject.toml uv.lock ./" in dockerfile
    assert "uv sync --frozen" in dockerfile


def test_smoke_bootstraps_catalog_and_roundtrips_empty_table() -> None:
    script = REPO / "deploy" / "lakekeeper" / "smoke.py"
    spec = importlib.util.spec_from_file_location("lakekeeper_smoke", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    settings = module.Settings(
        catalog_uri="http://lakekeeper:8181/catalog",
        warehouse="orc-citadel",
        s3_endpoint="http://minio:9000",
        s3_region="local-01",
        bucket="orc-citadel-warehouse",
        access_key="access",
        secret_key="secret",
    )

    class Storage:
        made: list[str] = []

        def bucket_exists(self, bucket: str) -> bool:
            return False

        def make_bucket(self, bucket: str) -> None:
            self.made.append(bucket)

    class Response:
        def __init__(self, status: int, body: dict | None = None):
            self.status_code = status
            self._body = body or {}
            self.text = ""

        def json(self) -> dict:
            return self._body

        def raise_for_status(self) -> None:
            assert self.status_code < 400

    class Session:
        posts: list[tuple[str, dict]] = []

        def get(self, url: str, timeout: int) -> Response:
            if url.endswith("/info"):
                return Response(200, {"bootstrapped": False})
            return Response(200, {"warehouses": []})

        def post(self, url: str, json: dict, timeout: int) -> Response:
            self.posts.append((url, json))
            return Response(204 if url.endswith("/bootstrap") else 201)

    class Scan:
        def to_arrow(self) -> SimpleNamespace:
            return SimpleNamespace(num_rows=0)

    class Table:
        def scan(self) -> Scan:
            return Scan()

    class Catalog:
        actions: list[tuple[str, object]] = []

        def list_namespaces(self) -> list[tuple[str]]:
            return []

        def create_namespace(self, namespace: tuple[str]) -> None:
            self.actions.append(("create_namespace", namespace))

        def list_tables(self, namespace: tuple[str]) -> list[tuple[str, str]]:
            return []

        def create_table(self, identifier: tuple[str, str], schema: object) -> Table:
            self.actions.append(("create_table", identifier))
            return Table()

        def load_table(self, identifier: tuple[str, str]) -> Table:
            self.actions.append(("load_table", identifier))
            return Table()

        def drop_table(self, identifier: tuple[str, str]) -> None:
            self.actions.append(("drop_table", identifier))

        def drop_namespace(self, namespace: tuple[str]) -> None:
            self.actions.append(("drop_namespace", namespace))

    catalog_options: dict[str, str] = {}

    def catalog_factory(**options: str) -> Catalog:
        catalog_options.update(options)
        return Catalog()

    storage = Storage()
    session = Session()
    module.run(
        settings,
        minio_client=storage,
        session=session,
        catalog_factory=catalog_factory,
    )

    assert storage.made == ["orc-citadel-warehouse"]
    assert session.posts[0][0].endswith("/management/v1/bootstrap")
    warehouse = session.posts[1][1]
    assert warehouse["storage-profile"]["sts-enabled"] is False
    assert warehouse["storage-profile"]["remote-signing-enabled"] is False
    assert warehouse["storage-credential"]["aws-access-key-id"] == "access"
    assert catalog_options["header.X-Iceberg-Access-Delegation"] == "client-managed"
    assert catalog_options["s3.access-key-id"] == "access"
    assert [action for action, _ in Catalog.actions] == [
        "create_namespace",
        "create_table",
        "load_table",
        "drop_table",
        "drop_namespace",
    ]


def test_deploy_runs_ephemeral_migration_then_catalog_smoke() -> None:
    compose = _service_block(_compose(), "prototype")
    prod = _service_block(_compose("docker-compose.prod.yml"), "prototype")
    mount = "./deploy/lakekeeper:/app/deploy/lakekeeper:ro"
    assert mount in compose
    assert mount in prod

    deploy = (REPO / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    assert "run --rm lakekeeper migrate" in deploy
    assert "up -d --wait lakekeeper" in deploy
    assert "run --rm prototype python deploy/lakekeeper/smoke.py" in deploy
    assert not re.search(r"^  migrate:", _compose(), re.M)
