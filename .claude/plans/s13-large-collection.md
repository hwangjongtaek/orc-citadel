# S13 대형 수집 러너 — resumable·idempotent·polite (1만 문서 기반)

> 권장안 3 선택. 소량 수집(6건)을 대형 resumable 수집 러너로 확장해 1만 문서 확보의
> 기반을 마련한다. 대상: [04-ingestion-and-parsing](../../docs/design/04-ingestion-and-parsing.md) §1.3·§1.4,
> 03 §2.1(content-hash doc_id), 11 §5.4(allow_redistribute=false).

## 배경·범위

| 결정 | 근거 |
| --- | --- |
| **`collect_large.py` — resumable·idempotent·polite 러너** | arXiv 페이징(유일 대량 소스) 주축 + RSS. content-hash doc_id로 재개 무중복(03 §2.1) |
| **arXiv 1 req/3s politeness** | 04 §1.3 — 선언 UA + 간격 |
| **`--limit`으로 배치 제어** | 데모는 작게, 전체 1만은 사용자 실행 |
| **이 세션은 러너 구축 + 유효성 실증, 전체 1만은 인계** | 진짜 1만은 arXiv 1 req/3s로 수 시간 소요 (예의·시간 예산) |

## 실제 실행 통찰 (라이브 데모)

- 데모 실행으로 **98건 raw 문서** 확보: arXiv 65·NVIDIA 20·SemiEngineering 13 (기존 6→98).
- **버그 발견/수정**: `ArxivConnector.discover`가 페이지당 최대 100을 요청해 `--limit`를
  무시하고 과다 수집 → `collect_arxiv`가 총 budget(total)에서 정지하도록 캡 강제
  (TDD `test_collect_arxiv_caps_at_limit`로 재현·방지).

## DoD

- 러너 코드 + 테스트 (batch 계획·저장 멱등성·limit 캡)
- 유효성 실증 (라이브 소량 러닝 → 98건 저장 확인)
- 전체 테스트 통과, code-only 커밋
- (1만 전체 실행은 사용자: `python -m orc_citadel.collect_large --limit 10000`)

## 한계 (문서화)

- SEC(gov)는 robots·인증 정교화 후 별도 커넥터 (이번 러너 제외 — 04 §1.4)
- RSS는 피드 길이 유한 — 대량은 arXiv 페이징 주축
- 엄밀한 robots.txt 파싱·backoff 재시도는 소량 실수집에서 커넥터별 확장 (04 §1.2)
