# B-0261 — QS Normalize/Detect 강화 (NFKC/ICU + 초성/권차/ISBN/시리즈 + canonicalKey)

## Goal
도서 도메인 입력을 운영형으로 안정화하는 **deterministic normalize/detect**를 강화한다.

- NFKC/ICU 기준 정규화
- 초성 검색/ISBN/권차/시리즈 패턴 감지
- canonicalKey(=중복 제거/머지/그룹핑의 기준 키) 생성
- SR/RS가 활용할 수 있는 신호(confidence/flags) 제공

## Background
- 도서 검색은 입력 흔들림이 매우 크다:
  - 붙여쓰기/띄어쓰기, 전각/반각, 권차 표기(01권/vol.1/Ⅰ)
  - 초성 입력(ㅎㄹㅍㅌ)
  - ISBN 하이픈/공백
- 여기서 흔들리면 downstream에서 품질/캐시/로그 집계가 모두 망가진다.

## Scope
### 1) Normalize rules (deterministic)
- Unicode:
  - NFKC 적용 (전각/반각/호환문자 정리)
- whitespace:
  - trim + collapse multi-spaces
- punctuation:
  - 의미없는 구분자는 공백 통일 (· _ - : 등)
  - 의미 있는 기호는 보존(C++, C# 등)
- casing:
  - 영문 lowercase
- numbers/volume:
  - "01권", "vol.1", "1편", "Ⅰ" → "1권"
  - 권차 토큰은 별도 추출(detected.volume)

### 2) Detect rules
- isbn:
  - 10/13자리, 하이픈 포함 패턴 감지
  - ISBN-10 check digit(X) 케이스 처리(선택)
- chosung:
  - 한글 자모/초성 비율로 mode=chosung
- mixed:
  - 한글+영문 혼용 감지
- series hints:
  - "시리즈", "세트", "완전판", "전권" 등 키워드
  - ":" 이후 부제 처리(선택)

### 3) canonicalKey generation (v1)
- 목표: 같은 의도의 입력은 같은 key로 모이게
- 제안:
  - base = normalize(q_norm) + (volume?) + (isbn?) + (mode)
  - canonicalKey = sha256(base) or normalized string
- 용도:
  - 캐시 키, 로그 집계 키, authority/merge 힌트

### 4) Test cases (must-have)
- 최소 30개 이상의 입력→출력 케이스 테이블을 fixtures로 고정
  - 초성, 권차, ISBN, 혼용, 전각, 특수문자
- regression 테스트로 CI에 포함

## Non-goals
- spell/LLM rewrite 2-pass (B-0262/0263)
- query cache (B-0264)

## DoD
- normalize/detect 규칙 구현 + fixtures 테스트 통과
- QueryContext v1에 detected/confidence/canonicalKey 채움
- edge 케이스(초성/권차/ISBN) 최소 30개 회귀 테스트 존재
- 성능: 1-pass p95 < 10~15ms 목표(로컬 기준)

## Observability
- metrics:
  - qs_detect_mode_total{mode}
  - qs_isbn_detect_total
  - qs_volume_detect_total
- logs:
  - request_id, canonicalKey, detected.mode, detected.volume?

## Codex Prompt
Implement QS normalize/detect:
- Add deterministic normalization pipeline (NFKC/whitespace/punct/case).
- Add detect for isbn/chosung/mixed and volume canonicalization.
- Generate canonicalKey and include in QueryContext v1.
- Create fixture-based regression tests (30+ cases) and wire into CI.
