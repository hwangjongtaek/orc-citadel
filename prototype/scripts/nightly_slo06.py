"""Nightly SLO-06 실측 + 7d rolling 누적 (1번 시간 축 전환 — A26, cron 전용).

세션 빈도의 순시 SLO-06 실측(A24 n=30, 확정(잠정))을 **일 단위 스케줄**로 전환해
"7d rolling 축적" 블로커를 해소한다 (방향성 제안 1번). 매일 작은 표본의 schema
검증 결과를 `data/slo06_accum.json` 에 append 하고, 최근 7일 누적분으로
`slo06_accum.accum_slo06` 이 재확정 판정(pass_rate·within_slo)을 내린다 —
확정(잠정)→확정 전환의 운영 근거.

- `.env`(repo root) 로드 → 무비용 LLM(litellm·bunker-flash) 로 canonical/
  contradiction 판정 (build_llm_client). read-only·유한 상한(LLM_CAP).
- 개별 `record_schema` 결과를 `accum_append`(ts 부여)로 append — 순전 함수.
- 7일치가 쌓이면 `accum_slo06(days=7)` 로 재확정 판정 출력.
- cron 등재: `crontab` 예
   7 7 * * * cd <repo>/prototype && .venv/bin/python scripts/nightly_slo06.py >> /tmp/orc_nightly_slo06.log 2>&1
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent  # prototype/
sys.path.insert(0, str(_REPO))

_PROJECT_ROOT = _REPO.parent  # repo root (`.env` 위치)
DATA_DIR = _REPO / "data"
ACCUM_PATH = DATA_DIR / "slo06_accum.json"

LLM_CAP = int(os.environ.get("SLO06_LLM_CAP", "30"))

from orc_citadel.claude_judge import ClaudeJudge
from orc_citadel.slo_observation_log import SloObservationLog
from orc_citadel.slo06_accum import accum_append, accum_slo06


def _load_env() -> None:
    """repo root `.env` 를 환경변수로 로드 (build_llm_client 가 os.environ 의존)."""
    env = _PROJECT_ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


class _BoundedJudge:
    """첫 N개 판정만 LLM 위임, 초과는 None — cap 상한 (smoke 와 동일 합산)."""

    def __init__(self, inner, cap):
        self._inner, self._cap, self._n = inner, cap, 0

    def _maybe(self, fn, pair):
        if self._n >= self._cap:
            return None
        self._n += 1
        return fn(pair)

    def judge_canonicalization(self, pair):
        return self._maybe(self._inner.judge_canonicalization, pair)

    def judge_contradiction(self, pair):
        return self._maybe(self._inner.judge_contradiction, pair)


def _measure_candidates(judge):
    """실수집 원문의 결정적 체인으로 candidate 쌍 생성 → judge 판정 (read-only).

    `slo06_measure.py` 와 동일 계열 — 최대 `max_docs` 문서에서 promoted claim 쌍을
    만들고 judge 로 판정. 어떤 영속·발송도 없음(`:memory:` zone).
    """
    from orc_citadel.load_raw_zone import load_raw_zone
    from orc_citadel.parse import extract_html, parse_document
    from orc_citadel.extract import extract_mentions
    from orc_citadel.resolve import EntityResolver
    from orc_citadel.extract_claims import extract_claims
    from orc_citadel.canonicalize import canonicalize_claims
    from orc_citadel.contradiction import find_conflict_candidates
    from orc_citadel.curated_zone import CuratedZone
    from orc_citadel.gate import Gate

    store, metas = load_raw_zone()
    zone = CuratedZone(path=":memory:")
    zone.initialize()
    resolver = EntityResolver()
    gate = Gate()

    all_claims, promoted = [], []
    max_docs = int(os.environ.get("SLO06_MAX_DOCS", "200"))
    for m in metas[:max_docs]:
        try:
            doc = extract_html(m["content"], m["url"])
        except Exception:
            continue
        segs = parse_document(m["doc_id"], doc)
        ms = extract_mentions(m["doc_id"], doc, segs)
        entities, resolved = resolver.resolve(m["doc_id"], ms)
        claims = extract_claims(m["doc_id"], segs, resolved,
                                {e.entity_id: e for e in entities})
        for c in claims:
            cresult = gate.evaluate(c)
            zone.update_claim_status(c.claim_candidate_id, cresult.status,
                                     ",".join(cresult.reasons) if cresult.reasons else None)
        all_claims.extend(claims)
        promoted.extend(c for c in claims
                        if gate.result(c.claim_candidate_id) is not None
                        and gate.result(c.claim_candidate_id).promote)

    canonicalize_claims(promoted, judge=judge)
    find_conflict_candidates(all_claims, judge=judge)


def main(slo_log=None) -> dict:
    """SLO-06 실측 + 7d 누적 — 런 요약 반환 (run_metrics flush 입력 셰이프).

    `slo_log` 주입 시 호출자가 원시 관측을 소유한다(런 종료 flush 용) — 부재 시
    자체 생성(기존 동작 그대로, 선택 주입).
    """
    _load_env()
    print("== nightly SLO-06 실측 + 7d 누적 ==", flush=True)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    slo_log = slo_log if slo_log is not None else SloObservationLog()
    inner = ClaudeJudge(slo_log=slo_log)
    print(f"judge provider={getattr(inner._client, 'provider', None)!r} "
          f"model={getattr(inner._client, 'model', None)!r} cap={LLM_CAP}", flush=True)

    judge = _BoundedJudge(inner, LLM_CAP)
    _measure_candidates(judge)

    # 오늘 판정분을 누적 로그에 append (ts 부여)
    now_iso = datetime.now(timezone.utc).isoformat()
    entries = slo_log.schema_log()
    accum_append(ACCUM_PATH, entries, now=now_iso)
    print(f"오늘 {len(entries)}건 schema 판정 append (캡 유지) -> {ACCUM_PATH}", flush=True)

    # 7d rolling 재확정 판정
    today = now_iso
    for days in (7,):
        res = accum_slo06(ACCUM_PATH, days=days, now=today)
        print(f"[7d roll] n={res['n_total']} pass={res['n_pass']} "
              f"unknown={res['n_unknown']} pass_rate={res['pass_rate']} "
              f"within_slo={res['within_slo']} classified={res['classified']} "
              f"measured={res['measured']}", flush=True)
    print(f"[usage] {inner.usage()}", flush=True)
    print("== nightly SLO-06 완료 ==", flush=True)
    return {"schema_n": len(entries)}


if __name__ == "__main__":
    main()
