# Subagent 설계 계획 — Orc Citadel

## 목표
프로젝트 성격(설계 중심 Phase 0, TDD/Tidy First 강제 AGENTS.md, 오크 세계관, 한국어 문서 문화)에 맞춰 `.claude/agents/*.md` 정의 파일로 실행 가능한 subagent 조직도를 만든다.

## 산출물
`.claude/agents/` 아래 정의 파일 생성 (각 1개). 참조용으로 함께 설계한다.

## 만들 subagent 후보 (초점: 코드+문서 종합)

### 엔지니어링 파이프라인
1. **implementation-engineer** — TDD 사이클(Red→Green→Refactor), AGENTS.md 원칙을 준수하는 코드 작성 subagent. Tidy First(구조/행동 변경 분리) 강제.
2. **code-reviewer** — 역량 검증 리뷰어. 설계 불변식(7개)·정확성·효율성·보안 관점에서 병렬 후보/거짓 검증.
3. **test-writer** — 골든 데이터셋·회귀 테스트·평가 지표(design 10)에 맞는 테스트 작성.
4. **pipeline-architect** — 설계 SSOT(01–08)를 구현 계약으로 바꾸는 아키텍처 subagent. 스키마·계약·불변식 정합.

### 설계·문서 관리
5. **docs-maintainer** — ROADMAP·Changelog·ADR·문서 상태 전이(Draft/Review/Stable) 관리.
6. **consistency-auditor** — 12개 SSOT 문서 간 상호참조·불변식·ID/버전 체계 일관성 검증.
7. **design-reviewer** — 설계 문서 리뷰 (blueprint 충실도·구현가능성).

### 도메인·데이터
8. **domain-researcher** — 소스 선정(Q1·Q2·Q3)·라이선스 검토(design 11)·1만 문서 샘플 확보 조사 (도메인: AI 반도체·데이터센터 공급망).

### UI·세계관
9. **mockup-designer** — 목업(8 화면)·DESIGN.md 토큰·캐릭터/자산(PixelLab) 관리.
10. (선택) **orc-lore-keeper** — 세계관 용어 ↔ 기술 용어 병기 사전, 신규 용어 제안.

## 설계 원칙
- 각 subagent 마다: role(역할), 사용 시점, 담당 scope(담당 design 문서), 도구(MCP), 행동 규칙(AGENTS.md 준수), 성공 기준.
- **역할 분리는 서로 겹치지 않게**: implementation ↔ review ↔ test 분리(자기 코드 검증 방지), docs ↔ consistency 분리(작성자/감사자 분리).
- **TDD 강제**: implementation-engineer가 AGENTS.md의 TDD 원칙을 명시적으로 하위 작업 지시로 포함.
- **한국어+영문 병기** 문화 유지, 세계관 명칭/기술 용어 규칙([README] §2.1) 준수.
- 코드는 아직 없음 → implementation-engineer는 "Phase 0 prototype(provenance·bitemporal)"부터 시작할 준비.

## 승인 후 작업 순서
1. `.claude/agents/` 디렉터리 생성
2. subagent 정의 파일 순서대로 작성 (9~10개)
3. 각 파일의 frontmatter(name/description/tools/model) + 본문(role/scope/규칙/성공기준)
4. 최종 검토 (누락·중복·도구 참조 확인)
