"""S6 Entity Resolution — 결정적 stage-1만 (설계 05 §2.2 rule 1, ADR-507).

캐스케이드에서 **결정적 외부식별자(identifier) exact match**만 자동 병합(`SAME_AS`)
한다. 설계 ADR-507: 결정적 외부식별자 exact match가 **유일한 자동 병합 경로**. 이름·
점수·embedding·LLM 고신뢰는 비결정적이라 자동 병합 금지 → 이 scope에서는 POSSIBLY/
lexical/LLM을 스텁으로 남기고 다루지 않는다.

- blocking key = 공유 식별자(설계 §2.1 `identifier`): 동일 식별자 집합만 같은 버킷.
  식별자 없는 mention은 (type, surface)만으로 개별 버킷 (오병합 방지).
- SAME_AS 동치류 → canonical 대표 1개 (설계 02 §4-5, §3.1): 최빈 표면형이 대표명, 동률
  사전순(결정적). entity_id = (type, canonical, identifiers) 결정적 해시.
- 결정성·idempotency (03 §5): 동일 mention → 동일 entity·동일 resolved.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .extract import Mention

# 해소 규칙·파라미터 식별 — 변경 시 bump (03 §5, idempotency/재해소).
RESOLUTION_VERSION = "r1"

# canonical_name 동률 시 사전순으로 결정하므로, 식별자·표면형 사용.


@dataclass(frozen=True)
class Entity:
    entity_id: str
    mention_type: str
    canonical_name: str
    identifiers: dict = field(default_factory=dict)
    surface_forms: tuple = ()  # 동치류 멤버 표면형 (결정적 정렬)

    def to_row(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "mention_type": self.mention_type,
            "canonical_name": self.canonical_name,
            "identifiers": self.identifiers,
            "surface_forms": list(self.surface_forms),
        }


@dataclass
class ResolvedMention:
    """해소된 mention — 원 mention + 연결된 canonical Entity (또는 None)."""

    mention: Mention
    resolved: Entity | None = None

    @property
    def surface_text(self) -> str:
        return self.mention.surface_text

    @property
    def doc_id(self) -> str:
        return self.mention.doc_id

    @property
    def resolved_entity_id(self) -> str | None:
        return self.resolved.entity_id if self.resolved else None


def entity_id_for(mention_type: str, canonical_name: str, identifiers: dict) -> str:
    """결정적 entity_id — (type, canonical, identifiers) hash (03 §5)."""
    key = json.dumps(
        {"t": mention_type, "c": canonical_name,
         "i": sorted(identifiers.items())},
        ensure_ascii=False, sort_keys=True,
    )
    return "org-" + hashlib.sha256(key.encode()).hexdigest()[:24]


def _blocking_key(m: Mention) -> tuple:
    """blocking key — 공유 식별자(설계 §2.1 identifier). 식별자 없으면 surface 정확."""
    if m.identifiers:
        return ("id", tuple(sorted(m.identifiers.items())))
    return ("surface", m.mention_type, m.surface_text)


class EntityResolver:
    """결정적 해소 캐스케이드 stage-1 (식별자 exact → SAME_AS 자동 병합)."""

    def resolve(
        self, doc_id: str, mentions: list[Mention]
    ) -> tuple[list[Entity], list[ResolvedMention]]:
        """mentions를 동치류로 묶어 canonical Entity 생성·연결.

        returns (entities, resolved). entities는 동치류별 1 Entity (결정적 순서),
        resolved는 입력 mention에 대응하는 ResolvedMention 목록.
        """
        # blocking → 버킷 (같은 식별자/표면형 언급 모음).
        buckets: dict[tuple, list[Mention]] = defaultdict(list)
        for m in mentions:
            buckets[_blocking_key(m)].append(m)

        entities: list[Entity] = []
        resolved: list[ResolvedMention] = []

        # mention 순서 보존을 위해 입력 순으로 매핑 (결정성).
        by_bucket: dict[tuple, Entity] = {}
        for key, members in buckets.items():
            ent = self._make_entity(members)
            by_bucket[key] = ent
            entities.append(ent)

        for m in mentions:
            ent = by_bucket[_blocking_key(m)]
            resolved.append(ResolvedMention(m, ent))

        return entities, resolved

    def _make_entity(self, members: list[Mention]) -> Entity:
        """동치류 멤버 → canonical Entity (결정적 대표명·ID)."""
        # entity_id는 공유 식별자(있으면) 아니면 대표 표면형으로 결정.
        ids: dict = {}
        for m in members:
            ids.update(m.identifiers)
        # canonical 대표명: 최빈 표면형, 동률 사전순 (결정적).
        surfaces = [m.surface_text for m in members]
        counts = Counter(surfaces)
        best = min(
            {s: -c for s, c in counts.items()}.items(),
            key=lambda kv: (kv[1], kv[0]),
        )[0]
        mention_type = members[0].mention_type
        eid = entity_id_for(mention_type, best, ids)
        return Entity(
            entity_id=eid,
            mention_type=mention_type,
            canonical_name=best,
            identifiers=ids,
            surface_forms=tuple(sorted(set(surfaces))),
        )
