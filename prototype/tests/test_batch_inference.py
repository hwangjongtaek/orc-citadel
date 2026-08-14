"""대량 embedding·LLM batch inference — 08 §2.3·ADR-802/809 + 07 §2.2 (Phase 4 DoD ①) TDD.

Phase 4 「대량 embedding·LLM batch inference」 — 08(검색)·07(LLM) 의 inference 단계
확장 지점을 봉인한다.

- **embedding 핀 (08 소유, ADR-809):** `BAAI/bge-m3`(1024-dim, cosine). 임베딩 대상은
  **segment/claim 만** (ADR-802 — 문서·evidence 비임베딩, provenance 로 연결).
- **index_version:** 모델·차원 핀 축약 — 변경 시 전량 reindex 트리거 (불변식 §3-1).
- **LLM batch (07 §2.2):** L3(`claude-sonnet-5`) Message Batches, **50% 절감**.
- **DoD ① 측정:** throughput·inference SLO (10 §1.4 slo-gate, 미측정 honest-gap §6.2).

결정적·read-only·mock/실측 격리 원칙 (Phase 4 전 작업과 동일 — executor 주입).
"""
from __future__ import annotations

import pytest

from orc_citadel.batch_inference import (
    BATCH_TIER,
    EMBEDDABLE_KINDS,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    EMBEDDING_SPACE,
    INFERENCE_SLO_MS,
    MESSAGE_BATCHES_DISCOUNT,
    batch_infer,
    batch_inference_cost,
    compute_inference_slo,
    embed_texts,
    embeddable_kind,
    embedding_index_version,
    inference_throughput,
)


# --- embedding 핀 (08 §2.3, ADR-809) ----------------------------------------


def test_embedding_pin_bge_m3_1024_cosine():
    """embedding 핀 = BAAI/bge-m3, 1024-dim, cosine (08 §2.3, ADR-809 — 08 소유)."""
    assert EMBEDDING_MODEL == "BAAI/bge-m3"
    assert EMBEDDING_DIM == 1024
    assert EMBEDDING_SPACE == "cosinesimil"


def test_embeddable_kind_only_segment_claim():
    """임베딩 대상은 segment/claim 만 (ADR-802 — 문서·evidence 비임베딩)."""
    assert embeddable_kind("segment")
    assert embeddable_kind("claim")
    assert not embeddable_kind("document")
    assert not embeddable_kind("evidence")
    assert not embeddable_kind("anything_else")


def test_embeddable_kinds_set_matches_contract():
    """EMBEDDABLE_KINDS = {segment, claim} 정확히 (08 §1.1②·ADR-802)."""
    assert EMBEDDABLE_KINDS == frozenset({"segment", "claim"})


# --- index_version (08 §2.1 — 재구축 트리거) ---------------------------------


def test_index_version_pins_model_and_dim():
    """index_version = model:dim 축약 — 변경 시 전량 reindex 트리거."""
    assert embedding_index_version() == f"{EMBEDDING_MODEL}:{EMBEDDING_DIM}"
    assert embedding_index_version("BAII/x", 512) == "BAII/x:512"


def test_index_version_changes_on_model_or_dim():
    """모델·차원 하나라도 바뀌면 index_version 이 달라져야 한다 (불변식 §3-1)."""
    base = embedding_index_version()
    assert embedding_index_version(model="other") != base
    assert embedding_index_version(dim=768) != base


def test_index_version_is_deterministic():
    """동일 핀 → 동일 index_version (결정성)."""
    assert embedding_index_version() == embedding_index_version()


# --- embed_texts (08 §2.3) --------------------------------------------------


def test_embed_texts_one_per_input():
    """각 텍스트마다 하나의 임베딩 결과 (text_index 순서 보존)."""
    out = embed_texts(["a", "b", "c"])
    assert len(out) == 3
    assert [o["text_index"] for o in out] == [0, 1, 2]
    assert [o["text"] for o in out] == ["a", "b", "c"]


def test_embed_dim_and_pin_attached():
    """결과에 embedding_model·dim·index_version 부착 (08 §2.1 인덱스 핀 정합)."""
    out = embed_texts(["hello"])
    assert len(out[0]["embedding"]) == EMBEDDING_DIM
    assert out[0]["embedding_model"] == EMBEDDING_MODEL
    assert out[0]["dim"] == EMBEDDING_DIM
    assert out[0]["index_version"] == embedding_index_version()


def test_embed_is_deterministic():
    """동일 텍스트 → 동일 임베딩 (결정성 — 벤치 재현성)."""
    assert embed_texts(["x"]) == embed_texts(["x"])


def test_embed_different_texts_differ():
    """서로 다른 텍스트는 서로 다른 임베딩 (정체성 보존)."""
    a = embed_texts(["alpha"])[0]["embedding"]
    b = embed_texts(["beta"])[0]["embedding"]
    assert a != b


def test_embed_empty_text_ok():
    """빈/공백 텍스트도 길이 보장 — dim 충족 (에뮬레이션 가드)."""
    out = embed_texts([""])
    assert len(out[0]["embedding"]) == EMBEDDING_DIM


def test_embed_executor_injected():
    """executor 주입 → 실측 백엔드 경로 위임 (mock/실측 격리)."""
    def ex(texts, dim, model):
        return [{"text_index": i, "text": t, "embedding": [1.0] * dim,
                 "embedding_model": model, "dim": dim,
                 "index_version": f"{model}:{dim}"}
                for i, t in enumerate(texts)]
    out = embed_texts(["a"], executor=ex)
    assert out[0]["embedding"][0] == 1.0


# --- batch_infer + batch_inference_cost (07 §2.2) ---------------------------


def test_batch_tier_is_l3_sonnet():
    """L3 대량 추출 tier = claude-sonnet-5 (07 §2.2, ADR-701 alias)."""
    assert BATCH_TIER == "claude-sonnet-5"


def test_batch_infer_pending_honest_gap():
    """미주입 mock 은 항목을 pending 으로 표시 — 실측 부재 드러냄 (honest-gap §6.2)."""
    res = batch_infer([{"text": "a"}, {"text": "b"}])
    assert res["batch"] is True  # Message Batches 경로 명시.
    assert res["calls"] == 2
    assert all(r["status"] == "pending" for r in res["results"])


def test_batch_infer_executor_injected():
    """executor 주입 → 실측 LLM 배치 경로 위임 (mock/실측 격리)."""
    def ex(items):
        return [{"index": i, "text": it.get("text", ""), "result": "parsed"}
                for i, it in enumerate(items)]
    res = batch_infer([{"text": "a"}], executor=ex)
    assert res["results"][0]["result"] == "parsed"
    assert res["calls"] == 1
    assert res["model"] == BATCH_TIER


def test_batch_discount_is_half():
    """Message Batches 50% 절감 (07 §2.2)."""
    assert MESSAGE_BATCHES_DISCOUNT == 0.5


def test_batch_inference_cost_half_of_sequential():
    """batch 비용 = 순차의 50% (07 §2.2 — 비용 절감 DoD ①)."""
    c = batch_inference_cost(n_calls=100, cost_per_call=0.01)
    assert c["sequential_cost"] == 1.0
    assert c["batch_cost"] == 0.5
    assert c["saving_usd"] == 0.5
    assert c["saving_ratio"] == 0.5


def test_batch_inference_cost_zero_calls():
    """호출 0 → 비용 0·절감 0 (명시적 가드, 분모 부재)."""
    c = batch_inference_cost(n_calls=0, cost_per_call=0.1)
    assert c["sequential_cost"] == 0.0
    assert c["batch_cost"] == 0.0
    assert c["saving_ratio"] == 0.0


def test_batch_inference_cost_discount_applies_even_single():
    """단일 호출도 batch 경로면 50% 적용 (비용 절감은 호출 형태에 종속)."""
    c = batch_inference_cost(n_calls=1, cost_per_call=1.0)
    assert c["batch_cost"] == 0.5


# --- DoD ① 측정 (10 §1.4) ---------------------------------------------------


def test_inference_throughput_delegates():
    """inference throughput = pipeline_bench.throughput 재사용 (10 §1.4)."""
    assert inference_throughput(50, 1000.0) == 50.0


def test_inference_slo_ok():
    """SLO 이내 → violated False · ok (10 §1.4 slo-gate)."""
    assert compute_inference_slo(10_000.0)["classified"] == "ok"
    assert compute_inference_slo(10_000.0)["violated"] is False


def test_inference_slo_violation():
    """SLO 초과 → violated True · slo-gate (CI 비차단 nightly)."""
    g = compute_inference_slo(INFERENCE_SLO_MS + 1)
    assert g["violated"] is True
    assert g["classified"] == "slo-gate"


def test_inference_slo_unmeasured_honest_gap():
    """미측정(None) → not-measured + violated False — honest-gap (§6.2)."""
    g = compute_inference_slo(None)
    assert g["classified"] == "not-measured"
    assert g["violated"] is False


# --- 불변식 (read-only·결정성) -----------------------------------------------


def test_read_only_no_mutation():
    """batch_inference 모듈은 read-only — 쓰기·mutation 미노출 (불변식 §3-3)."""
    from orc_citadel import batch_inference as bi

    for bad in ("apply", "persist", "create_node", "create_edge", "insert",
                "write", "upsert"):
        assert not hasattr(bi, bad), f"read-only 위반: {bad} 노출"


def test_embed_texts_does_not_mutate_input():
    """embed_texts 는 입력 texts 를 변경하지 않는다 (순수 함수 — read-only)."""
    texts = ["a", "b", "c"]
    snapshot = list(texts)
    embed_texts(texts)
    assert texts == snapshot


def test_inference_deterministic():
    """동일 입력 → 동일 inference 측정 (결정성 — 벤치 재현성)."""
    assert compute_inference_slo(5_000.0) == compute_inference_slo(5_000.0)
