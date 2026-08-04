# 대량 파이프라인 E2E 스모크 (100건, S5→S12)

> 권장안 1 선택. 현재 수집된 전체 raw 문서(arXiv 65 포함 100건)를 결정적 파이프라인
> S5→S12 전 체인으로 흘려, 대량 스케일 견고성을 검증한다.
> 대상: 기존 정규화/추출/해소/claim/게이트/canonicalize/contradiction/assertion/authoritative.

## 결과 (100건)

- 파싱: **100/100 OK** (arXiv HTML도 extract_html 견고), empty 0
- mentions 523 → **전부 authoritative 승격** (mention 게이트)
- claims 29 → 전부 promoted → **29 assertions** materialized
- canonical claims 7 (29 members 병합)
- conflict 0 (arXiv 논문 동일 event 계열 — 상충 부재, 정직)
- 결정성 불변식 유지

## 발견·수정한 견고성 버그

- **`assertions.tx_from` NOT NULL 위반**: publication_time이 없는 문서(arXiv 일부)에서
  `observed_at=None` → 스모크에서 관측시각 폴백(또는 head time)으로 해결.

## DoD

- 전 체인 대량 스케일 동작 확인, 결정성·멱등성 유지
- 전체 테스트 통과(133), code-only 커밋
