"""S25 그래프·어세션 질의 — bitemporal AS-OF (설계 06 §8.2, ADR-606) TDD.

06 §8.2: AS-OF는 Assertion의 valid/tx 두 축을 필터해 재현한다.
- AS-OF valid time `T_v`: `valid_from ≤ T_v < valid_to` (open lower/upper bound).
- AS-OF transaction time `T_t`: `tx_from ≤ T_t < (tx_to ?? ∞)`.
- 두 축 동시 지정으로 "특정 관찰 시점 기준, 특정 유효 시점 상태" 재현 (03 §6.3).
superseded 버전은 삭제하지 않으므로 과거 상태가 그대로 조회된다.
"""
from __future__ import annotations

from datetime import datetime, timezone

from orc_citadel.curated_zone import CuratedZone
from orc_citadel.extract_claims import ClaimCandidate


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _claim(cid: str, subj: str, pred: str, obj: str | None = None) -> ClaimCandidate:
    return ClaimCandidate(
        claim_candidate_id=cid, doc_id="doc-1", predicate=pred, subject_id=subj,
        object_id=obj, object_literal=None, modality="asserted",
        polarity="positive", confidence=0.8, seg_order=0, char_start=0,
        char_end=4, surface_fragment="x", event_type_hint=None, status="candidate",
    )


def _zone_with_assertions() -> tuple[CuratedZone, list[str]]:
    """두 assertion 어셔블 — 하나는 superseded(tx_to 있음), 하나는 현재.
    time_precision/valid/tx 필드를 06 §8.2 경계 규칙 검증에 맞춰 세팅."""
    from orc_citadel.assertions import materialize

    z = CuratedZone(":memory:")
    z.initialize()
    # 어세션 1: valid [2026-01-01, 2026-12-31), tx_from 2026-02-01, 현재(tx_to null).
    c1 = _claim("clm-1", "org-nvda", "announces", "org-cowos")
    a1 = materialize(c1, observed_at=_dt("2026-02-01T00:00:00"), mutation="mut-1")
    # valid_from/valid_to를 경계 테스트용으로 오버라이드.
    a1 = a1.__class__(
        assertion_id=a1.assertion_id, claim_id=a1.claim_id, subject_id=a1.subject_id,
        predicate=a1.predicate, object_id=a1.object_id, object_literal=a1.object_literal,
        valid_from=_dt("2026-01-01T00:00:00"), valid_to=_dt("2026-12-31T00:00:00"),
        time_precision="day", tx_from=a1.tx_from, tx_to=None,
        supersedes_id=a1.supersedes_id, mutation_id=a1.mutation_id,
        provenance_ref=a1.provenance_ref,
    )
    # 어세션 2: superseded — tx_to 2026-05-01 (이후 폐기).
    c2 = _claim("clm-2", "org-nvda", "announces", "org-tsmc")
    a2 = materialize(c2, observed_at=_dt("2026-03-01T00:00:00"), mutation="mut-2")
    a2 = a2.__class__(
        assertion_id=a2.assertion_id, claim_id=a2.claim_id, subject_id=a2.subject_id,
        predicate=a2.predicate, object_id=a2.object_id, object_literal=a2.object_literal,
        valid_from=_dt("2026-01-01T00:00:00"), valid_to=_dt("2026-12-31T00:00:00"),
        time_precision="day", tx_from=_dt("2026-03-01T00:00:00"), tx_to=_dt("2026-05-01T00:00:00"),
        supersedes_id=a2.supersedes_id, mutation_id=a2.mutation_id,
        provenance_ref=a2.provenance_ref,
    )
    z.persist_assertion(a1)
    z.persist_assertion(a2)
    return z, [a1.assertion_id, a2.assertion_id]


def test_as_of_current_valid_time_returns_current_assertion():
    """유효시점(2026-06-01) 조회 — superseded(tx 03→05) 제외, 현재만 반환."""
    z, ids = _zone_with_assertions()
    # T_t=2026-06-01 (현재) 기준: a2는 tx_to(05-01)로 이미 폐기 → 제외.
    rows = z.assertions_as_of(valid_at=_dt("2026-06-01T00:00:00"),
                              tx_at=_dt("2026-06-01T00:00:00"))
    assert ids[1] not in [r["assertion_id"] for r in rows]
    assert ids[0] in [r["assertion_id"] for r in rows]


def test_as_of_tx_before_supersede_includes_both():
    """T_t=2026-04-01(둘 다 tx_to 이전) → 두 assertion 모두 현재로서 반환."""
    z, ids = _zone_with_assertions()
    rows = z.assertions_as_of(valid_at=_dt("2026-06-01T00:00:00"),
                              tx_at=_dt("2026-04-01T00:00:00"))
    got = {r["assertion_id"] for r in rows}
    assert got == set(ids)  # supersede 전에는 두 버전 모두 "시스템이 믿던" 상태.


def test_as_of_valid_time_out_of_window_excluded():
    """T_v=2025-06-01 (valid_from 이전) → 어세션 없음 (open lower bound 위반)."""
    z, ids = _zone_with_assertions()
    rows = z.assertions_as_of(valid_at=_dt("2025-06-01T00:00:00"),
                              tx_at=_dt("2026-06-01T00:00:00"))
    assert rows == []


def test_as_of_valid_upper_bound_open_excluded():
    """T_v=2026-12-31는 valid_to(12-31)와 같음 → open 상한(exclusive) 제외."""
    z, ids = _zone_with_assertions()
    rows = z.assertions_as_of(valid_at=_dt("2026-12-31T00:00:00"),
                              tx_at=_dt("2026-06-01T00:00:00"))
    assert rows == []


def test_as_of_tx_upper_bound_open_excluded():
    """T_t=2026-05-01은 a2.tx_to와 같음 → open 상한(exclusive) 제외 (현재만)."""
    z, ids = _zone_with_assertions()
    rows = z.assertions_as_of(valid_at=_dt("2026-06-01T00:00:00"),
                              tx_at=_dt("2026-05-01T00:00:00"))
    got = {r["assertion_id"] for r in rows}
    assert ids[1] not in got  # a2는 정확히 tx_to 경계 → 제외
    assert ids[0] in got


def test_as_of_no_args_returns_all_current():
    """인자 없음 → 현재(tx_to null) 어세션 모두 반환 (현재 그래프)."""
    z, ids = _zone_with_assertions()
    rows = z.assertions_as_of()
    got = {r["assertion_id"] for r in rows}
    assert ids[0] in got
    assert ids[1] not in got  # superseded 제외
