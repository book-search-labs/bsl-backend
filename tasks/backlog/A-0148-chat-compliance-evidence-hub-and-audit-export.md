# A-0148 — Chat Compliance Evidence Hub + Audit Export

## Priority
- P2

## Dependencies
- A-0144, A-0147, B-0383, B-0386

## Goal
정책 준수/안전성/무결성 관련 증빙을 한곳에서 조회·내보내기 할 수 있는 운영 허브를 제공한다.

## Scope
### 1) Evidence aggregation
- 정책평가 trace, output guard 결과, signature 검증 로그 집계
- 기간/서비스/인텐트 기준 필터 제공

### 2) Audit export
- 감사용 리포트(PDF/CSV/JSON) 생성
- 내보내기 요청/다운로드 감사로그 기록

### 3) Compliance dashboard
- 위반 추세, 차단 추세, 예외 승인 추세 시각화
- 위험 임계치 초과 알림

### 4) Investigation shortcuts
- incident/replay/티켓으로 바로가기 링크
- 증빙 누락 탐지 경고

## DoD
- 감사 대응에 필요한 핵심 증빙을 1개 콘솔에서 확보
- export 이력의 추적 가능성 보장
- 준수 위반 추세를 운영자가 조기 인지 가능

## Codex Prompt
Build an evidence hub for chat compliance:
- Aggregate policy, safety, and integrity evidence in one admin console.
- Support auditable exports for compliance review.
- Highlight violation trends and missing-evidence risks with drill-down links.
