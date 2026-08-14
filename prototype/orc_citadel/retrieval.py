"""MVP #7 SEARCH 단계 — Retrieval Agent (설계 07 §3.4, 08 §GraphRAG) — read-only.

조사 루프의 SEARCH (07 §4): 그래프 공백(gap subclaim)을 채울 후보 문서·span을
`gap → {candidates: [{doc_id, segment_id, span, score, retrieval_path}]}`로 반환.

- corpus: 멘션 `context_window`(해당 멘션 포함 문장) — 정규화 세그먼트에 등가.
- 동작: 질의 용어(주장·subject 용어)의 BM25 근사 선형 스코어로 후보 span 정렬,
  상한 k 반환, 점수 내림차순 결정적 정렬 (08 retrieval 경로 중 BM25).
- subject_id 제약: 대상 entity의 resolved 멘션만 우선 (그래프 공백을 그 행위자 span으로).
- **read-only** (불변식 §3-3): 조회만, 영속·mutation 미노출. 결정적.
"""
from __future__ import annotations

import math
import re


class RetrievalAgent:
    """그래프 공백을 채울 후보 문서·span 검색 (07 §3.4, tier L3)."""

    _PATH = "bm25::context_window"

    def __init__(self, zone, top_k: int = 5) -> None:
        self._zone = zone
        self._default_k = top_k

    def _tokens(self, text: str) -> list[str]:
        """소문자 토큰화 (단어 경계) — 결정적."""
        return re.findall(r"[a-z0-9가-힣]+", (text or "").lower())

    def _bm25_approx(self, query_terms: list[str], doc_terms: list[str],
                     df: dict[str, int], n_docs: int) -> float:
        """BM25 근사 (read-only·결정적) — tf·idf 결합 스코어.

        prototype 경량: k1=1.2, b=1.0(장문 보정), idf = ln(1 + (N - df + .5)/(df + .5)).
        """
        k1, b = 1.2, 1.0
        doc_len = len(doc_terms) or 1
        avgdl = self._avgdl
        tf_map: dict[str, int] = {}
        for t in doc_terms:
            tf_map[t] = tf_map.get(t, 0) + 1
        score = 0.0
        for t in query_terms:
            tf = tf_map.get(t, 0)
            if not tf:
                continue
            idf = math.log(1.0 + (n_docs - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5))
            denom = tf + k1 * (1 - b + b * doc_len / avgdl)
            score += idf * (tf * (k1 + 1)) / denom
        return round(score, 6)

    def _corpus(self) -> list[dict]:
        """corpus: 멘션 문장 텍스트 (doc·segment·span 메타 포함)."""
        out = []
        for m in self._zone.mentions():
            text = (m.get("context_window") or "").strip()
            if not text:
                continue
            out.append({
                "doc_id": m["doc_id"],
                "segment_id": m["segment_id"] or "",
                "surface_text": m["surface_text"],
                "resolved_entity_id": m.get("resolved_entity_id"),
                "span": text,
                "terms": self._tokens(text),
            })
        return out

    def search(self, query: dict, k: int | None = None) -> list[dict]:
        """gap → 후보 span (점수 내림차순, k 상한)."""
        k = k or self._default_k
        terms = query.get("terms") or []
        terms = [t for t in terms if t]
        subj = query.get("subject_id")
        if not terms:
            return []
        corpus = self._corpus()
        if not corpus:
            return []

        # DF·N 통계 (결정적) — BM25 idf.
        df: dict[str, int] = {}
        for doc in corpus:
            for t in set(doc["terms"]):
                df[t] = df.get(t, 0) + 1
        n_docs = len(corpus)
        avg_len = sum(len(d["terms"]) for d in corpus) / n_docs
        self._avgdl = avg_len if avg_len > 0 else 1.0

        # subject 제약 — 대상 entity resolved 멘션을 우선 배치하되 오매칭 없이
        # (전체 corpus에서 주어진 항만 스코어, subject는 span 메타로 노출).
        qset = set(terms)
        scored = []
        for d in corpus:
            hit = any(t in qset for t in d["terms"])
            if not hit:
                continue
            # subject 제약: 대상 entity의 멘션이고 해당 문장에 query 용어가 있으면 우선.
            match_subj = subj and d["resolved_entity_id"] == subj
            score = self._bm25_approx(terms, d["terms"], df, n_docs)
            # subject 일치 문장 +0.5 보정 (그래프 공백을 해당 행위자 span으로 우선).
            if match_subj:
                score += 0.5
            scored.append({
                "doc_id": d["doc_id"],
                "segment_id": d["segment_id"],
                "span": d["span"],
                "score": round(score, 6),
                "retrieval_path": self._PATH,
            })
        scored.sort(key=lambda c: (-c["score"], c["doc_id"], c["span"]))
        return scored[:k]
