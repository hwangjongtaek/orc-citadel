"""P1 트랙 A — dedup 배선 (design 04 §4, ADR-403).

`Deduplicator`(S4) 가 run_pipeline 에 배선되어, 파이프라인이 실제 실행될 때
`dup_clusters` 를 영속한다. near-dup 문서 2건 → `run_pipeline` → 단일 클러스터 생성,
root 는 publication_time 이른 쪽 (design 04 §4.2). cluster_id 는 결정적
(doc_id + dedup_version 재생성 계약) 이어야 한다.
"""
from __future__ import annotations

import pytest

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.pipeline_runner import run_pipeline


def _doc(content: str, doc_id: str, pub: str) -> dict:
    return {
        "source_id": "test", "url": f"https://e/{doc_id}", "doc_id": doc_id,
        "content": content.encode(),
        "publication_time": pub,
    }


# 실제 파이프라인 결정적 체인을 통과하는 문서들 (NVIDIA 템플릿 사용).
BASE = """<html><head><title>NVIDIA Conference Call</title>
<meta property="article:published_time" content="%s"/></head><body><article>
<h1>NVIDIA Sets Conference Call</h1>
<p>%s</p>
<p>NVIDIA powers the data center and announces new accelerator products.</p>
</article></body></html>"""

# 중복 복제 — 동일 본문을 서로 다른 doc_id(재수집)로 보유. clean text 동일 → S4 ① exact
# 병합으로 단일 클러스터 (04 §4, ADR-403 content-hash). root 는 publication_time 이른 쪽.
SENT = (
    "NVIDIA announced its next-generation Blackwell architecture for data centers. "
    "The new platform delivers up to four times faster inference performance while "
    "reducing energy consumption per token. NVIDIA will host a conference call on "
    "Wednesday to discuss quarterly results and the roadmap. "
    "Analysts expect strong demand from cloud providers and AI startups alike. "
    "The company also touted partnerships with major server manufacturers."
)


def _metas():
    return [
        _doc(BASE % ("2026-08-01T14:00:00+00:00", SENT), "doc-t0000000000000000000000001", "2026-08-01"),
        _doc(BASE % ("2026-08-02T14:00:00+00:00", SENT), "doc-t0000000000000000000000002", "2026-08-02"),
    ]


def test_run_pipeline_populates_dup_clusters():
    """run_pipeline 이 Deduplicator 호출 → 중복 2건이 하나의 클러스터로 축소."""
    z = CuratedZone(); z.initialize()
    res = run_pipeline(_metas(), z)
    clusters = z.clusters()
    assert len(clusters) == 1  # 중복 2건 → 단일 클러스터
    assert res.clusters == 1


def test_cluster_root_is_earlier_publication():
    """root 는 publication_time 이른 쪽 (design 04 §4.2)."""
    z = CuratedZone(); z.initialize()
    run_pipeline(_metas(), z)
    clusters = z.clusters()
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster["root_doc_id"] == "doc-t0000000000000000000000001"  # 08-01 이 더 이르다
    # 더 늦은(파생) 문서는 member 로 편입
    assert "doc-t0000000000000000000000002" in cluster["member_doc_ids"]


def test_cluster_id_deterministic():
    """동일 입력 재실행 → 동일 cluster_id (doc_id+dedup_version 재생성 계약)."""
    z1 = CuratedZone(); z1.initialize()
    run_pipeline(_metas(), z1)
    c1 = [c["cluster_id"] for c in z1.clusters()]

    z2 = CuratedZone(); z2.initialize()
    run_pipeline(_metas(), z2)
    c2 = [c["cluster_id"] for c in z2.clusters()]

    assert c1 == c2
