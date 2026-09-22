#!/usr/bin/env python3
"""Idempotently prepare Lakekeeper and prove an empty PyIceberg table roundtrip."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import NamedTuple
from urllib.parse import urlparse

import requests
from minio import Minio
from pyiceberg.catalog.rest import RestCatalog
from pyiceberg.schema import Schema
from pyiceberg.types import LongType, NestedField


class Settings(NamedTuple):
    catalog_uri: str
    warehouse: str
    s3_endpoint: str
    s3_region: str
    bucket: str
    access_key: str
    secret_key: str

    @classmethod
    def from_env(cls) -> "Settings":
        def required(name: str) -> str:
            value = os.environ.get(name)
            if not value:
                raise RuntimeError(f"required environment variable is missing: {name}")
            return value

        return cls(
            catalog_uri=required("ICEBERG_CATALOG_URI"),
            warehouse=required("ICEBERG_WAREHOUSE"),
            s3_endpoint=required("ICEBERG_S3_ENDPOINT"),
            s3_region=required("ICEBERG_S3_REGION"),
            bucket=required("LAKEKEEPER_WAREHOUSE_BUCKET"),
            access_key=required("MINIO_ROOT_USER"),
            secret_key=required("MINIO_ROOT_PASSWORD"),
        )


def _management_uri(catalog_uri: str) -> str:
    base = catalog_uri.rstrip("/")
    if not base.endswith("/catalog"):
        raise RuntimeError("ICEBERG_CATALOG_URI must end with /catalog")
    return base.removesuffix("/catalog") + "/management/v1"


def _ensure_bucket(client: Minio, bucket: str) -> None:
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def _ensure_bootstrapped(session: requests.Session, management_uri: str) -> None:
    info_url = f"{management_uri}/info"
    response = session.get(info_url, timeout=30)
    response.raise_for_status()
    if response.json()["bootstrapped"]:
        return

    response = session.post(
        f"{management_uri}/bootstrap",
        json={"accept-terms-of-use": True},
        timeout=30,
    )
    if response.status_code == 204:
        return

    # A concurrent deploy may have won the bootstrap race.
    info = session.get(info_url, timeout=30)
    info.raise_for_status()
    if not info.json()["bootstrapped"]:
        response.raise_for_status()


def _warehouse_payload(settings: Settings) -> dict[str, object]:
    return {
        "warehouse-name": settings.warehouse,
        "storage-profile": {
            "type": "s3",
            "bucket": settings.bucket,
            "key-prefix": "warehouse",
            "endpoint": settings.s3_endpoint,
            "region": settings.s3_region,
            "path-style-access": True,
            "flavor": "s3-compat",
            "sts-enabled": False,
            "remote-signing-enabled": False,
        },
        "storage-credential": {
            "type": "s3",
            "credential-type": "access-key",
            "aws-access-key-id": settings.access_key,
            "aws-secret-access-key": settings.secret_key,
        },
        "delete-profile": {"type": "hard"},
    }


def _ensure_warehouse(
    session: requests.Session, management_uri: str, settings: Settings
) -> None:
    warehouse_url = f"{management_uri}/warehouse"

    def matching_warehouses() -> list[dict[str, object]]:
        response = session.get(warehouse_url, timeout=30)
        response.raise_for_status()
        return [
            warehouse
            for warehouse in response.json()["warehouses"]
            if warehouse["name"] == settings.warehouse
        ]

    existing = matching_warehouses()
    if len(existing) == 1:
        return
    if len(existing) > 1:
        raise RuntimeError(f"multiple warehouses named {settings.warehouse!r}")

    response = session.post(
        warehouse_url,
        json=_warehouse_payload(settings),
        timeout=30,
    )
    if response.status_code == 201:
        return

    # A concurrent deploy may have created the warehouse after our list call.
    if len(matching_warehouses()) != 1:
        response.raise_for_status()


def _roundtrip(
    settings: Settings,
    catalog_factory: Callable[..., RestCatalog],
) -> None:
    catalog = catalog_factory(
        name="g1-smoke",
        uri=settings.catalog_uri,
        warehouse=settings.warehouse,
        token="dummy",
        **{
            "header.X-Iceberg-Access-Delegation": "client-managed",
            "s3.endpoint": settings.s3_endpoint,
            "s3.region": settings.s3_region,
            "s3.access-key-id": settings.access_key,
            "s3.secret-access-key": settings.secret_key,
        },
    )
    namespace = ("g1_smoke",)
    identifier = (*namespace, "empty_table")
    namespace_created = namespace not in catalog.list_namespaces()
    if namespace_created:
        catalog.create_namespace(namespace)
    if identifier in catalog.list_tables(namespace):
        catalog.drop_table(identifier)
    table_created = False

    try:
        catalog.create_table(
            identifier,
            schema=Schema(
                NestedField(
                    field_id=1,
                    name="id",
                    field_type=LongType(),
                    required=True,
                )
            ),
        )
        table_created = True
        reloaded = catalog.load_table(identifier)
        if reloaded.scan().to_arrow().num_rows != 0:
            raise RuntimeError("new G1 smoke table is not empty")
    finally:
        if table_created:
            catalog.drop_table(identifier)
        if namespace_created:
            catalog.drop_namespace(namespace)


def run(
    settings: Settings,
    *,
    minio_client: Minio,
    session: requests.Session,
    catalog_factory: Callable[..., RestCatalog] = RestCatalog,
) -> None:
    _ensure_bucket(minio_client, settings.bucket)
    management_uri = _management_uri(settings.catalog_uri)
    _ensure_bootstrapped(session, management_uri)
    _ensure_warehouse(session, management_uri, settings)
    _roundtrip(settings, catalog_factory)


def main() -> None:
    settings = Settings.from_env()
    endpoint = urlparse(settings.s3_endpoint)
    if endpoint.scheme not in {"http", "https"} or not endpoint.netloc or endpoint.path not in {"", "/"}:
        raise RuntimeError("ICEBERG_S3_ENDPOINT must be an HTTP(S) origin")
    run(
        settings,
        minio_client=Minio(
            endpoint.netloc,
            access_key=settings.access_key,
            secret_key=settings.secret_key,
            secure=endpoint.scheme == "https",
            region=settings.s3_region,
        ),
        session=requests.Session(),
    )
    print("Lakekeeper G1 smoke passed: empty table created, reloaded, scanned, and removed")


if __name__ == "__main__":
    main()
