# File: tasks/backlog/B-0319-spell-offline-eval-and-quality-loop.md

# B-0319 — Spell Offline Eval + Quality Loop (regression gate for spell behavior)

## Goal
Build an offline evaluation + regression framework for spell correction:
- detects over-correction and numeric/token corruption
- tracks accept-rate and improvements over time
- provides a stable “Golden set” for CI gating (optional initially)

This is the "quality loop" counterpart to B-0316/0317/0318.

## Background / Current State
- QS has rewrite log storage (SQLite) and metrics.
- Spell is currently provider-based; real spell will be MIS-backed.
- Without eval, spell changes can silently degrade search (worse than doing nothing).

## Scope
### 1) Dataset
Create evaluation datasets:
- Golden set (fixed, curated): 300~2,000 queries
- Hard set (edge cases):
  - ISBN, volume, series tokens, mixed ko/en, chosung, punctuation-heavy
- Recent set (optional): sampled from logs (requires privacy-safe collection)

Data format (jsonl):
{ "q_raw": "...", "expected": "...", "tags": ["volume","author","spacing"] }

### 2) Evaluator Script
Add `scripts/eval/spell_eval.py` that:
- Calls QS (or directly calls MIS spell + QS guardrails) in batch
- Computes metrics:
  - exact_match_rate vs expected
  - token_preservation (digits/ISBN/volume)
  - over_correction_rate (edit distance too large)
  - unchanged_rate (no-op)
  - latency stats (p50/p95)
- Produces:
  - JSON report
  - Markdown summary
  - Failure dump (top N failures)

### 3) Regression Gate (optional initial, required later)
Add a mode `--gate` that fails if:
- token_preservation drops below threshold
- over_correction rises above threshold
- exact match drops beyond delta
  This can later be plugged into CI (I-0318 style) but for now it should be runnable locally.

### 4) Feedback Loop Integration
- Export “failures” into a file that can be imported into:
  - QS spell dictionary (B-0318)
  - MIS model fine-tuning backlog (future)
- Optionally store eval_run rows in DB if available (future ticket)

## Non-goals
- Human labeling UI (Admin) — separate ticket
- Online A/B testing framework (separate ticket)
- Training pipeline (separate ticket)

## Config (env / args)
- QS_URL (default http://localhost:8001)
- MIS_URL (optional if evaluating MIS directly)
- DATASET_PATH (default data/eval/spell/golden.jsonl)
- BATCH_SIZE, TIMEOUT_SEC
- GATE_* thresholds

## DoD
- `scripts/eval/spell_eval.py` runs end-to-end and outputs:
  - data/eval/reports/spell_eval.json
  - data/eval/reports/spell_eval.md
  - data/eval/reports/spell_failures.jsonl
- Includes at least:
  - sample golden dataset (>=50 queries)
  - hard set dataset (>=30 queries)
- Basic regression gate mode implemented with sensible defaults
- Document how to add new cases and interpret reports

## Files to Add/Change
- `scripts/eval/spell_eval.py` (new)
- `data/eval/spell/golden.jsonl` (new)
- `data/eval/spell/hard.jsonl` (new)
- `data/eval/reports/` (output folder; commit sample report optional)
- `docs/eval/spell_eval.md` (new)

## Commands
- `python scripts/eval/spell_eval.py --dataset data/eval/spell/golden.jsonl --out data/eval/reports/`
- `python scripts/eval/spell_eval.py --dataset data/eval/spell/hard.jsonl --gate`

## Codex Prompt
Create an offline spell evaluation tool for QS/MIS spell correction:
datasets (golden/hard), batch runner, metrics, markdown+json reports, and optional regression gate mode.
Include failure dumps that can feed back into the domain dictionary and future training.
Keep it self-contained and runnable locally.
