# B-0251 — Feature Spec Single Source: features.yaml (Online/Offline parity)

## Goal
LTR/리랭킹 성공의 핵심인 **피처 정의를 단일 소스(features.yaml)**로 만들고,
- online feature fetcher
- offline dataset builder
  가 **같은 정의/변환**을 쓰도록 강제한다.

## Background
- LTR이 망하는 1순위: online/offline 피처 불일치
- “정의는 문서, 구현은 따로”면 100% 깨진다.
- 따라서 YAML/JSON 스펙을 파싱해 공통 변환을 생성한다.

## Scope
### 1) features.yaml 스펙(예시 형태)
- feature_name
- type (float/int/bool/categorical)
- key_type: DOC | QUERY_DOC
- source: redis/mysql/opensearch/derived
- transform:
  - default
  - clip/min/max
  - log1p
  - bucketize (optional)
- versioning:
  - feature_set_version

### 2) Codegen / Shared lib
- (권장) `bsl-feature-spec` 모듈(언어별)
  - python: offline builder + MIS/RS
  - java: SR debug/explain(선택)
- 스펙 파싱 → runtime transform 적용
- “미정의 피처 요청”은 실패(혹은 strict mode)

### 3) Validation
- CI에서:
  - 스펙 lint
  - 중복/타입 불일치 체크
  - sample input에 대한 변환 결과 스냅샷 테스트

### 4) Rollout plan
- feature_set_version을 model_registry와 함께 기록
- 모델은 “어떤 feature set으로 학습했는지”를 갖고, 서빙 시 동일 version만 사용

## Non-goals
- 모델 학습 파이프라인 자체(B-0294)
- point-in-time correctness(B-0293) 구현 자체(하지만 설계는 반영)

## DoD
- features.yaml 초안(v1) 작성(최소 10개 피처)
- 파서/검증기 구현 + CI 연결
- online fetcher가 spec 기반으로 default/transform 적용
- offline builder가 동일 spec 기반으로 transform 적용(스켈레톤이라도)

## Observability
- spec_version tag를 metrics/logs에 포함:
  - rerank_requests_total{spec_version}
  - feature_missing_total{spec_version,feature}

## Codex Prompt
Create feature spec system:
- Define features.yaml schema and implement parser/validator.
- Add CI checks (lint + snapshot).
- Update online feature fetch layer to apply defaults/transforms from spec.
- Provide offline builder stub that uses the same spec for transforms.
