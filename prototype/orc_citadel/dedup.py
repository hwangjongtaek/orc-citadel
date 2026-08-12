"""S4 출처 계보·복제 축소 (design 04 §4, 03 §4.3, blueprint §8.3).

서로 다른 `doc_id` 사이의 복제·파생 관계를 판정해 `dup_clusters`로 축소한다 —
"복제 K건을 독립 K으로 세지 않음" 과대평가 방지. 순수 Python·결정적.

판정 수준 (§4.1):
  ① exact    — content hash 완전 일치
  ② near     — MinHash(shingle) 기반 Jaccard near-dup
  ③ semantic — LLM 의미적 파생 (이 prototype은 스텁 — 고비용, 후보 쌍 전용)

결정성: (doc_id, dedup_version) 하에 재생성 (02 §4.2). root 선정은
publication_time 이른 쪽 + source_type 신뢰(official/gov), 동률 doc_id 사전순.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

# 분할·정규화·MinHash 파라미터 조합을 식별 (bump → dedup 재생성, 04 §4.2).
DEDUP_VERSION = "d1"

# 기본 임계값 (Q2 실측, 2026-08-03 → 04 ADR-403 정합).
# 실수집 395문서 MinHash Jaccard 분포 측정 결과: intra-source·inter-source 모두
# 0.5~0.7에 첨두로 겹치고, 진짜 복제만 0.9+ (근접 3쌍 J=1.0이 실제 중복). 즉 단일
# MinHash 임계로는 겹치는 애매 구간(0.80~0.90)에서 near-dup을 신뢰 판정할 수 없다.
# 설계 04 ADR-403 전략에 따라: 확실한 복제(0.90+)만 minhash로 병합하고, 애매 구간은
# level-③(embedding/LLM) 후보로 위임한다. (기존 0.6은 intra 오결합 5152쌍 유발.)
JACCARD_THRESHOLD = 0.90
MIN_TEXT_CHARS = 200
MINHASH_PERMS = 64  # min-hash 회수(결정적 — 해시 시드 고정)
SHINGLE_K = 5

_WORD = re.compile(r"[a-z0-9]+")


def shingles(text: str, k: int = SHINGLE_K) -> set[str]:
    """워드 5-gram shingle set (소문자 단어 토큰)."""
    tokens = _WORD.findall(text.lower())
    return {" ".join(tokens[i:i + k]) for i in range(len(tokens) - k + 1)}


def _minhash(s: set[str], perms: int = MINHASH_PERMS) -> list[int]:
    """결정적 MinHash: 각 perm 시드로 sha256 해시의 최솟값을 취한다."""
    vals: list[int] = []
    for p in range(perms):
        m = None
        for sh in s:
            h = hashlib.sha256(f"{p}:{sh}".encode()).hexdigest()
            v = int(h[:12], 16)
            m = v if m is None else min(m, v)
        vals.append(m if m is not None else 0)
    return vals


def _jaccard_est(a: list[int], b: list[int]) -> float:
    """MinHash 시그니처에서 Jaccard 추정 (일치 비율)."""
    return sum(1 for x, y in zip(a, b) if x == y) / len(a)


@dataclass(frozen=True)
class Cluster:
    """dup_clusters row (03 §4.3)."""

    cluster_id: str
    root_doc_id: str
    member_doc_ids: tuple[str, ...]  # 파생까지 포함 전체 멤버
    independent_addition_doc_ids: tuple[str, ...]  # ⊆ member, root ∉
    dedup_method: str  # content_hash | minhash


class Deduplicator:
    """정규화 문서들을 복제 클러스터로 축소."""

    def __init__(self, jaccard_threshold: float = JACCARD_THRESHOLD) -> None:
        self._threshold = jaccard_threshold

    def dedup(self, docs: list[dict]) -> list[Cluster]:
        """input: [{doc_id, text, publication_time, source_type}] → Cluster list.

        순서와 무관하게 결정적 결과를 낸다(정렬 후 처리, §4.2 재현성).
        """
        if not docs:
            return []
        ordered = sorted(docs, key=lambda d: d["doc_id"])
        clusters = _cascade_cluster(ordered, self._threshold)
        return [_finalize(members, ordered) for members in clusters]


def _cascade_cluster(docs: list[dict], threshold: float) -> list[list[str]]:
    """① exact → ② near 계단식 병합. 각 그룹은 doc_id 목록. 결정적."""
    # ① exact: sha256(text) 동일 그룹
    by_hash: dict[str, list[str]] = {}
    for d in docs:
        by_hash.setdefault(hashlib.sha256(d["text"].encode()).hexdigest(), []).append(d["doc_id"])
    groups = [list(g) for g in by_hash.values()]

    # ② near: 결정적 MinHash 시그니처. 짧은 본문(MIN_TEXT_CHARS 미만)은 boilerplate
    # 지배라 근접성 판정의 신뢰가 낮아 near-dup 후보에서 제외한다 (level-② 한계).
    eligible = {d["doc_id"]: d for d in docs if len(d["text"]) >= MIN_TEXT_CHARS}
    sig = {did: _minhash(shingles(d["text"])) for did, d in eligible.items()}

    merged: list[list[str]] = []
    for g in groups:
        base = set(g)
        rep = next(iter(g))
        rep_sig = sig.get(rep)
        for did, d in eligible.items():
            if did in base:
                continue
            other_sig = sig[did]
            if rep_sig is not None and _jaccard_est(rep_sig, other_sig) >= threshold:
                base.add(did)
        merged.append(sorted(base))

    return _union_by_overlap(merged)


def _union_by_overlap(groups: list[list[str]]) -> list[list[str]]:
    """교집합 있는 그룹들을 합친다 (결정적, 원소 오름차순)."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # 같은 원소 포함 시 union
    seen_pairs: set[tuple[str, str]] = set()
    for g in groups:
        for a in g:
            for b in g:
                if (a, b) in seen_pairs:
                    continue
                union(a, b)
                seen_pairs.add((a, b))

    out: dict[str, list[str]] = {}
    for d_ in parent:
        out.setdefault(find(d_), []).append(d_)
    return [sorted(v) for v in out.values()]


def _finalize(members: list[str], docs_all: list[dict]) -> Cluster:
    """root/member/independent 분류 + cluster_id 발급. 결정적."""
    doc_by_id = {d["doc_id"]: d for d in docs_all}
    # root: publication_time 이른 쪽 → source_type 신뢰 → doc_id 사전순
    def trust(t: str) -> int:
        return {"official": 2, "gov": 3, "research": 1, "press": 1}.get(t, 0)

    def key(did: str) -> tuple:
        d = doc_by_id[did]
        return (d.get("publication_time") or "9999", -trust(d.get("source_type", "")), did)

    root = min(members, key=key)

    # member = 파생(비-root) 멤버. root ∉ member (03 §4.3 disjoint).
    derived = [m for m in members if m != root]
    # independent: root 텍스트에 없는 문장(추가 정보)을 가진 파생 doc.
    root_sents = {s for s in _sentences(doc_by_id[root]["text"])}
    independents = [m for m in derived if _has_new_sentence(doc_by_id[m]["text"], root_sents)]

    # 결정적 cluster_id — (정렬 members + dedup_version) 해시 (04 §4.2 재생성 계약).
    seed = "|".join(sorted(members)) + "|" + DEDUP_VERSION
    cluster_id = "clus-" + hashlib.sha256(seed.encode()).hexdigest()[:24]
    return Cluster(
        cluster_id=cluster_id,
        root_doc_id=root,
        member_doc_ids=tuple(sorted(derived)),
        independent_addition_doc_ids=tuple(sorted(independents)),
        dedup_method="minhash",
    )


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _has_new_sentence(text: str, root_sents: set[str]) -> bool:
    """text가 root에 없는 문장을 1개 이상 포함하면 독립 추가로 본다."""
    return any(s not in root_sents for s in _sentences(text))
