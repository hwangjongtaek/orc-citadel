from __future__ import annotations

import io
from dataclasses import dataclass


@dataclass(frozen=True)
class FakeObject:
    object_name: str


class FakeResponse(io.BytesIO):
    def release_conn(self) -> None:
        pass


class FakeMinio:
    """Small in-memory subset of the MinIO client used by raw-store tests."""

    def __init__(self) -> None:
        self.buckets: dict[str, dict[str, bytes]] = {}

    def bucket_exists(self, bucket: str) -> bool:
        return bucket in self.buckets

    def make_bucket(self, bucket: str) -> None:
        self.buckets[bucket] = {}

    def remove_bucket(self, bucket: str) -> None:
        del self.buckets[bucket]

    def put_object(self, bucket: str, key: str, data, length: int, **_kwargs):
        payload = data.read(length)
        self.buckets[bucket][key] = payload
        return FakeObject(key)

    def get_object(self, bucket: str, key: str) -> FakeResponse:
        try:
            return FakeResponse(self.buckets[bucket][key])
        except KeyError as exc:
            raise FileNotFoundError(key) from exc

    def stat_object(self, bucket: str, key: str) -> FakeObject:
        if key not in self.buckets[bucket]:
            raise FileNotFoundError(key)
        return FakeObject(key)

    def list_objects(self, bucket: str, prefix: str | None = None, recursive: bool = False):
        del recursive
        for key in sorted(self.buckets.get(bucket, {})):
            if prefix is None or key.startswith(prefix):
                yield FakeObject(key)

    def remove_object(self, bucket: str, key: str) -> None:
        del self.buckets[bucket][key]
