"""존 부트스트랩 — 배포가 보장하는 것과 이관이 하는 일을 가른다 (03 §1, 11 §2.2).

2026-09-22 cutover 배포에서 스택이 뜨자 viewer 가 `NoSuchTableError` 로 죽었다.
배포 어디에도 Iceberg 테이블을 만드는 단계가 없었고, 사람이 이관 스크립트를 손으로
돌려 메웠다. 그 상태로 두면 다음 호스트에서 같은 함정이 그대로 재현된다.

**"이관을 배포에 걸자" 는 틀린 답이다.** `migrate()` 는 대상이 원본과 어긋나고
비어 있지 않으면 `zone.reset()` 으로 전량 삭제 후 legacy 로 덮어쓴다 — 이관의
정의상 맞는 동작이지만, 살아 있는 시스템에서는 파괴다. 2026-09-26 prod 실측으로
그 크기가 확인됐다: curated `mentions` **656 vs legacy 494**, `dup_signatures`
**303 vs 183** — 배포마다 이관이 돌았다면 cutover 이후 이벤트 경로 산출이 통째로
사라진다. legacy DuckDB 는 롤백 경로로 **의도적으로 남겨둔** 파일이라 "원본이
있으면 이관" 이라는 규칙도 성립하지 않는다.

그래서 둘로 나눈다:
- **배포가 보장하는 것 = 초기화**. 멱등이고 legacy 와 무관하며, 신규 호스트든
  운영 중인 호스트든 같은 결과다. 이 모듈의 `bootstrap_zones`.
- **이관 = 일회성 cutover 도구**. 살아 있는 존을 말없이 지우지 못하도록
  `guard_divergent_target` 이 막고, 운영자가 `--force` 로 명시해야 통과한다.
"""
from __future__ import annotations

import pathlib

from .curated_zone import CuratedZone
from .iceberg_zone import NormalizedZone


class DivergentTarget(RuntimeError):
    """The target zone holds rows the migration source does not know about."""


def guard_divergent_target(visible: dict[str, int], *, force: bool, kind: str) -> None:
    """비어 있지 않은 대상을 지우려 할 때 멈춘다 — 무엇이 사라지는지 말하면서.

    빈 대상(정상 cutover)은 그냥 통과한다. `force` 는 운영자가 "legacy 를 정본으로
    되돌린다" 고 명시적으로 선언한 경우다.
    """
    populated = {name: count for name, count in visible.items() if count}
    if not populated or force:
        return
    rows = ", ".join(f"{name}={count}" for name, count in sorted(populated.items()))
    raise DivergentTarget(
        f"{kind} 대상 존이 원본과 어긋나며 비어 있지 않다 — 이관은 이 행들을 "
        f"삭제하고 legacy 로 덮어쓴다: {rows}. 이관이 정말 의도라면 --force 로 "
        f"명시하라 (운영 중 시스템이면 거의 항상 의도가 아니다)."
    )


def bootstrap_zones(data_dir: str | pathlib.Path) -> dict[str, dict[str, int]]:
    """Iceberg 테이블을 멱등 생성하고 현재 행 수를 반환한다 (이관하지 않는다)."""
    root = pathlib.Path(data_dir) / "iceberg"
    normalized = NormalizedZone(root)
    curated = CuratedZone(root)
    try:
        normalized.initialize()
        curated.initialize()
        return {"normalized": normalized.counts(), "curated": curated.counts()}
    finally:
        curated.close()
        normalized.close()


def main() -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=os.environ.get("ORC_DATA_DIR", "data"))
    args = parser.parse_args()
    summary = bootstrap_zones(args.data_dir)
    print(f"[zone-init] normalized={summary['normalized']['documents']} documents "
          f"curated={summary['curated']['mentions']} mentions (초기화 완료·이관 없음)",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
