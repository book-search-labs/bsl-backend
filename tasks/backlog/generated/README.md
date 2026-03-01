# Generated Backlog Artifacts

이 디렉터리는 운영 스크립트가 생성하는 backlog 산출물을 저장한다.

## Chat feedback loop outputs

- `chat_feedback_auto.md`
  - `evaluation/chat/feedback_backlog.json`를 사람이 빠르게 확인할 수 있는 요약 문서로 렌더링한 파일.
- `feedback/*.md`
  - 피드백 신호 항목별 자동 티켓 초안.
  - 생성 스크립트: `scripts/chat/sync_feedback_backlog_tickets.py`
  - 다음 실행에서 덮어쓰기/정리(prune)될 수 있으므로 수동 편집을 권장하지 않는다.
- `chat_feedback_regression_seeds.md`
  - 피드백 하락 이유(reason_code) 상위 항목을 회귀 시나리오 stub으로 변환한 초안.
  - 생성 스크립트: `scripts/chat/generate_feedback_regression_seeds.py`
  - 운영 실패 신호를 B-0623 회귀셋 편입 후보로 빠르게 큐레이션하기 위한 아티팩트.
- `chat_feedback_regression_fixture_candidates.md`
  - 회귀 시드 초안을 기존 fixture와 대조하여 신규 편입 후보만 추린 문서.
  - 생성 스크립트: `scripts/chat/build_regression_seed_fixture.py`
  - 본 fixture에 직접 반영 전, 리뷰/수정용 입력으로 사용한다.

## Refresh command

```bash
./scripts/chat/run_recommend_quality_loop.sh
```
