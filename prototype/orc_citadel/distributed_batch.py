"""분산 batch 처리 — k-파라미터 sharding + 병렬 실행 측정 (design 01 §6, Phase 4 DoD ①).

Phase 4 「분산 batch 처리」 — 설계 01 §6 초기 `worker = Ray Data (단일 노드 ray의 k
병렬)`. Ray Data 는 이 prototype 환경에 미설치이므로 실제 분산 백엔드는 **주입
지점(executor)으로 격리**하고, 본 모듈은 분포를 봉인하는 **결정적·read-only** 부분을
담는다:

- `shard(metas, k)` — 재결정 가능한 파티셔닝 (k-파라미터, 실제 백엔드 진입점).
- `ParallelismBench` — 병렬 실행 벽시계·speedup 측정 (mock executor, 실측 대비 mock).
- `merge_results` — 노드별 파이프라인 결과 합산 (병렬 총계).
- `throughput_docs_per_sec`·`compute_slo_gate` — MVP #9(design 10 §1.4) 계약
  재사용 → **DoD ① 처리 시간·비용 측정** 계약.

**벤치 벽시계 모델 (결정적):** 노드 벽시계 = `len(shard) × per_node_ms` (문서당
환산). 병렬 = `max(노드별)` · 순차(k=1) = `sum` → speedup = 순차/병렬. 실제 벽시계는
executor가 주입(실측 경로와 해후), 결정성은 에뮬레이션으로 봉인 (recompute_bench 의
store-hooks 패턴과 동일).

read-only (불변식 §3-3)·결정적·mock/실측 격리 원칙 (Phase 4 전 작업과 동일).
"""
from __future__ import annotations

from .pipeline_bench import throughput  # design 10 §1.4 — throughput 계약 재사용.

# design 01 §6 / 10 §1.4 — 노드당 처리 SLO (성능 nightly 경보·CI 비차단).
PER_NODE_SLO_MS = 60_000.0  # MVP 처리 예산 60초 — 재측정 시 프로파일로 조정.


def shard(metas: list, k: int) -> list[list]:
    """metas 를 `k`개 파티션으로 분할 (재결정, read-only).

    - `k ≤ 1` 또는 빈 metas → 단일 파티션 (분할 불가).
    - `k > len(metas)` → k 를 len 으로 클램프 (빈 파티션 방지).
    - round-robin(`i % k`) — 원소 보존, 밸런스(차 ≤ 1), 결정적.

    실제 Ray Data 는 이 진입점을 백엔드 shard 로 대체한다 (주입 지점).
    """
    n = len(metas)
    if n == 0 or k <= 1:
        return [metas]
    k = min(k, n)
    groups: list[list] = [[] for _ in range(k)]
    for i, m in enumerate(metas):
        groups[i % k].append(m)
    return groups


def per_node_wall_ms(size: int, per_node_ms: float) -> float:
    """노드 벽시계 = `len(shard) × per_node_ms` (결정적 병렬 모델).

    `per_node_ms` ≤ 0 (보호) → 0 — 음수·그릇된 입력 방지. 실제 실행에선 executor 가
    이 값을 실측 벽시계로 대체한다 (mock/실측 격리).
    """
    if per_node_ms <= 0:
        return 0.0
    return size * per_node_ms


def merge_results(node_results: list[dict]) -> dict:
    """노드별 파이프라인 결과 딕트 합산 → 병렬 총계.

    숫자 필드는 합산, list 필드는 접합, 기타(무시) — 분산 걸침시간(`per_doc_elapsed_ms`)
    분포를 보존한다. 빈 입력 → 빈 dict (가드).
    """
    if not node_results:
        return {}
    merged: dict = {}
    for res in node_results:
        items = res.items() if hasattr(res, "items") else vars(res).items()
        for key, val in items:
            if isinstance(val, (int, float)):
                merged[key] = merged.get(key, 0) + val
            elif isinstance(val, list):
                merged.setdefault(key, []).extend(val)
            else:
                merged.setdefault(key, val)
    return merged


class ParallelismBench:
    """병렬 실행 벽시계·speedup 측정 (mock executor, 실측 대비 mock).

    `executor(shard, per_node_ms)` → `({docs, claims, ...}, node_wall_ms)`.
    미주입 시 결정적 에뮬레이션(`per_node_wall_ms`) 사용 — 벤치 재현성.
    """

    def __init__(self, executor=None):
        self._executor = executor

    def run(self, metas: list, k: int, per_node_ms: float = 0.0) -> dict:
        """metas 를 k 병렬로 실행·측정 — DoD ① 처리 시간.

        반환: `{wall_ms, docs, parallelism, k, nodes_used, speedup}`
        - `wall_ms` = 병렬 벽시계 = `max(노드별)` (k=1 은 순차 = sum).
        - `speedup` = 순차(k=1) 벽시계 / 병렬 벽시계 (≥1 — 병렬 이득).
        """
        groups = shard(metas, k)
        if self._executor is not None:
            results = []
            node_walls = []
            for g in groups:
                counts, node_wall = self._executor(g, per_node_ms)
                results.append(counts)
                node_walls.append(node_wall)
            merged = merge_results(results)
            docs = merged.get("docs", 0)
            nodes_used = len(groups) if len(groups) <= len(metas) or not metas else 1
            if not metas:
                nodes_used = 0
        else:
            docs = len(metas)
            node_walls = [per_node_wall_ms(len(g), per_node_ms) for g in groups]
            nodes_used = len(groups) if metas else 0

        parallel_wall = max(node_walls) if node_walls else 0.0
        sequential_wall = sum(node_walls)  # k=1 → 단일 그룹 = 전체 문서
        speedup = (sequential_wall / parallel_wall) if parallel_wall > 0 else 0.0
        return {
            "wall_ms": round(parallel_wall, 3),
            "docs": docs,
            "parallelism": len(groups),
            "k": k,
            "nodes_used": nodes_used,
            "speedup": round(speedup, 3),
        }


def throughput_docs_per_sec(docs_processed: int, elapsed_sec: float) -> float:
    """분산 throughput = `throughput(docs, elapsed)` — MVP #9 계약 재사용 (10 §1.4)."""
    return throughput(docs_processed, elapsed_sec)


def compute_slo_gate(per_node_ms: float | None, wall_ms: float | None) -> dict:
    """노드당 벽시계 SLO 게이트 (design 10 §1.4 — slo-gate·CI 비차단).

    실측(`per_node_ms`·`wall_ms`)이 `PER_NODE_SLO_MS` 이상이면 `violated=True`,
    `classified="slo-gate"`. None (미측정) → violated False — honest-gap (§6.2):
    실측 부재가 위반이 아니다. read-only·결정적.
    """
    if per_node_ms is None or wall_ms is None:
        return {"violated": False, "classified": "not-measured",
                "threshold_ms": PER_NODE_SLO_MS}
    violated = max(per_node_ms, wall_ms) >= PER_NODE_SLO_MS
    return {"violated": violated,
            "classified": "slo-gate" if violated else "ok",
            "threshold_ms": PER_NODE_SLO_MS,
            "per_node_ms": per_node_ms, "wall_ms": wall_ms}
