"""TDD Red stage — failing tests for Phase 0 DoD.

DoD ① 원문 offset → segment → claim → 원문 왕복 추적
DoD ② 동일 문서 재처리 시 중복 mutation 없음
(부가) immutable raw — 동일 URL 변경분은 새 doc_id로 보존
"""
