"""S22 LLM 판정 하이브리드 E2E 스모크 — 395문서 전 체인 + ClaudeJudge 주입.

결정적 체인(추출→해소→게이트→claims→canonicalize→contradiction→assertion)에 S21의
`ClaudeJudge`를 주입해, 결정적 규칙이 미결로 남긴 쌍만 LLM이 판정하는 **하이브리드**
구성(05 §5·§6)을 실데이터로 검증한다.

비용 통제(blueprint §9.2): LLM은 미결 쌍에만, 그중에서도 `_BoundedJudge`가 첫 N개로
**상한**(기본 20)을 둔다. 상한 초과 쌍은 결정적 후보 유지(None 폴백) — 잘린 개수를
명시적으로 로그로 남긴다 (no silent truncation).
"""
from __future__ import annotations

import pathlib
from collections import Counter
from datetime import datetime, timezone

from orc_citadel.assertions import materialize
from orc_citadel.canonicalize import canonicalize_claims
from orc_citadel.claude_judge import ClaudeJudge, _AnthropicClient
from orc_citadel.contradiction import find_conflict_candidates
from orc_citadel.curated_zone import CuratedZone
from orc_citadel.extract import extract_mentions
from orc_citadel.extract_claims import extract_claims
from orc_citadel.gate import Gate
from orc_citadel.load_raw_zone import load_raw_zone
from orc_citadel.parse import extract_html, parse_document
from orc_citadel.resolve import EntityResolver

DB_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "curated_llm.duckdb"

# 비용 상한 (LLM 미결 쌍 판정 수).
LLM_CAP = 20


class _BoundedJudge:
    """첫 N개 판정만 하위 judge(LLM)로 위임, 초과는 None (결정적 후보 유지).

    카운트는 canonical/contradiction 합산 — 전체 LLM 호출을 상한으로 통제한다.
    상한 초과분은 None -> 호출 측이 결정적 결과를 그대로 유지 (ADR-507, 결정성 안전).
    """

    def __init__(self, inner, cap: int = LLM_CAP):
        self._inner = inner
        self._cap = cap
        self._n = 0
        self.calls: list[str] = []
        # 영속용 — 실제 호출된 (kind, pair, verdict dict) 기록.
        self.verdicts: list[tuple[str, tuple[str, str], dict | None]] = []

    def _maybe(self, fn_name: str, pair: tuple[str, str], fn):
        if self._n >= self._cap:
            self.calls.append(f"{fn_name}:capped")
            return None
        self._n += 1
        self.calls.append(f"{fn_name}:{pair[0]}")
        out = fn(pair)
        self.verdicts.append((fn_name, pair, out))
        return out

    def judge_canonicalization(self, pair: tuple[str, str]):
        return self._maybe("canon", pair, self._inner.judge_canonicalization)

    def judge_contradiction(self, pair: tuple[str, str]):
        return self._maybe("conf", pair, self._inner.judge_contradiction)


def persist_llm_verdicts(zone, bounded: _BoundedJudge) -> None:
    """_BoundedJudge가 실제 LLM으로 판정한 결과를 curated zone에 영속 (S23).

    canonical: 인자(dict)를 canonical_llm_records row로, contradiction: conflict_verdicts.
    version_tuple은 판정 dict에 포함된 5축(07 §6.1)을 그대로 사용, 없으면 기본.
    """
    # S21 ClaudeJudge는 version 키를 평면(flat: model_id/prompt_template_hash 등)으로
    # 붙인다 → 03 §7.1 5축 `version_tuple` JSON으로 조립해 저장.
    def _version_tuple(v: dict) -> dict:
        return {
            "ontology_version": v.get("ontology_version", "1.0.0"),
            "schema_version": v.get("output_schema_version", "0.1.0"),
            "prompt_template_hash": v.get("prompt_template_hash", ""),
            "model_id": v.get("model_id", ""),
            "extraction_code_version": "p1",
        }

    for kind, pair, v in bounded.verdicts:
        if v is None:
            continue
        a, b = pair
        vt = _version_tuple(v)
        if kind == "canon":
            if "relation" in v:
                zone.persist_canonical_llm_record(
                    claim_id_a=a, claim_id_b=b, relation=v["relation"],
                    canonical_text=v.get("canonical_text", ""),
                    confidence=float(v.get("confidence", 0.0)),
                    rationale=v.get("rationale", ""), version_tuple=vt,
                    judged_by=v.get("judged_by", "llm"),
                )
        elif kind == "conf":
            if "verdict" in v:
                zone.persist_conflict_verdict(
                    claim_id_a=a, claim_id_b=b, verdict=v["verdict"],
                    conflict_type=v.get("conflict_type"),
                    rationale=v.get("rationale", ""),
                    confidence=float(v.get("confidence", 0.0)),
                    version_tuple=vt, judged_by=v.get("judged_by", "llm"),
                )


def _build_bounded_judge() -> _BoundedJudge:
    """실 ClaudeJudge 위에 상한 래퍼 — proxy 미가용이면 stub 폴백 (오프라인 격리)."""
    inner = ClaudeJudge()
    try:
        inner = ClaudeJudge(client=_AnthropicClient(model="bunker-flash"))
    except Exception:
        pass  # proxy 미가용 → stub 폴백.
    return _BoundedJudge(inner)


def main() -> None:
    store, metas = load_raw_zone()
    print(f"== LLM 하이브리드 E2E 스모크: {len(metas)} raw docs (LLM cap={LLM_CAP}) ==")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    zone = CuratedZone(str(DB_PATH))
    zone.initialize()
    resolver = EntityResolver()
    gate = Gate()

    agg = Counter()
    all_claims = []
    resolved_mention_ids = []
    for m in metas:
        try:
            doc = extract_html(m["content"], m["url"])
        except Exception:
            agg["parse_fail"] += 1
            continue
        segs = parse_document(m["doc_id"], doc)
        ms = extract_mentions(m["doc_id"], doc, segs)
        for men in ms:
            zone.persist_mention(men)
        agg["mentions"] += len(ms)
        entities, resolved = resolver.resolve(m["doc_id"], ms)
        for e in entities:
            zone.persist_resolved(e, resolved)
        for rm in resolved:
            r = gate.evaluate_mention(rm.mention, resolved_entity_id=rm.resolved_entity_id)
            if r.promote:
                zone.set_mention_authoritative(rm.mention.mention_id)
                resolved_mention_ids.append(rm.mention.mention_id)
        claims = extract_claims(m["doc_id"], segs, resolved, {e.entity_id: e for e in entities})
        for c in claims:
            zone.persist_claim(c)
            cresult = gate.evaluate(c)
            zone.update_claim_status(c.claim_candidate_id, cresult.status,
                                     ",".join(cresult.reasons) if cresult.reasons else None)
            if cresult.promote:
                mut = next((mm["mutation_id"] for mm in gate.mutations()
                            if mm["op"] == "create_node"
                            and mm["element_ref"] == c.claim_candidate_id), "")
                observed = doc.publication_time or datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
                a = materialize(c, observed_at=observed, mutation=mut)
                zone.persist_assertion(a)
        all_claims.extend(claims)

    promoted = [c for c in all_claims
                if gate.result(c.claim_candidate_id) is not None
                and gate.result(c.claim_candidate_id).promote]

    # --- 결정적 baseline (judge 미주입) → LLM 상한 내 비교. ---
    canon_base = canonicalize_claims(promoted)
    conf_base = find_conflict_candidates(all_claims)
    print(f"\n[결정적 baseline] canonical={len(canon_base)} conflict={len(conf_base)}")

    judge = _build_bounded_judge()
    canon_hy = canonicalize_claims(promoted, judge=judge)
    conf_hy = find_conflict_candidates(all_claims, judge=judge)

    judge_kind = "llm" if isinstance(judge._inner, ClaudeJudge) \
        and judge._inner._client is not None else "stub"
    llm_calls = sum(1 for c in judge.calls if not c.endswith(":capped"))
    capped = sum(1 for c in judge.calls if c.endswith(":capped"))
    llm_conf = [c for c in conf_hy if c.judged_by == "llm"]

    print(f"[하이브리드] judge={judge_kind} canonical={len(canon_hy)} "
          f"conflict={len(conf_hy)}")
    print(f"[LLM] 실제 판정 호출={llm_calls}  상한초과(결정적 유지)={capped}")
    print(f"canonical delta: {len(canon_hy) - len(canon_base)} "
          f"conflict delta: {len(conf_hy) - len(conf_base)}")
    print(f"conflict judged_by=llm: {len(llm_conf)}")
    for c in llm_conf[:5]:
        print(f"   {c.claim_id_a}×{c.claim_id_b} [{c.conflict_type}] {c.rationale[:70]}")

    # S23: LLM 판정 산출물 영속 (version tuple 포함).
    persist_llm_verdicts(zone, judge)
    print(f"[영속] canonical_llm_records={len(zone.canonical_llm_records())} "
          f"conflict_verdicts={len(zone.conflict_verdicts())}")

    # --- 결정성 불변식: 동일 doc 재추출 → 동일 mention id. ---
    doc0 = metas[0]
    d0 = extract_html(doc0["content"], doc0["url"])
    s0 = parse_document(doc0["doc_id"], d0)
    m0a = extract_mentions(doc0["doc_id"], d0, s0)
    m0b = extract_mentions(doc0["doc_id"], d0, s0)
    assert [x.mention_id for x in m0a] == [x.mention_id for x in m0b]
    print("결정성: 동일 doc 재추출 → 동일 mention id ✓")

    zone.close()
    print("\n== ALL OK (LLM 하이브리드) ==")


if __name__ == "__main__":
    main()
