"""P1 저장 계층 키스톤 ② — MinIO raw 객체 스토어 (design 03 §2, ADR-301).

raw zone(§2.1)이 로컬 fs + in-memory `RawStore`뿐이던 것을 **MinIO 객체 스토어**에
영속화한다. §2 객체 레이아웃을 그대로 따른다:

```text
raw/
  source_id=<src-…>/
    doc_id=<doc-…>/            # doc_id = sha256(raw_bytes)[:24]
      content.bin              # 원본 bytes (수정 금지)
      fetch.json               # §2.2 수집 메타데이터
```

- **불변식 (§2/§2.1, ADR-301):** 동일 `url`의 변경 버전은 **새 `doc_id`로 모두 보존**
  (덮어쓰기 금지). `doc_id`가 내용 기반이므로 동일 bytes 재수집은 동일 객체 → idempotent
  (불변식 §3-6).
- `fetch.json` 필드 중 license/robots_allowed 등 governance([`11`](./11-...))는 이
  저장 계층 증분 범위 밖 — 여기선 core 필드만 기록 (후속 증분에서 반영).
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from datetime import datetime, timezone

from .identity import doc_id_for

try:  # minio 드라이버 선택 — 없으면 모듈 import는 유지 (테스트 importorskip)
    from minio import Minio
except Exception:  # pragma: no cover
    Minio = None


def build_minio_client() -> "Minio":
    """MinIO 클라이언트. .env(환경)의 MINIO_ROOT_USER/PASSWORD/HOST/PORT 사용."""
    if Minio is None:
        raise RuntimeError("minio 드라이버 미설치")
    user = os.environ.get("MINIO_ROOT_USER", "citadel")
    password = os.environ.get("MINIO_ROOT_PASSWORD", "citadel-local-minio")
    host = os.environ.get("MINIO_HOST", "localhost")
    port = os.environ.get("MINIO_PORT", "9000")
    return Minio(
        f"{host}:{port}",
        access_key=user,
        secret_key=password,
        secure=False,
    )


class MinioRawStore:
    """§2 raw zone을 MinIO에 영속화한 append-only 객체 스토어.

    idempotent put — 동일 bytes는 동일 `doc_id`로 no-op, 변경분은 새 `doc_id`로 보존.
    """

    def __init__(self, client, bucket: str = "raw") -> None:
        self.client = client
        self.bucket = bucket
        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)

    # ---- keys (§2.1) ----
    def _content_key(self, source_id: str, doc_id: str) -> str:
        return f"raw/{source_id}/{doc_id}/content.bin"

    def _meta_key(self, source_id: str, doc_id: str) -> str:
        return f"raw/{source_id}/{doc_id}/fetch.json"

    # ---- put ----
    def put(self, source_id: str, url: str, content: bytes, meta: dict | None = None) -> str:
        """raw 저장 — 내용 기반 doc_id 반환. 동일 bytes는 no-op, 변경분은 새 doc_id.

        returns doc_id. meta는 fetch.json에 병합된다.
        """
        doc_id = doc_id_for(content)
        content_key = self._content_key(source_id, doc_id)
        meta_key = self._meta_key(source_id, doc_id)
        if self._object_exists(content_key):
            # 이미 수집 — idempotent no-op (동일 bytes, 중복 객체 없음)
            return doc_id
        # content.bin — 원본 bytes (수정 금지, append-only)
        self.client.put_object(
            self.bucket, content_key, io.BytesIO(content), length=len(content)
        )
        # fetch.json — §2.2 핵심 필드
        fetch = dict(meta or {})
        fetch.setdefault("doc_id", doc_id)
        fetch.setdefault("source_id", source_id)
        fetch.setdefault("url", url)
        fetch.setdefault("content_hash", "sha256:" + hashlib.sha256(content).hexdigest())
        fetch.setdefault("fetched_at", datetime.now(timezone.utc).isoformat())
        self.client.put_object(
            self.bucket, meta_key,
            io.BytesIO(json.dumps(fetch, ensure_ascii=False).encode()), length=len(json.dumps(fetch, ensure_ascii=False).encode()),
        )
        return doc_id

    # ---- get / meta ----
    def _object_exists(self, key: str) -> bool:
        try:
            self.client.stat_object(self.bucket, key)
            return True
        except Exception:
            return False

    def get_raw(self, doc_id: str) -> bytes:
        """content.bin 바이트 반환. doc_id로 source_id를 몰라도 조회하게끔 전체 버킷 스캔 없이
        객체 접두로 찾는다 (doc_id가 내용 기반이므로 어느 source든 키가 유일)."""
        # 정확한 소스 키를 모르므로 전체 버킷에서 doc_id 접미 검색 (소량 raw용 단순 구현).
        prefix = None
        for obj in self.client.list_objects(self.bucket, recursive=True):
            if obj.object_name.endswith(f"/{doc_id}/content.bin"):
                prefix = obj.object_name
                break
        if prefix is None:
            raise KeyError(doc_id)
        resp = self.client.get_object(self.bucket, prefix)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def fetch_meta(self, doc_id: str) -> dict:
        """fetch.json dict 반환."""
        for obj in self.client.list_objects(self.bucket, recursive=True):
            if obj.object_name.endswith(f"/{doc_id}/fetch.json"):
                resp = self.client.get_object(self.bucket, obj.object_name)
                try:
                    return json.loads(resp.read().decode())
                finally:
                    resp.close()
                    resp.release_conn()
        raise KeyError(doc_id)

    def has(self, doc_id: str) -> bool:
        """doc_id 존재 여부 (재개 스킵용)."""
        for obj in self.client.list_objects(self.bucket, recursive=True):
            if obj.object_name.endswith(f"/{doc_id}/content.bin"):
                return True
        return False

    def count_docs(self) -> int:
        """유일 문서(doc_id) 수. 각 doc은 content.bin+fetch.json 2객체라 doc_id 집합으로 센다."""
        return len({
            o.object_name.split("/")[2]  # raw/<source_id>/<doc_id>/content.bin
            for o in self.client.list_objects(self.bucket, recursive=True)
            if o.object_name.endswith("/content.bin")
        })
