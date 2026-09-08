"""Nightly 수집 래퍼 (1번 시간 축 전환 — A26, cron 전용).

세션 빈도의 순시 RSS 폴링(P24 이 저가치)을 **일 단위 스케줄**로 전환해 "피드
갱신 대기" 블로커를 해소한다 (방향성 제안 1번). HTTP 커넥터(RSS/sitemap) 신규
만 수집 — arXiv 10만 bulk 는 이미 과거 연대 소진이라 매일 재시도가 과부하
(A10·§6.2 서신호 bulk 재수집 금지), 세션/사용자 인계 실행으로 유지.

- `collect_rss`/`collect_sitemap`(`known_urls=S1 URL-skip`) 직접 호출 — 피드
  갱신분만 신규 저장, 무중복 (URL-skip + content-hash S2).
- read-only 외부 GET, LLM 불사용 → `.env`(LLM credential) 불필요.
- 저장은 `data/raw/<source>/...` (gitignore) — 로그는 stdout.
- cron 등재: `crontab` 예
   0 7 * * * cd <repo>/prototype && .venv/bin/python scripts/nightly_collect.py >> /tmp/orc_nightly_collect.log 2>&1
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent  # prototype/
sys.path.insert(0, str(_REPO))

from orc_citadel.collect_large import SOURCES, _stored_urls, collect_rss, collect_sitemap


def main(slo_log=None) -> dict:
    """수집 실행 — 런 요약 반환 (run_metrics flush 입력 셰이프).

    `slo_log`(SloObservationLog) 주입 시 커넥터가 SLO-05 시도/성공을 기록한다 —
    부재 시 무기록(기존 동작 그대로, 선택 주입).
    """
    print("== nightly collect (RSS/sitemap 신규만) ==", flush=True)
    total_new = 0
    sources: dict[str, dict] = {}
    for source_id, (kind, url) in SOURCES.items():
        known = _stored_urls(source_id)
        if kind == "sitemap":
            c = collect_sitemap(url, source_id, slo_log=slo_log, known_urls=known)
        else:
            c = collect_rss(url, source_id, slo_log=slo_log, known_urls=known)
        print(f"[{source_id}] ({kind}) saved={c['saved']} skipped={c['skipped']} "
              f"errors={c['errors']} (known_urls={len(known)})", flush=True)
        sources[source_id] = {"saved": c["saved"], "skipped": c["skipped"],
                              "errors": c["errors"]}
        total_new += c["saved"]
    print(f"== nightly collect 완료: 신규 {total_new}건 ==", flush=True)
    return {"total_new": total_new, "sources": sources}


if __name__ == "__main__":
    main()
