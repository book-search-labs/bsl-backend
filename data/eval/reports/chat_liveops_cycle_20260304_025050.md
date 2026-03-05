# Chat LiveOps Cycle Report

- generated_at: 2026-03-03T17:50:50.324547+00:00
- release_signature: 392ee76bc1355c49
- launch_gate_pass: false
- release_action: rollback
- release_reason: launch_gate_failed
- next_stage: 12

## Failures

- budget gate failed: insufficient perf samples: window_size=0 < min_window=20
- insufficient reason samples: window_size=0 < min_reason_window=20
- insufficient legacy samples: window_size=0 < min_legacy_window=20
- insufficient replay samples: run_total=0 < min_run_window=20
- insufficient commerce samples: commerce_total=0 < min_commerce_samples=10
- cycle failure regression: baseline=0, current=5, allowed_increase=1
- launch gate pass regression: baseline_pass=true current_pass=false