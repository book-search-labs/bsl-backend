# B-0251 — Feature Spec Single Source: features.yaml (Online/Offline parity)

## Goal
LTR/Ricing is the core of success** Create a single source (features.yaml)**,
- online feature fetcher
- offline dataset builder
About Us ** Forces to write the same definition/translation**.

## Background
- LTR 1: Online/offline Defence
- “The correct document, implementation is separated” if 100% broken.
- Thus, parsing YAML/JSON spec to generate common conversion.

## Scope
### 1) features.yaml spec (e.g. form)
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
- (Title)   TBD   Module (Language)
  - python: offline builder + MIS/RS
  - java: SR debug/explain
- Specching → runtime transform application
- “Specification request” fails (or strict mode)

### 3) Validation
- About Us News
  - lint lint
  - Check the Reservation·Cancel
  - Sample input

### 4) Rollout plan
- feature set version with model registry
- The model has "learned with any feature set", and only use the same version when serving.

## Non-goals
- Model Learning Pipeline Self(B-0294)
- point-in-time correctness(B-0293)

## DoD
- feature.yaml draft(v1) (minimum 10 pitcher)
- Implementation of a statement/deletion + CI connection
- application of default/transform based on the spec
- offline builder is based on the same spec.

## Observability
- include spec version tag metrics/logs:
  - rerank_requests_total{spec_version}
  - feature_missing_total{spec_version,feature}

## Codex Prompt
Create feature spec system:
- Define features.yaml schema and implement parser/validator.
- Add CI checks (lint + snapshot).
- Update online feature fetch layer to apply defaults/transforms from spec.
- Provide offline builder stub that uses the same spec for transforms.
