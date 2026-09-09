"""LLM 조사 종합 (W2 — on-request·read-only, 07 §9.3 evidence-first 유지).

결정적 Synthesizer 의 템플릿 문장을 LLM 생성 문장으로 대체하는 **표현 계층**
확장. 근거 계층은 그대로다 — LLM 에게는 subject 의 assertions 승격 claim rows
만 제공되고, 문장의 claim_ref 는 그 화이트리스트로 강제된다:

- 목록 밖 claim_ref·무출처 asserted·허용 외 modality·빈 텍스트 → 폐기
  (discarded 카운트) — 지어낸 근거가 응답에 실리지 않는다 (ADR-703 방향).
- prediction/opinion 은 무출처 허용(07 §9.3)하되 claim_ref 는 제거한다.
- 호출측(viewer)은 Audit.trace(§3.9)를 최종 문장에 재적용해 역추적 미통과
  문장을 추가 차단한다.
- LLM 오류·미설정·비스키마는 예외 전파 없이 None/빈 산출 — 결정적 경로 폴백
  (§6.2 정직 표기는 호출측 llm.error 몫).

**read-only** (§3-3): 조회·생성만, 영속 없음. 결정성 예외는 mode=llm 옵트인에
한정 — 기본 경로는 여전히 결정적이다.
"""

from __future__ import annotations

import json
import os

from orc_citadel.llm_providers import build_llm_client

# 근거 상한 — 토큰 예산 보호 (근거는 결정적 순서라 상한도 결정적).
MAX_EVIDENCE = 20

_SYSTEM = (
    "너는 Orc Citadel 조사 종합기다. 제공된 근거(claims) 목록만으로 한국어 "
    "보고서 문장을 만든다. 목록에 없는 사실·수치·날짜를 지어내지 마라. "
    '출력은 JSON 하나: {"statements": [{"text": "...", '
    '"modality": "asserted|prediction", "claim_ref": "..."}]}. '
    "asserted 문장은 claim_ref 필수 — 반드시 근거 목록의 claim_id 중 하나. "
    "prediction 은 근거 종합에서 나오는 전망일 때만, claim_ref 없이 허용. "
    "문장은 3~6개, 간결한 브리핑 톤."
)

_ALLOWED_MODALITIES = ("asserted", "prediction", "opinion")

# 기본 client 는 lazy 1회 생성 — 요청마다 httpx client 를 만들지 않는다.
_default_client: object | None = None
_default_built = False


def default_client():
    global _default_client, _default_built
    if not _default_built:
        _default_client = build_llm_client()
        _default_built = True
    return _default_client


def evidence_rows(zone, subject_id: str, cap: int = MAX_EVIDENCE) -> list[dict]:
    """subject 의 근거 rows — assertions 승격 claim 만, 결정적 순서·상한.

    evidence-first: assertions 가 SoT — 승격되지 않은 claim 은 근거로 주지
    않는다. claim_id 오름차순 정렬로 동일 zone → 동일 프롬프트.
    """
    ids = sorted({a["claim_id"] for a in zone.assertions()
                  if a["subject_id"] == subject_id})
    by_id = {c["claim_candidate_id"]: c for c in zone.claims()}
    out = []
    for cid in ids[:cap]:
        c = by_id.get(cid)
        if c is None:
            continue
        out.append({
            "claim_id": cid,
            "predicate": c["predicate"],
            "object": c.get("object_literal") or c.get("object_id"),
            "surface": (c.get("surface_fragment") or "")[:200],
        })
    return out


class LlmSynthesis:
    """근거 화이트리스트 강제 LLM 문장 생성 — client 주입 가능 (테스트 격리)."""

    def __init__(self, client=None) -> None:
        # None = env 기본 client. False 등 falsy 주입은 '없음' 그대로 둔다.
        self._client = default_client() if client is None else (client or None)

    def available(self) -> bool:
        return self._client is not None

    def synthesize(self, subject_label: str, question: str,
                   evidence: list[dict]) -> dict | None:
        """LLM 문장 생성 — 실패는 None, 비스키마는 빈 statements (지어내기 금지).

        반환: {statements, discarded, model, provider, usage}.
        """
        if self._client is None or not evidence:
            return None
        user = json.dumps({"subject": subject_label, "question": question,
                           "claims": evidence}, ensure_ascii=False)
        # reasoning 모델은 reasoning 토큰을 completion 예산에서 소비한다 (A30
        # 실측 — 2048 은 20건 근거에서 본문 잘림 경계선). 기본 8192.
        max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "8192") or 8192)
        try:
            data = self._client.messages_create(
                model=None, system=_SYSTEM, user=user,
                max_tokens=max_tokens, temperature=0)
        except Exception:  # noqa: BLE001 — 프로바이더 오류는 폴백 신호일 뿐.
            return None
        raw = data.get("statements") if isinstance(data, dict) else None
        valid_ids = {e["claim_id"] for e in evidence}
        statements, discarded = [], 0
        for st in raw if isinstance(raw, list) else []:
            text = st.get("text") if isinstance(st, dict) else None
            modality = st.get("modality") if isinstance(st, dict) else None
            if (not isinstance(text, str) or not text.strip()
                    or modality not in _ALLOWED_MODALITIES):
                discarded += 1
                continue
            ref = st.get("claim_ref")
            if modality == "asserted":
                if ref not in valid_ids:
                    discarded += 1
                    continue
            else:
                ref = None  # 무출처 전망 — 목록 밖 ref 가 흘러들지 않게 제거.
            statements.append({"text": text.strip(), "modality": modality,
                               "claim_ref": ref})
        return {
            "statements": statements,
            "discarded": discarded,
            "model": getattr(self._client, "model", None),
            "provider": getattr(self._client, "provider", None),
            "usage": dict(getattr(self._client, "last_usage", {}) or {}),
        }
