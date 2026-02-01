# B-0320 — MIS Real Spell Model (T5/ONNX) Enablement + Runtime Wiring + Smoke Test

## Goal
- MIS의 `/v1/spell`이 **toy가 아니라 실제 T5 기반 ONNX**로 교정 결과를 반환하도록 한다.
- QS에서 `QS_SPELL_PROVIDER=http` + enhance 전략(SPELL_ONLY / SPELL_THEN_REWRITE)에서 **실제 교정 문자열이 반영**되도록 한다.
- dev/stage에서 **fail-closed(artifact 없으면 503)**로 운영 실수(몰래 toy fallback)를 방지한다.

## Background / Problem
- 현재 기본값:
  - `MIS_SPELL_BACKEND=toy`
  - `MIS_SPELL_FALLBACK=toy`
- ONNX 아티팩트(onnx/tokenizer)가 없거나 경로/마운트가 잘못되면 **조용히 toy로 fallback**되어 “T5가 안 되는 것처럼” 보인다.
- 코드 경로(B-0316~B-0319)는 준비되었으나, **실제 모델 아티팩트 배포/마운트/검증 루프**가 없다.

## Scope
### In scope
1) **Model artifacts 준비/배치 방식 확정**
- (선택 A) repo 외부(로컬/서버) `./models/spell/t5-typo-ko-v1/`에 아티팩트 보관
- (선택 B) 내부 artifact store/S3/registry에서 받아오는 스크립트 제공(추후 I-ticket로 분리 가능)
- 최소 구성:
  - `spell.onnx`
  - `tokenizer.json` (또는 tokenizer artifacts set)
  - (필요 시) vocab/merges/special_tokens_map 등

2) **docker-compose(또는 실행 스크립트)에서 MIS에 모델 마운트**
- host path → container path를 **명확히 고정**
- 예: host `./models/spell/t5-typo-ko-v1/` → container `/models/spell/t5-typo-ko-v1/`

3) **dev/stage에서 fail-closed**
- `MIS_SPELL_FALLBACK=error` 기본 적용(또는 stage만)
- 모델 로드 실패/파일 누락 시 `/v1/spell`은 503을 반환해야 함

4) **Smoke test / verification**
- MIS 직접 호출로 교정 확인
- QS enhance 경유로 교정 반영 확인
- (가능하면) `scripts/eval/spell_eval.py --mode mis` 최소 샘플 실행 가능하도록 문서화

### Out of scope
- spell 품질 튜닝(데이터셋 확장, guardrail threshold 최적화)
- 새로운 모델 학습/파인튜닝
- 대규모 A/B 실험/온라인 평가

## Implementation Notes
### Required env (MIS)
- `MIS_SPELL_ENABLE=true`
- `MIS_SPELL_BACKEND=onnx`
- `MIS_SPELL_MODEL_ID=t5-typo-ko-v1`
- `MIS_SPELL_MODEL_PATH=/models/spell/t5-typo-ko-v1/spell.onnx`
- `MIS_SPELL_TOKENIZER_PATH=/models/spell/t5-typo-ko-v1/tokenizer.json`
- `MIS_SPELL_FALLBACK=error`  (dev/stage 권장. prod는 정책에 따라 toy/error 선택)

### Required env (QS)
- `QS_SPELL_PROVIDER=http`
- `QS_SPELL_URL=http://model-inference-service:<port>`
- `QS_SPELL_PATH=/v1/spell`
- `QS_SPELL_MODEL=t5-typo-ko-v1`
- (참고) enhance가 spell을 타려면 reason/전략이 SPELL_ONLY 또는 SPELL_THEN_REWRITE로 선택되어야 함

## Tasks
1) `models/` 경로 규약 문서화
- README 또는 docs에 “host↔container 경로”와 파일명 규약 명시

2) docker-compose wiring 추가/수정
- MIS service에 volumes 추가
- MIS env 추가 (onnx backend + paths + fallback policy)

3) Fail-closed 동작 검증
- 아티팩트 없을 때 `/v1/spell` → 503 확인
- 아티팩트 있을 때 `/v1/spell` → 200 + corrected 변경 확인

4) Smoke test 스크립트/커맨드 정리
- MIS 단독:
  - `curl -X POST ... /v1/spell` (오타 입력) → corrected 확인
- QS 경유:
  - `/query/enhance` payload로 reason=HIGH_OOV 또는 ZERO_RESULTS 등으로 spell 전략 유도
  - response에 spell.corrected가 원문과 다르게 나오는지 확인

5) (옵션) 최소한의 “운영 실수 방지” 로깅
- MIS 시작 시 spell backend/model_id/path/fallback을 INFO로 남김
- 모델 로드 실패 시 명확한 에러 로그

## DoD (Definition of Done)
- [ ] dev 환경에서 `MIS_SPELL_BACKEND=onnx` 설정 시 `/v1/spell`이 **toy가 아닌 실제 교정 결과**를 반환한다.
- [ ] dev 환경에서 아티팩트가 없거나 경로가 틀리면 `/v1/spell`이 **503**을 반환한다 (`MIS_SPELL_FALLBACK=error`).
- [ ] QS에서 `QS_SPELL_PROVIDER=http` + enhance 경유 시 교정 결과가 응답에 반영된다.
- [ ] 문서에 “아티팩트 위치/마운트/검증 커맨드”가 포함된다.

## Verification Checklist
- [ ] `GET /health` (MIS/QS) OK
- [ ] `POST /v1/spell` with typo → corrected != input
- [ ] (negative) artifact missing → 503
- [ ] `POST /query/enhance` → debug/spell.corrected 확인

## Rollback
- `MIS_SPELL_BACKEND=toy`로 되돌리거나
- `MIS_SPELL_FALLBACK=toy`로 fail-open 전환(필요 시)
- QS는 `QS_SPELL_PROVIDER=off`로 즉시 no-op 처리 가능
