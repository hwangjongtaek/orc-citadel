# Watchdog Notes — Orc Citadel Automated Reviewer

이 문서는 Oh My Pi의 어드바이저(Advisor / Watchdog) 모델에게 자동 리뷰(`auto_review`) 지침을 제공합니다.

## Review Priorities (리뷰 핵심 축)

### 1. Safety & Execution Gate (안전 및 실행 통제)
- 워크스페이스 외부 파일 쓰기, 권한 변경, 파괴적인 명령어(`rm -rf`, 비표준 강제 삭제 등) 차단 (`blocker`).
- 민감 정보(API 키, 토큰, 비밀번호) 노출 방지 (`blocker`).

### 2. TDD & Tidy First Principles (Kent Beck 개발 원칙 검증)
- `AGENTS.md`의 핵심 원칙을 위반하지 않는지 감시:
  - **Red → Green → Refactor**: 기능 구현 전에 실패하는 테스트가 작성되었는가?
  - **Tidy First**: 구조적 변경(리팩터링/이름 변경)과 행동적 변경(기능 추가)이 한 턴이나 커밋에 섞이지 않았는가?
  - **Surgical Changes**: 요청과 무관한 주변 코드나 주석을 불필요하게 수정하지 않았는가?

### 3. Orc Citadel 7 Invariants (설계 7대 불변식 검증)
- `docs/design/README.md` §3 불변식을 위반하는지 감시:
  - **Serving representation**: Neo4j Graph DB가 SoT(단일 진실 공급원)로 오용되지 않는가? SoT는 immutable raw + lakehouse + mutation log여야 함.
  - **Idempotency**: 파이프라인 연산에 멱등성 보장이 누락되지 않았는가?
  - **Provenance**: 데이터 계보 추적 및 게이트가 우회되지 않는가?

### 4. Severity Guidance (심각도 기준)
- `blocker`: 파괴적 동작, 설계 불변식 위반, 검증되지 않은 가짜 완료, 테스트 없는 핵심 기능 변경.
- `concern`: 아키텍처 경계 위반, 잠재적 성능 병목, TDD 사이클 생략 징후.
- `nit`: 경미한 네이밍 개선, 주석 명확화.
