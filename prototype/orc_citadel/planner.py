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
    surface: str | None = None  # 질문에서 해소된 표면형 (entity name 해소 시)


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

    def _entity_index(self) -> list[tuple[str, str]]:
        """(표면형, entity_id) — canonical_name + surface_forms, 결정적 순서.

        긴 표면형 우선 매칭(부분 문자열 오탐 방지), 동률은 사전순. 1글자
        표면형은 오탐만 만들므로 제외.
        """
        pairs = []
        for e in self._zone.entities():
            names = [e.get("canonical_name")] + list(e.get("surface_forms") or [])
            for n in names:
                if n and len(n) >= 2:
                    pairs.append((n, e["entity_id"]))
        pairs.sort(key=lambda p: (-len(p[0]), p[0], p[1]))
        return pairs

    def _match_entities(self, question: str) -> list[dict]:
        """질문에 등장한 entity 표면형 → entity_id 결정적 해소.

        경계 규칙: 표면형 앞뒤가 영숫자가 아니어야 한다 — 'BN' 이 'RBNZ' 안에서
        오탐하지 않고, 한글 조사('엔비디아가')는 경계로 통과한다.
        """
        out, seen = [], set()
        for name, eid in self._entity_index():
            if eid in seen:
                continue
            pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(name)
                             + r"(?![A-Za-z0-9])", re.IGNORECASE)
            if pat.search(question):
                seen.add(eid)
                out.append({"surface": name, "entity_id": eid})
        return out

    def _decompose(self, question: str) -> list[dict]:
        """질문 텍스트에서 subject·predicate 분해 — 결정적 규칙.

        ① 질문의 표면형을 zone entities(canonical_name·surface_forms — 한글
        포함)로 해소해 실데이터 subject_id(org-해시)에 잇는다. ② 남은 대문자
        약어(예: 'NVDA', 'INTEL')는 기존 규칙 그대로 subclaim 후보 — 해소 안
        되면 gap 정직 표기 (07 §3.2, §3.1 비목표: 사전 지식 추가 금지).
        """
        known_set = self._subjects_in_knowledge()
        raw = (question or "").strip()
        out = []
        matched_surfaces: set[str] = set()
        for m in self._match_entities(raw):
            eid = m["entity_id"]
            matched_surfaces.add(m["surface"].upper())
            out.append({
                "subject": eid,
                "surface": m["surface"],
                "known": eid in known_set,
                "gap_reason": None if eid in known_set else "insufficient_evidence",
            })
        # 질문이 곧 알려진 subject(예: org-id)면 그 자체를 대상으로 — 하위 주장은
        # 대문자 약어 subject를 분해하되, 질문 전체가 기존 지식 leaf면 known 유지.
        subjects = re.findall(r"[A-Z]{2,}", raw) or ([raw] if raw in known_set else [])
        for subj in subjects:
            # name 해소로 이미 잡힌 표면형(또는 그 일부)은 중복 배제.
            if any(subj in s for s in matched_surfaces):
                continue
            if any(o["subject"] == subj for o in out):
                continue
            known = subj in known_set
            out.append({
                "subject": subj,
                "surface": subj,
                "known": known,
                "gap_reason": None if known else "insufficient_evidence",
            })
        if not out:
            out.append({"subject": "?subject", "surface": None, "known": False,
                        "gap_reason": "insufficient_evidence"})
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
            # 해소된 표면형이 있으면 그걸 쓴다 (org-해시보다 읽을 수 있게).
            text = (f"{p.get('surface') or subj} 는 "
                    f"{self._predicate(question)} 한다 (공급망 영향)")
            subclaims.append(PlannedSubclaim(
                id=sc_id, text=text,
                required_evidence_types=list(self._EVIDENCE_TYPES),
                known=p["known"], subject_id=subj, gap_reason=p["gap_reason"],
                surface=p.get("surface")))
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
