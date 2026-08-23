"""P1 viewer — Signal Spire (`/spire`) 데이터 계약.

`/api/spire` 응답이 (a) 5 종 트리거 카탈로그(정본 `signal_spire.TRIGGER_TYPES`)와
(b) 정직한 빈 alert feed 를 포함하는지 검증. alert 는 영속 저장소가 없어(in-memory
fire-once) 실제 mutation 이벤트에서 파생된 것만 렌더 — 없으면 빈 상태(§6.2 honest-gap).
read-only 결정적 (불변식 §3-3).
"""
from __future__ import annotations

import json
import types

from orc_citadel.viewer import Handler


def _spire(self=None):
    return json.loads(Handler._api_spire(self or types.SimpleNamespace(), {}))


def test_spire_catalog_lists_five_triggers():
    r = _spire()
    triggers = [c["trigger"] for c in r["trigger_catalog"]]
    assert triggers == [
        "contradicting_evidence", "claim_changed", "plan_to_execution",
        "new_independent_source", "confidence_threshold",
    ]
    # 각 트리거에 정본 모듈 docstring 기반 설명 제공 (허위 아님).
    assert all(c["description"] for c in r["trigger_catalog"])


def test_spire_feed_is_honest_empty():
    """영속 alert 저장소 없음 → 점화 없음은 빈 상태, 가짜 alert 금지."""
    r = _spire()
    assert r["alerts"] == []
    assert "fire_once_rule" in r
    assert "1회 점화" in r["fire_once_rule"]
