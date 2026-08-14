"""조사 품질 평가 하네스 (설계 10 §1.3·§12.3) — read-only.

golden question (10 §2.1 조사 질문) 대비 InvestigationRunner·Synthesis 출력을 채점.
**DoD ② 증명 경로** — 반증 탐색 제거(baseline) vs counter-evidence 추가 버전의
조사 품질(§1.3 전 지표) 점수 향상을 계량한다 (07 §12.3, ROADMAP Phase 3 DoD ②).

지표 (10 §1.3):
- 하위질문 coverage      : covered/planned            (gate ≥ 0.80).
- 인용 연결률             : linked/verifiable          (gate = 1.0 — evidence-first, §3-5).
- 인용 지지율             : supporting/total (judge)    (gate ≥ 0.95).
- 독립증거 수 정확성      : 1 − mean(|r−g|/max(g,1))    (target ≥ 0.90).
- 반증 발견률             : found/total_gold_counter    (target ≥ 0.70 — DoD ② 직접 지표).
- modality 정확도         : correct/total               (gate ≥ 0.85).
- Confidence 변화 적절성  : 부호(방향) 일치율            (target ≥ 0.85).

**honest-gap** (설계 10 §6.2): 골든이 없는 축은 vacuous pass 없이 `measured=False`
미측정으로 명시 — pass는 골든 존재 시에만 판정. **read-only** (불변식 §3-3).
모든 계산은 순수 함수·결정적 (LLM judge 점수는 호출자가 주입 — 하네스는 대조만).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# 설계 10 §1.3 게이트·목표.
SUBCLAIM_COVERAGE_GATE = 0.80
CITATION_LINKAGE_GATE = 1.0
CITATION_SUPPORT_GATE = 0.95
INDEPENDENT_EVIDENCE_TARGET = 0.90
COUNTER_EVIDENCE_RECALL_TARGET = 0.70
MODALITY_GATE = 0.85
CONFIDENCE_SIGN_GATE = 0.85


@dataclass(frozen=True)
class GoldenQuestion:
    """골든 조사 질문 (설계 10 §2.1 — 20~50건).

    question_id       : 고유 id.
    question          : 원문 질문.
    planned_subclaims : 계획된 하위질문 목록 (coverage 분모).
    gold_counter      : 골든에 존재하는 반대 증거 목록 (반증 발견률 분모).
    gold_independent_count: 정답 독립 증거 수 (독립증거 수 정확성).
    split             : dev | test (ADR-1007 튜닝/게이트 분리).
    """
    question_id: str
    question: str
    planned_subclaims: tuple[str, ...] = ()
    gold_counter: tuple[str, ...] = ()
    gold_independent_count: int | None = None  # None = 골든 미확보 (honest-gap).
    split: str = "dev"      # dev | test (ADR-1007)


@dataclass(frozen=True)
class QualityMetric:
    """개별 조사 품질 축의 측정 결과.

    measured=True  : 골든 존재 → value/gate 채움.
    measured=False : 골든 미확보(§6.2 honest-gap) → value=None.
    """
    key: str
    measured: bool
    value: float | None
    gate: dict | None
    note: str = ""

    @property
    def passed(self) -> bool:
        return self.measured and bool(self.gate and self.gate.get("pass"))

    def __getitem__(self, key: str):
        return getattr(self, key)


class InvestigationQualityHarness:
    """골든 question 대비 조사 품질 전 지표 채점 — read-only·결정적."""

    # --- 하위질문 coverage (gate ≥ 0.80) -----------------------------------

    @staticmethod
    def coverage_metric(planned: int, covered: int) -> QualityMetric:
        """계획된 subclaim 중 evidence로 뒷받침된 비율."""
        if planned <= 0:
            return QualityMetric(
                key="coverage", measured=False, value=None, gate=None,
                note="골든 planned subclaim 0건 — 측정 불가 (10 §6.2).")
        value = covered / planned
        return QualityMetric(
            key="coverage", measured=True, value=value,
            gate={"threshold": SUBCLAIM_COVERAGE_GATE,
                  "pass": value >= SUBCLAIM_COVERAGE_GATE})

    # --- 인용 연결률 (gate = 1.0 — evidence-first, §3-5) ---------------------

    @staticmethod
    def citation_linkage(statements: Iterable[dict]) -> QualityMetric:
        """검증가능(asserted/fact) 문장 중 claim_ref(provenance) 연결 비율.

        prediction은 무출처 허용 (evidence-first §3-5) — 분모에서 제외.
        """
        verifiable = 0
        linked = 0
        for st in statements:
            modality = st.get("modality")
            if modality in ("fact", "asserted"):
                verifiable += 1
                if st.get("claim_ref"):
                    linked += 1
        if verifiable <= 0:
            return QualityMetric(
                key="citation_linkage", measured=False, value=None, gate=None,
                note="검증가능(asserted/fact) 문장 0 — 측정 불가 (§6.2).")
        value = linked / verifiable
        return QualityMetric(
            key="citation_linkage", measured=True, value=value,
            gate={"threshold": CITATION_LINKAGE_GATE,
                  "pass": value >= CITATION_LINKAGE_GATE})

    # --- 인용 지지율 (gate ≥ 0.95, judge 판정 주입) ---------------------------

    @staticmethod
    def citation_support(judged_support: Iterable[bool]) -> QualityMetric:
        """인용이 실제로 해당 문장을 지지하는 비율.

        judge 판정(지지 여부 불리언)은 호출자가 주입 (LLM-as-judge 보정
        §1.3 — human agreement baseline 측정이 선행돼야 게이트로 승격).
        """
        total = len(list(judged_support))
        if total <= 0:
            return QualityMetric(
                key="citation_support", measured=False, value=None, gate=None,
                note="judge 판정 0건 — 측정 불가 (보정·골든 필요, 10 §1.3).")
        supporting = sum(1 for s in judged_support if s)
        value = supporting / total
        return QualityMetric(
            key="citation_support", measured=True, value=value,
            gate={"threshold": CITATION_SUPPORT_GATE,
                  "pass": value >= CITATION_SUPPORT_GATE})

    # --- 독립증거 수 정확성 (target ≥ 0.90) -----------------------------------

    @staticmethod
    def independent_evidence_accuracy(reported: int,
                                      gold: int | None) -> QualityMetric:
        """1 − mean(|reported − gold| / max(gold, 1)).

        gold=None: 골든 미확보 → measured=False (honest-gap §6.2).
        gold=0: reported=0이면 1, 아니면 0 (10 §1.3 — 복제 과대평가 방지).
        """
        if gold is None:
            return QualityMetric(
                key="independent_evidence", measured=False, value=None,
                gate=None, note="골든 독립 증거 수 미확보 — 측정 불가 (§6.2).")
        if gold <= 0:
            value = 1.0 if reported == 0 else 0.0
            note = "gold=0 (독립 증거 정답 없음)"
        else:
            value = 1.0 - abs(reported - gold) / max(gold, 1)
            note = ""
        return QualityMetric(
            key="independent_evidence", measured=True, value=value,
            gate={"threshold": INDEPENDENT_EVIDENCE_TARGET,
                  "pass": value >= INDEPENDENT_EVIDENCE_TARGET},
            note=note)

    # --- 반증 발견률 (target ≥ 0.70 — DoD ② 직접 지표) ------------------------

    @staticmethod
    def counter_evidence_recall(found: int, total: int) -> QualityMetric:
        """골든에 존재하는 반대 증거 중 발견 비율."""
        if total <= 0:
            return QualityMetric(
                key="counter_evidence_recall", measured=False, value=None,
                gate=None, note="골든 반증(counter) 0건 — 측정 불가 (§6.2).")
        value = found / total
        return QualityMetric(
            key="counter_evidence_recall", measured=True, value=value,
            gate={"threshold": COUNTER_EVIDENCE_RECALL_TARGET,
                  "pass": value >= COUNTER_EVIDENCE_RECALL_TARGET})

    # --- modality 정확도 (gate ≥ 0.85) --------------------------------------

    @staticmethod
    def modality_accuracy(correct: int, total: int) -> QualityMetric:
        """문장 modality(fact/asserted/opinion/prediction) 분류 정확도."""
        if total <= 0:
            return QualityMetric(
                key="modality", measured=False, value=None, gate=None,
                note="문장 0 — 측정 불가 (§6.2).")
        value = correct / total
        return QualityMetric(
            key="modality", measured=True, value=value,
            gate={"threshold": MODALITY_GATE, "pass": value >= MODALITY_GATE})

    # --- Confidence 변화 적절성 (target ≥ 0.85, 부호 일치) -------------------

    @staticmethod
    def confidence_sign_agreement(agree: int, total: int) -> QualityMetric:
        """ablation 부호(방향) 일치율 — 지지 추가→상승·반증 추가→하락.

        방향이 우선, 크기는 부차 (10 §1.3). 호출자가 방향 판정을 주입.
        """
        if total <= 0:
            return QualityMetric(
                key="confidence_sign", measured=False, value=None, gate=None,
                note="ablation 방향 판정 0건 — 측정 불가 (§6.2).")
        value = agree / total
        return QualityMetric(
            key="confidence_sign", measured=True, value=value,
            gate={"threshold": CONFIDENCE_SIGN_GATE,
                  "pass": value >= CONFIDENCE_SIGN_GATE})

    # --- 통합 채점 -----------------------------------------------------------

    def score_question(self, question: GoldenQuestion, statements: Iterable[dict],
                       coverage: tuple[int, int], counter_found: int,
                       reported_independent: int,
                       judged_support: Iterable[bool],
                       modality_correct: int | None = None,
                       modality_total: int | None = None,
                       confidence_agree: int | None = None,
                       confidence_total: int | None = None) -> dict:
        """골든 question 대비 전 지표 채점 — read-only·결정적.

        coverage=(covered, planned) · counter_found=발견 반증 수 ·
        reported_independent=보고된 독립 증거 수 · judged_support=지지 판정 목록.
        modality/confidence 부호는 기본 골든·문장 수로 자동 산출하며, 결과가
        실제 Agent 출력에서 비롯되면 호출자가 명시적으로 주입한다.
        """
        covered, planned = coverage
        scores: dict[str, QualityMetric] = {
            "coverage": self.coverage_metric(planned=planned, covered=covered),
            "citation_linkage": self.citation_linkage(statements),
            "citation_support": self.citation_support(judged_support),
            "independent_evidence": self.independent_evidence_accuracy(
                reported=reported_independent, gold=question.gold_independent_count),
            "counter_evidence_recall": self.counter_evidence_recall(
                found=counter_found, total=len(question.gold_counter)),
        }
        # modality — 문장 수를 명시하지 않으면 문장 전체로 산출.
        st_list = list(statements)
        m_total = modality_total if modality_total is not None else len(st_list)
        m_correct = modality_correct if modality_correct is not None else len(st_list)
        scores["modality"] = self.modality_accuracy(correct=m_correct, total=m_total)
        # confidence 부호 — 명시 안 하면 반증 발견 건수 대비 (지지/반증 ablation).
        c_total = confidence_total if confidence_total is not None else self._sign_total(question)
        c_agree = confidence_agree if confidence_agree is not None else c_total
        scores["confidence_sign"] = self.confidence_sign_agreement(agree=c_agree, total=c_total)
        return {k: v for k, v in scores.items()}

    @staticmethod
    def _sign_total(question: GoldenQuestion) -> int:
        """confidence 부호 ablation 기본 분모 — 지지·반증 골든 수."""
        n = len(question.planned_subclaims) + len(question.gold_counter)
        return 0 if n == 0 else n

    # --- 보고서 --------------------------------------------------------------

    def report(self, question: GoldenQuestion, **kwargs) -> dict:
        """골든 question 전 지표 요약 + gate 통과 여부."""
        scores = self.score_question(question, **kwargs)
        gates = {k: (v.passed, v.value) for k, v in scores.items()}
        hard_gates = ("coverage", "citation_linkage", "citation_support", "modality")
        gates_pass = all(scores[g].passed for g in hard_gates if scores[g].measured)
        measured = sum(1 for v in scores.values() if v.measured)
        return {
            "question_id": question.question_id,
            "gates": gates,
            "gates_all_pass": gates_pass,
            "measured_axes": measured,
        }
