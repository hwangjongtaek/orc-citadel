"""TDD Red — S4 출처 계보·복제 축소 (design 04 §4, 03 §4.3).

Deduplicator 계약:
- exact(① content hash) 동일 콘텐츠 → 같은 cluster
- near(② MinHash/Jaccard) 거의 동일 문서 → 같은 cluster
- 무관 문서 → 다른 cluster
- root 선정: publication_time 이른 쪽, 동률 doc_id 사전순 tie-break
- 불변식: independent ⊆ member, root ∉ member/independent (03 §4.3)
- 결정성: (doc_id, dedup_version) 하에 재생성 (02 §4.2)
"""
from orc_citadel.dedup import Deduplicator, Cluster, DEDUP_VERSION

# 공통 시그니처: (doc_id, text, publication_time, source_type)
def _doc(did, text, pubtime="2026-08-01T00:00:00+00:00", stype="press"):
    return {"doc_id": did, "text": text, "publication_time": pubtime, "source_type": stype}


TEXT_A = (
    "NVIDIA will host a conference call on Wednesday to discuss its financial results. "
    "The results cover the second quarter of fiscal year 2027 which ended July 26 2026. "
    "Executives will take questions from analysts about data center demand and HBM supply."
)
TEXT_A_NEAR = (
    "NVIDIA will host a conference call on Wednesday to discuss its financial results "
    "(rescheduled from Tuesday). "  # 삽입만 — 표면 거의 동일 (near-dup)
    "The results cover the second quarter of fiscal year 2027 which ended July 26 2026. "
    "Executives will take questions from analysts about data center demand and HBM supply."
)
TEXT_B = (
    "TSMC starts construction on a new advanced packaging fab in Arizona. "
    "The facility will focus on CoWoS capacity to meet growing AI chip demand. "
    "Production is expected to begin in early 2027 according to company officials."
)


# ---- 1. exact (① content hash) ----
def test_exact_same_content_same_cluster():
    d = Deduplicator()
    docs = [
        _doc("doc-a", TEXT_A, "2026-08-01T00:00:00+00:00", "official"),
        _doc("doc-b", TEXT_A, "2026-08-02T00:00:00+00:00", "press"),  # 다른 url 재수집, 동일 text
        _doc("doc-c", TEXT_B, "2026-08-01T00:00:00+00:00", "press"),
    ]
    def find_cluster(doc_id):
        return next(c for c in clusters if doc_id == c.root_doc_id or doc_id in c.member_doc_ids)

    clusters = d.dedup(docs)
    # exact 동일 text는 같은 cluster; B는 별개
    assert len(clusters) == 2
    cl_a = find_cluster("doc-a")
    assert "doc-b" in cl_a.member_doc_ids  # 동일 내용 파생 멤버
    assert "doc-c" not in cl_a.member_doc_ids and cl_a.root_doc_id != "doc-c"


# ---- 2. near (② MinHash/Jaccard) ----
def test_near_duplicate_same_cluster():
    d = Deduplicator()
    docs = [
        _doc("doc-a", TEXT_A, "2026-08-01T00:00:00+00:00", "official"),
        _doc("doc-a2", TEXT_A_NEAR, "2026-08-01T00:00:00+00:00", "press"),
        _doc("doc-b", TEXT_B, "2026-08-03T00:00:00+00:00", "press"),
    ]
    clusters = d.dedup(docs)
    def find_cluster(doc_id):
        return next(c for c in clusters if doc_id == c.root_doc_id or doc_id in c.member_doc_ids)
    cl = find_cluster("doc-a")
    assert "doc-a2" in cl.member_doc_ids  # near-dup 병합
    assert "doc-b" not in cl.member_doc_ids and cl.root_doc_id != "doc-b"


def test_unrelated_docs_separate_clusters():
    d = Deduplicator()
    docs = [
        _doc("doc-a", TEXT_A, "2026-08-01T00:00:00+00:00", "official"),
        _doc("doc-b", TEXT_B, "2026-08-01T00:00:00+00:00", "press"),
    ]
    clusters = d.dedup(docs)
    assert len(clusters) == 2


# ---- 3. root 선정 ----
def test_root_is_earliest_publication():
    d = Deduplicator()
    docs = [
        _doc("doc-late", TEXT_A_NEAR, "2026-08-03T00:00:00+00:00", "press"),
        _doc("doc-early", TEXT_A, "2026-08-01T00:00:00+00:00", "official"),
    ]
    cl = d.dedup(docs)[0]
    assert cl.root_doc_id == "doc-early"


def test_root_tiebreak_by_doc_id():
    d = Deduplicator()
    docs = [
        _doc("doc-z", TEXT_A, "2026-08-01T00:00:00+00:00", "press"),
        _doc("doc-a", TEXT_A_NEAR, "2026-08-01T00:00:00+00:00", "press"),
    ]
    cl = d.dedup(docs)[0]
    assert cl.root_doc_id == "doc-a"  # 동률 → doc_id 사전순(앞)


# ---- 4. 불변식 (03 §4.3) ----
def test_independent_subset_member_root_disjoint():
    d = Deduplicator()
    docs = [
        _doc("doc-root", TEXT_A, "2026-08-01T00:00:00+00:00", "official"),
        # 복제인데 독립 추가 문장 포함
        _doc("doc-copy-plus", TEXT_A_NEAR + " The company also announced a stock buyback.", "2026-08-02T00:00:00+00:00", "press"),
    ]
    cl = d.dedup(docs)[0]
    assert set(cl.independent_addition_doc_ids) <= set(cl.member_doc_ids)  # ⊆
    assert cl.root_doc_id not in cl.member_doc_ids
    assert cl.root_doc_id not in cl.independent_addition_doc_ids


# ---- 5. 결정성 ----
def test_deduplication_is_deterministic():
    d = Deduplicator()
    docs = [  # 순서 뒤섞어도 동일 cluster 결정 (재현성, §4.2)
        _doc("doc-copy", TEXT_A_NEAR, "2026-08-02T00:00:00+00:00", "press"),
        _doc("doc-root", TEXT_A, "2026-08-01T00:00:00+00:00", "official"),
    ]
    c1 = d.dedup(docs)
    c2 = d.dedup(list(reversed(docs)))
    # cluster의 (member) 집합이 일치
    def sig(clusters):
        return sorted(frozenset(c.member_doc_ids) for c in clusters)
    assert sig(c1) == sig(c2)


# ---- 6. 버전 상수 ----
def test_dedup_version_constant():
    assert isinstance(DEDUP_VERSION, str) and len(DEDUP_VERSION) > 0
    assert Cluster.__dataclass_fields__["cluster_id"].default is None or isinstance(DEDUP_VERSION, str)
