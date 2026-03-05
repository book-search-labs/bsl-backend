# Chat Production Launch Gate Report

- generated_at: 2026-03-03T17:50:50.220971+00:00
- release: model=unknown prompt=unknown policy=unknown signature=392ee76bc1355c49
- pass: false
- failure_count: 5

## Key Metrics

- commerce_completion_rate: 0.0000 (0/0)
- insufficient_evidence_ratio: 0.0000

## Gate Failures

- budget gate failed: insufficient perf samples: window_size=0 < min_window=20
- insufficient reason samples: window_size=0 < min_reason_window=20
- insufficient legacy samples: window_size=0 < min_legacy_window=20
- insufficient replay samples: run_total=0 < min_run_window=20
- insufficient commerce samples: commerce_total=0 < min_commerce_samples=10