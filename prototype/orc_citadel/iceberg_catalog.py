"""Iceberg catalog construction for normalized-zone storage.

Production uses the configured REST catalog and object store. Local paths use the
same Iceberg table format through a persistent SQLite catalog and a file warehouse.
"""
from __future__ import annotations

import os
import pathlib
import tempfile
from dataclasses import dataclass


@dataclass
class CatalogHandle:
    catalog: object
    root: pathlib.Path | None
    temporary: tempfile.TemporaryDirectory | None = None

    def close(self) -> None:
        if self.temporary is not None:
            self.temporary.cleanup()
            self.temporary = None


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required for the Iceberg REST catalog")
    return value


def open_catalog(root: str | pathlib.Path) -> CatalogHandle:
    """Open the configured REST catalog or a local persistent SQLite catalog."""
    from pyiceberg.catalog import load_catalog

    uri = os.environ.get("ICEBERG_CATALOG_URI")
    if uri:
        props = {
            "type": "rest",
            "uri": uri,
            "warehouse": _required("ICEBERG_WAREHOUSE"),
            "s3.endpoint": _required("ICEBERG_S3_ENDPOINT"),
            "s3.region": _required("ICEBERG_S3_REGION"),
            "s3.access-key-id": _required("MINIO_ROOT_USER"),
            "s3.secret-access-key": _required("MINIO_ROOT_PASSWORD"),
            "header.X-Iceberg-Access-Delegation": "client-managed",
            "py-io-impl": "pyiceberg.io.pyarrow.PyArrowFileIO",
        }
        return CatalogHandle(load_catalog("orc-citadel", **props), None)

    temporary = None
    if str(root) == ":memory:":
        temporary = tempfile.TemporaryDirectory(prefix="orc-citadel-iceberg-")
        local_root = pathlib.Path(temporary.name)
    else:
        local_root = pathlib.Path(root).expanduser().resolve()
        local_root.mkdir(parents=True, exist_ok=True)
    catalog_file = local_root / "catalog.sqlite"
    warehouse = local_root.as_uri()
    catalog = load_catalog(
        "orc-citadel-local",
        type="sql",
        uri=f"sqlite:///{catalog_file}",
        warehouse=warehouse,
        **{"py-io-impl": "pyiceberg.io.pyarrow.PyArrowFileIO"},
    )
    return CatalogHandle(catalog, local_root, temporary)
