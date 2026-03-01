# Generated Backlog Artifacts

이 디렉터리는 운영 스크립트가 생성하는 backlog 산출물을 저장한다.

## Chat feedback loop outputs

- `chat_feedback_auto.md`
  - `evaluation/chat/feedback_backlog.json`를 사람이 빠르게 확인할 수 있는 요약 문서로 렌더링한 파일.
- `feedback/*.md`
  - 피드백 신호 항목별 자동 티켓 초안.
  - 생성 스크립트: `scripts/chat/sync_feedback_backlog_tickets.py`
  - 다음 실행에서 덮어쓰기/정리(prune)될 수 있으므로 수동 편집을 권장하지 않는다.

## Refresh command

```bash
./scripts/chat/run_recommend_quality_loop.sh
```
