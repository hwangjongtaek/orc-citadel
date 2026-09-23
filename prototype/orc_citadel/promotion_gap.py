"""승격 공백 관측 — raw 에 내구화됐지만 존에 없는 문서 (03 §8.1, 11 §2.2).

2026-09-23 prod 에서 **55건이 이틀간 승격 없이 방치됐고 아무도 몰랐다.** 수집은
성공 메트릭을 남기고 끝났고, 승격은 다른 프로세스의 일이라 수집 런의 어떤 수치도
이 공백을 비추지 않았다. 승격이 always-on consumer 로 옮겨간 뒤에도 그 프로세스가
멈추면 같은 침묵이 그대로 재현된다 — 실제로 같은 날 consumer 는 무한 재기동
중이었다.

여기서는 공백을 **수치로** 만든다. 판정 기준은 단순하다: raw 샤드에 있는 doc_id
중 `normalized.documents` 에 없는 것의 수. 집계는 `new_doc_ids` 의 on-disk
anti-join 을 그대로 쓴다 — 코퍼스 크기의 파이썬 집합을 만들지 않는다.

정직 경계 (§6.2):
- 파싱 불가로 격리(quarantine)된 문서는 영원히 승격되지 않으므로 **상수 공백**으로
  남는다. 이 모듈은 그것을 0으로 보정하지 않는다 — 승격 불가 문서도 공백이다.
  같은 doc_id 가 매일 sample 에 반복되면 격리 건으로 읽어야 한다.
- 관측 실패를 0으로 보고하지 않는다. 호출자가 실패를 그대로 드러내야 한다.
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass

from .incremental_promote import new_doc_ids

# 로그·메트릭에 실을 근거 doc_id 상한. 공백 자체는 전수 집계하되 증거는 유계다.
GAP_SAMPLE = 10


@dataclass(frozen=True)
class PromotionGap:
    """승격 공백 1회 관측 — 전수 집계 + 유계 근거."""

    gap: int
    sample: tuple[str, ...]

    @property
    def behind(self) -> bool:
        """공백이 하나라도 있으면 뒤처진 것이다 — 임계 완화 없음."""
        return self.gap > 0

    def describe(self) -> str:
        if not self.behind:
            return "promotion gap 0 — raw 전량이 존에 있다"
        shown = ", ".join(self.sample)
        suffix = " …" if len(self.sample) < self.gap else ""
        return f"promotion gap {self.gap} — 미승격 doc_id: {shown}{suffix}"


def measure_promotion_gap(raw_dir, data_dir, *,
                          sample: int = GAP_SAMPLE) -> PromotionGap:
    """raw 에 있으나 존에 없는 문서를 센다 (read-only·결정적).

    `sample` 은 로그에 남길 doc_id 개수 상한이며 집계 자체를 자르지 않는다.
    """
    gap = 0
    evidence: list[str] = []
    for doc_id in new_doc_ids(pathlib.Path(raw_dir),
                              pathlib.Path(data_dir) / "iceberg"):
        gap += 1
        if len(evidence) < sample:
            evidence.append(doc_id)
    return PromotionGap(gap=gap, sample=tuple(evidence))
