"""Investigation Planner (설계 07 §3.2) — read-only·결정적.

질문의 범위·시간대를 해석하고, 답변에 필요한 하위 주장과 증거 유형을 정의하며,
그래프의 기존 지식과 공백(gap)을 구분한다 (07 §3.1 비목표 — 사전 지식으로 사실
추가 금지, 그래프에 없는 것만 gap으로 남김).

- 입력 : {question, scope: {region?, source_types?, depth?}} (07 §3.2 표).
- 출력 : {subclaims: [{id, text, required_evidence_types[], known, gap_reason?}],
          plan: {tool_calls[]}} (07 §3.2 strict JSON).
- subclaim마다 `known`/`gap` 라벨 필수 (불변식) — 질문에 등장한 subject가 zone
  assertion에 있으면 known(기존 지식), 없으면 gap.
- 도구 : `graph:read`(기존 subgraph 존재 여부 확인) — read-only.
- 결정적 : subject·predicate 분해와 known/gap 판정 모두 결정적 규칙.

**read-only** (불변식 §3-3): 분해·조회만, 영속·graph mutation 미노출.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from orc_citadel.investigation import Subclaim


@dataclass(frozen=True)
class PlannedSubclaim:
    """07 §3.2 subclaim 원소 — known/gap 라벨 필수."""
    id: str
    text: str
    required_evidence_types: list
    known: bool
    subject_id: str | None = None
    gap_reason: str | None = None


@dataclass(frozen=True)
class Plan:
    """07 §3.2 플랜 출력 — subclaim 트리 + tool_calls 계획."""
    subclaims: list
    tool_calls: list


class InvestigationPlanner:
    """질문 → subclaim 트리 분해 + 기존 지식/공백 구분 (07 §3.2, read-only)."""

    # 결정적 질문 템플릿 — subject·predicate 분해 후 보강 (07 §3.2).
    _EVIDENCE_TYPES = ("claim", "evidence", "provenance")

    def __init__(self, zone) -> None:
        self._zone = zone

    def _subjects_in_knowledge(self) -> set[str]:
        """zone assertions에 존재하는 subject → 알려진 지식 (read-only 조회)."""
        return {a["subject_id"] for a in self._zone.assertions()}

    def _decompose(self, question: str) -> list[dict]:
        """질문 텍스트에서 subject·predicate 분해 — 결정적 규칙.

        텍스트에서 대문자 조직명(예: 'NVDA', 'INTEL')과 술어 키워드를 추출해
        subclaim 후보를 만든다. 구조화되지 않은 서술을 하위 주장으로 나눈다 (07 §3.2).
        """
        known_set = self._subjects_in_knowledge()
        # 질문이 곧 알려진 subject(예: org-id)면 그 자체를 대상으로 — 하위 주장은
        # 대문자 약어 subject를 분해하되, 질문 전체가 기존 지식 leaf면 known 유지.
        raw = (question or "").strip()
        subjects = re.findall(r"[A-Z]{2,}", raw) or ([raw] if raw in known_set else [])
        out = []
        for i, subj in enumerate(subjects or ["?subject"]):
            known = subj in known_set
            out.append({
                "subject": subj,
                "known": known,
                "gap_reason": None if known else "insufficient_evidence",
            })
        return out

    def plan(self, question: str, scope: dict | None = None) -> Plan:
        """질문 → subclaim 트리 + tool_calls 계획 (07 §3.2)."""
        parts = self._decompose(question)
        subclaims: list[PlannedSubclaim] = []
        tool_calls: list[dict] = []
        for i, p in enumerate(parts):
            sc_id = f"sc{i + 1}"
            subj = p["subject"]
            # 하위 주장 텍스트 — evidence-first 채점의 planned subclaim 기반.
            text = f"{subj} 는 {self._predicate(question)} 한다 (공급망 영향)"
            subclaims.append(PlannedSubclaim(
                id=sc_id, text=text,
                required_evidence_types=list(self._EVIDENCE_TYPES),
                known=p["known"], subject_id=subj, gap_reason=p["gap_reason"]))
            # 계획된 tool — 기존 지식 확인 graph:read, gap은 SEARCH 보강.
            if p["known"]:
                tool_calls.append({"tool": "graph:read",
                                   "args": {"subject": subj, "hops": 1}})
            else:
                tool_calls.append({"tool": "graph:read",
                                   "args": {"subject": subj, "hops": 1}})
        return Plan(subclaims=subclaims, tool_calls=tool_calls)

    @staticmethod
    def _predicate(question: str) -> str:
        """질문에서 술어 후보 추출 (결정적 fallback 포함)."""
        m = re.search(r"\b(announc\w*|invest|partn\w*|suppl\w*|contract\w*)\b",
                      question, re.IGNORECASE)
        return m.group(1) if m else "commits"
