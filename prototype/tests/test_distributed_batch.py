"""분산 batch — k-파라미터 sharding + 병렬 실행 측정 (design 01 §6, Phase 4 DoD ①) TDD.

Phase 4 「분산 batch 처리」 — Ray Data (단일 노드 ray의 k 병렬) 확장 지점을 봉인한다.
설계 01 §6: 초기 `worker = Ray Data / stage runners`, MVP #9(design 10 §1.4)는
**처리 시간·비용 측정**이 DoD ① 핵심. Ray 는 이 환경에 미설치이므로:

- `shard(metas, k)` — 재결정 가능한 파티셔닝 (순수·read-only). 실제 Ray/Spark
  백엔드는 진입점만 맞추는 **mock 실행자**로 격리 (실측 대비 mock, 리포 원칙).
- 분산 실행 결과를 `PipelineResult` 합산 · throughput·문서당 비용(MVP #9)으로
  공개 → DoD ① 처리 시간·비용 측정 계약.

**벤치 벽시계 모델 (결정적):** 노드별 벽시계 = `len(shard) × per_node_ms` (문서당
시간 환산). 병렬 실행 벽시계 = `max(노드별)` · **순차(k=1) = sum** → 병렬 이득을
정직하게 측정한다 (실측 대비 mock, 리포 원칙).

결정적·read-only·mock/실측 격리 원칙 (Phase 4 전 작업과 동일).
"""
from __future__ import annotations

import pytest

from orc_citadel.distributed_batch import (
    PER_NODE_SLO_MS,
    ParallelismBench,
    compute_slo_gate,
    merge_results,
    per_node_wall_ms,
    shard,
    throughput_docs_per_sec,
)

# --- shard: 재결정 가능 파티셔닝 --------------------------------------------


def test_shard_splits_into_k_groups():
    """metas k개 그룹으로 분할 — 원소 보존(순서 중립 merges) (design 01 §6)."""
    metas = [{"doc_id": f"d{i}"} for i in range(6)]
    groups = shard(metas, k=3)
    assert len(groups) == 3
    flat = [m["doc_id"] for g in groups for m in g]
    assert sorted(flat) == [f"d{i}" for i in range(6)]


def test_shard_k_one_is_identity():
    """k=1 → 원본 그대로 단일 파티션 (병렬 없음 시퀸셜 기준선)."""
    metas = [{"doc_id": "a"}, {"doc_id": "b"}]
    assert shard(metas, k=1) == [metas]


def test_shard_k_exceeds_len_clamps():
    """k > 문서 수 → k를 len 으로 클램프 — 빈 파티션 방지 (deadlock 등)."""
    metas = [{"doc_id": "a"}]
    assert len(shard(metas, k=4)) == 1


def test_shard_is_deterministic():
    """동일 입력·k → 동일 파티션 (결정성 원칙 — 벤치 재현성)."""
    metas = [{"doc_id": f"d{i}"} for i in range(7)]
    assert shard(metas, k=3) == shard(metas, k=3)


def test_shard_empty():
    """빈 metas → k=1 반환 (분할 불가 가드)."""
    assert shard([], k=2) == [[]]


def test_shard_balance_within_one():
    """split 배분 균형 — 그룹 크기 차 ≤ 1 (00..k-1 round-robin 근사)."""
    metas = [{"doc_id": f"d{i}"} for i in range(10)]
    groups = shard(metas, k=4)
    sizes = [len(g) for g in groups]
    assert max(sizes) - min(sizes) <= 1


# --- per_node_wall_ms / merge_results ----------------------------------------


def test_per_node_wall_scales_with_shard_size():
    """노드 벽시계 = len(shard) × per_node_ms (결정적 병렬 모델)."""
    assert per_node_wall_ms(size=4, per_node_ms=100) == 400.0


def _res(docs=0, parse_fail=0, claims=0):
    from orc_citadel.pipeline_runner import PipelineResult

    r = PipelineResult()
    r.docs = docs
    r.parse_fail = parse_fail
    r.claims = claims
    return r


def test_merge_results_sums_counts():
    """여러 노드 결과 합산 — 병렬 총계 (docs·claims·fail)."""
    merged = merge_results([_res(docs=40, claims=300), _res(docs=60, claims=700)])
    assert merged["docs"] == 100
    assert merged["claims"] == 1000
    assert merged["parse_fail"] == 0


def test_merge_results_lists_concatenate():
    """list 필드(per_doc_elapsed_ms) 는 접합 — 분산 걸침시간 분포 보존."""
    from orc_citadel.pipeline_runner import PipelineResult

    a = PipelineResult()
    a.per_doc_elapsed_ms = [10, 20]
    b = PipelineResult()
    b.per_doc_elapsed_ms = [30]
    merged = merge_results([a, b])
    assert merged["per_doc_elapsed_ms"] == [10, 20, 30]


def test_merge_results_empty():
    """노드 결과 없음 → 빈 dict (가드)."""
    assert merge_results([]) == {}


# --- ParallelismBench: 병렬 실행 측정 (mock 실행자) -------------------------


def _fake_executor(results_by_size):
    """병렬 실행자 mock — 셔드 크기별 결과·시간 주입.

    returns: 총 docs = Σlen(shard), 노드 벽시계는 결정적 모델 per_node_wall_ms.
    """
    def run(shard_batch, per_node_ms):
        counts = {"docs": len(shard_batch), "claims": len(shard_batch) * 10}
        return counts, per_node_wall_ms(len(shard_batch), per_node_ms)
    return run


def test_parallelism_bench_parallel_wall_is_max():
    """병렬 벽시계 = max(노드별) — k=2·8doc·per_doc 100 → 400ms (DoD ① 처리 시간)."""
    metas = [{"doc_id": f"d{i}"} for i in range(8)]
    bench = ParallelismBench(executor=_fake_executor(None))
    res = bench.run(metas, k=2, per_node_ms=100)
    assert res["wall_ms"] == 400.0          # (4+4)×100, 병렬=max
    assert res["parallelism"] == 2


def test_parallelism_bench_k1_sequential_wall_is_sum():
    """k=1 (순차) 벽시계 = 전체 문서 × per_node — 병렬 이득 비교 기준선."""
    metas = [{"doc_id": f"d{i}"} for i in range(8)]
    bench = ParallelismBench(executor=_fake_executor(None))
    res = bench.run(metas, k=1, per_node_ms=100)
    assert res["wall_ms"] == 800.0          # 8×100, 순차=sum


def test_parallelism_bench_reports_speedup():
    """speedup = 순차/병렬 (k=4, N=16, per_doc 50 → 800/200 = 4.0)."""
    metas = [{"doc_id": f"d{i}"} for i in range(16)]
    bench = ParallelismBench(executor=_fake_executor(None))
    res = bench.run(metas, k=4, per_node_ms=50)
    assert res["speedup"] == 4.0
    assert res["wall_ms"] == 200.0


def test_parallelism_bench_aggregates_docs():
    """전체 처리 문서 수 = 분산 총계 (k 무관 보존)."""
    metas = [{"doc_id": f"d{i}"} for i in range(8)]
    for k in (1, 2, 4):
        bench = ParallelismBench(executor=_fake_executor(None))
        res = bench.run(metas, k=k, per_node_ms=50)
        assert res["docs"] == 8


def test_parallelism_bench_reports_node_count():
    """실제 사용 노드 수 = min(k, docs) 리포트 (빈 셔드 제외)."""
    metas = [{"doc_id": f"d{i}"} for i in range(8)]
    bench = ParallelismBench(executor=_fake_executor(None))
    res = bench.run(metas, k=3, per_node_ms=50)
    assert res["k"] == 3
    assert res["nodes_used"] == 3


# --- 증분 병렬 이득 + SLO 게이트 ---------------------------------------------


def test_add_shard_speedup_edge():
    """파티션 증가 → 속도 향상 (분산 batch DoD ① 증분 이득, k1→k2 2×)."""
    metas = [{"doc_id": f"d{i}"} for i in range(8)]
    bench = ParallelismBench(executor=_fake_executor(None))
    r1 = bench.run(metas, k=1, per_node_ms=50)
    r2 = bench.run(metas, k=2, per_node_ms=50)
    assert r2["wall_ms"] <= r1["wall_ms"]


def test_compute_slo_gate_violation():
    """per-node 벽시계 ≥ PER_NODE_SLO 실측 시 slo-gate 발생 (10 §1.4 비차단)."""
    res = compute_slo_gate(per_node_ms=PER_NODE_SLO_MS + 10, wall_ms=PER_NODE_SLO_MS + 10)
    assert res["violated"] is True
    assert res["classified"] == "slo-gate"


def test_compute_slo_gate_under_threshold():
    """임계 미만 → violated False."""
    res = compute_slo_gate(per_node_ms=PER_NODE_SLO_MS - 10, wall_ms=PER_NODE_SLO_MS - 10)
    assert res["violated"] is False


def test_compute_slo_gate_empty():
    """측정 없음 → violated False (honest — 실측 부재가 위반 아님)."""
    res = compute_slo_gate(per_node_ms=None, wall_ms=None)
    assert res["violated"] is False


# --- throughput: MVP #9 계약 재사용 ------------------------------------------


def test_throughput_docs_per_sec_delegates():
    """throughput = docs/elapsed — pipeline_bench 계약 재사용 (design 10 §1.4)."""
    assert throughput_docs_per_sec(500, 10.0) == 50.0


# --- read-only·결정성 (불변식 §3-3, Phase 전 작업 공통 원칙) -----------------


def test_read_only_no_mutation():
    """분산 batch 모듈은 read-only — 쓰기·mutation 미노출 (불변식 §3-3)."""
    from orc_citadel import distributed_batch as db

    for bad in ("apply", "persist", "create_node", "create_edge", "insert",
                "write", "upsert"):
        assert not hasattr(db, bad), f"read-only 위반: {bad} 노출"


def test_shard_is_read_only_no_mutation():
    """shard 는 입력 metas 를 변경하지 않는다 — 순수 함수."""
    metas = [{"doc_id": f"d{i}"} for i in range(6)]
    snapshot = list(metas)
    shard(metas, k=2)
    assert metas == snapshot


def test_bench_is_deterministic():
    """동일 입력·k·per_node → 동일 벤치 결과 (결정성 — 재현성)."""
    metas = [{"doc_id": f"d{i}"} for i in range(8)]
    bench = ParallelismBench(executor=_fake_executor(None))
    a = bench.run(metas, k=2, per_node_ms=100)
    b = bench.run(metas, k=2, per_node_ms=100)
    assert a == b
