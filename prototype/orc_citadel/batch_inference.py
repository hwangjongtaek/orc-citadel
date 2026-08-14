"""대량 embedding·LLM batch inference — 확장 지점 계약 (design 07 §2.2, 08 §2.3, Phase 4 DoD ①).

Phase 4 「대량 embedding·LLM batch inference」 — 08(검색) 과 07(LLM) 의 inference
단계 실경로를 봉인한다.

- **embedding (08 §2.3, ADR-802·809):** dense embedding `BAAI/bge-m3`(1024-dim,
  cosine) 핀은 08 소유. 임베딩 대상은 **segment 문장 + claim `canonical_text` 만**
  (ADR-802 — 문서 전체·evidence 는 비임베딩, provenance 로 연결). 모델·차원 변경은
  `index_version` bump → 전량 reindex(08 §2.1).
- **embedding batch:** `embed_texts` — 대량 대상 일괄 임베딩. 실제 임베딩 백엔드는
  **주입(executor)으로 격리**, 결정성은 순수 에뮬레이션으로 봉인 (mock/실측 격리,
  Phase 4 전 작업과 동일).
- **LLM batch (07 §2.2):** L3 대량 추출(`claude-sonnet-5`)은 Message Batches
  (비-latency-민감, **50% 절감**). `batch_infer` + `batch_inference_cost` 로 일괄
  호출·비용 절감 계약을 봉인 (배치 할인 = MESSAGE_BATCHES_DISCOUNT).
- **DoD ① 측정:** `inference_throughput`·`compute_inference_slo` — 처리 시간·SLO
  게이트 (10 §1.4, slo-gate·CI 비차단, 미측정은 honest-gap §6.2).

read-only(불변식 §3-3)·결정적·mock/실측 격리 원칙 (Phase 4 전 작업과 동일).
"""
from __future__ import annotations

import random

from .pipeline_bench import throughput  # design 10 §1.4 — throughput 계약 재사용.

# ADR-809·08 §2.3 — embedding 핀 (08 소유, 07 은 참조만). 차원 변경 → index_version bump.
EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIM = 1024
EMBEDDING_SPACE = "cosinesimil"

# 08 §2.3 / ADR-802 — 임베딩 대상 = segment 문장 + claim canonical_text 만.
EMBEDDABLE_KINDS = frozenset({"segment", "claim"})

# 07 §2.2 — L3 대량 추출 tier (Message Batches, 비-latency-민감).
BATCH_TIER = "claude-sonnet-5"
# 07 §2.2 — Message Batches 50% 절감.
MESSAGE_BATCHES_DISCOUNT = 0.5

# design 10 §1.4 — inference 단계 처리 지연 SLO (성능 nightly 경보·CI 비차단).
INFERENCE_SLO_MS = 60_000.0  # 대량 inference 배치 당 예산 60초 (재측정 시 프로파일로 조정).


def embedding_index_version(model: str = EMBEDDING_MODEL,
                            dim: int = EMBEDDING_DIM) -> str:
    """index_version — 모델·차원 핀의 축약 (08 §2.1 index_version bump 트리거).

    모델·차원 중 하나라도 바뀌면 index_version 이 달라져 전량 reindex 를 유발해야
    한다 (불변식 §3-1 — 인덱스는 파생물). 결정적·read-only.
    """
    return f"{model}:{dim}"


def embeddable_kind(kind: str) -> bool:
    """임베딩 가능 대상인가 — segment/claim 만 (ADR-802, 문서·evidence 제외).

    evidence 는 소속 segment/claim 벡터로 검색 후 provenance 로 연결한다 (08 §1.1②).
    """
    return kind in EMBEDDABLE_KINDS


def _deterministic_embed(text: str, dim: int) -> list[float]:
    """결정적 pseudo-embedding (실측 백엔드 부재 시 에뮬레이션).

    `random.Random(text)` 시드 → 같은 텍스트는 항상 같은 벡터 (결정성). 실제
    embedding model 은 executor 로 주입해 실측 경로와 격리한다 (mock/실측 격리).
    """
    rng = random.Random(text)
    return [round(rng.uniform(-1.0, 1.0), 6) for _ in range(dim)]


def embed_texts(texts: list[str], executor=None,
                dim: int = EMBEDDING_DIM,
                model: str = EMBEDDING_MODEL) -> list[dict]:
    """대량 텍스트 일괄 임베딩 (08 §2.3). 결정·read-only.

    `executor(texts, dim, model)` → `[{text_index, text, embedding, model, dim}]`
    를 반환할 수 있다 (실측 백엔드 주입). 미주입 시 결정적 에뮬레이션 사용.
    각 항목에 `embedding_model`·`index_version` 를 부착 (08 §2.1 인덱스 핀 정합).
    """
    if executor is not None:
        return executor(texts, dim, model)
    iv = embedding_index_version(model, dim)
    out = []
    for i, t in enumerate(texts):
        out.append({
            "text_index": i,
            "text": t,
            "embedding": _deterministic_embed(t or "", dim),
            "embedding_model": model,
            "dim": dim,
            "index_version": iv,
        })
    return out


def batch_infer(items: list[dict], executor=None) -> dict:
    """L3 대량 추출 — Message Batches 일괄 호출 (07 §2.2).

    `executor(items)` → `[{index, text, result, ...}]` (주입 지점, 실측 LLM 경로).
    미주입 시 결정적 mock — 각 항목을 `pending` 으로 표시해 **실측 부재를 드러낸다**
    (honest-gap §6.2, 진공 통과 금지). `model` = BATCH_TIER (L3 alias).
    """
    if executor is not None:
        results = executor(items)
        return {"results": results, "calls": len(results),
                "model": BATCH_TIER}
    return {
        "results": [
            {"index": i, "text": it.get("text", ""),
             "model": BATCH_TIER, "status": "pending"}
            for i, it in enumerate(items)
        ],
        "calls": len(items),
        "model": BATCH_TIER,
        "batch": True,  # Message Batches 경로임을 명시.
    }


def batch_inference_cost(n_calls: int, cost_per_call: float) -> dict:
    """일괄 inference 비용 — 순차 대비 batch 50% 절감 (07 §2.2).

    `sequential = n × cost_per_call`, `batch = sequential × MESSAGE_BATCHES_DISCOUNT`.
    `saving_ratio` = 1 - batch/sequential (없으면 0). DoD ① 비용 측정 계약.
    """
    sequential = n_calls * cost_per_call
    batch = sequential * MESSAGE_BATCHES_DISCOUNT
    ratio = (1.0 - MESSAGE_BATCHES_DISCOUNT) if sequential > 0 else 0.0
    return {"sequential_cost": round(sequential, 6),
            "batch_cost": round(batch, 6),
            "saving_usd": round(sequential - batch, 6),
            "saving_ratio": round(ratio, 6),
            "discount": MESSAGE_BATCHES_DISCOUNT}


def inference_throughput(items_processed: int, elapsed_ms: float) -> float:
    """inference throughput = `throughput(items, elapsed_sec)` (10 §1.4 재사용)."""
    return throughput(items_processed, (elapsed_ms or 0.0) / 1000.0)


def compute_inference_slo(elapsed_ms: float | None) -> dict:
    """inference 지연 SLO 게이트 (10 §1.4 slo-gate·CI 비차단).

    `elapsed_ms` 가 `INFERENCE_SLO_MS` 이상이면 `violated=True·classified="slo-gate"`.
    None(미측정) → violated False · `classified="not-measured"` — honest-gap (§6.2):
    실측 부재가 위반이 아니라 OK 도 아니다. read-only·결정적.
    """
    if elapsed_ms is None:
        return {"violated": False, "classified": "not-measured",
                "slo_ms": INFERENCE_SLO_MS}
    violated = elapsed_ms >= INFERENCE_SLO_MS
    return {"violated": violated,
            "classified": "slo-gate" if violated else "ok",
            "slo_ms": INFERENCE_SLO_MS, "elapsed_ms": elapsed_ms}
