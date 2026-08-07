"""S41 실데이터 승격 적용 + Open Question 실측 리포트 (read-mostly).

S38–S40 승격 파이프라인을 실데이터(임시 복사 zone)에 적용해 design 10 §3.1을
검증하고 Q3/Q5 최소 실측을 리포트로 산출한다.

- promotion: 5축 판정 — INITIALIZED/PROMOTED/BLOCKED(major revalidate).
- q3       : claim confidence 분포(min/max/p50) + 저신뢰 임계 후보.
- q5       : LLM 비용 상태 — 결정적 체인만이라 미측정으로 명시.

**read-mostly** (불변식 §3-3): 리포트는 조회만. 골든 영속·승격 align은 호출자가
임시 복사 zone에서 수행 (원본 zone 상태 불변). 결정적.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from orc_citadel.promotion_pipeline import PromotionPipeline


@dataclass(frozen=True)
class Phase0Report:
    promotion: dict
    q3: dict
    q5: dict
    summary: str


BASE_AXES = {
    "ontology_version": "1.0.0", "schema_version": "0.1.0",
    "prompt_template_hash": "sha256:phase0", "model_id": "claude-opus-4-8",
    "extraction_code_version": "p1",
}


def _promotion(zone) -> dict:
    p = PromotionPipeline(zone)
    # dry_run — zone에 영속 없음 (원본 불변, read-mostly).
    res = p.dry_run(version_tuple=BASE_AXES)
    return {
        "action": res.action,
        "passed": res.passed,
        "ontology_major_bump": res.ontology_major_bump,
        "revalidate_required": res.revalidate_required,
        "regressions": res.regressions,
        "baseline_version": None,  # dry_run — 기준선 미설정 상태 리포트.
    }


def _q3(zone) -> dict:
    claims = zone.claims()
    confs = [c["confidence"] for c in claims if c.get("confidence") is not None]
    if not confs:
        return {"count": 0, "min": None, "max": None, "p50": None,
                "low_confidence_candidate": None}
    return {
        "count": len(confs),
        "min": min(confs),
        "max": max(confs),
        "p50": statistics.median(confs),
        # 저신뢰 임계 후보 — 실측 최소값 기반 (design 10 §2.4 dev 실측 방향).
        "low_confidence_candidate": round(min(confs), 3),
    }


def _q5() -> dict:
    # 실데이터는 결정적 체인만 실행 — LLM 조사 미실행 → 비용 미측정.
    return {
        "llm_costs_measured": False,
        "note": "결정적 체인(LLM 미실행)만 실행해 문서당 LLM 비용 미측정 — LLM 조사/Campaign 실행 시 측정 (design 10 §1.4).",
    }


def generate_report(zone) -> Phase0Report:
    prom = _promotion(zone)
    q3 = _q3(zone)
    q5 = _q5()
    summary = (f"승격 판정 {prom['action']} (major={prom['ontology_major_bump']}), "
               f"Q3 confidence {q3.get('count', 0)}건 "
               f"{q3.get('min')}~{q3.get('max')}, "
               f"Q5 LLM 비용 미측정(결정적-only)")
    return Phase0Report(promotion=prom, q3=q3, q5=q5, summary=summary)
