# Spell Eval (Offline)

This eval runner measures spell-correction quality offline and produces JSON + Markdown reports along with a failure dump.

## Dataset format (jsonl)

Each line is a JSON object:

```json
{ "q_raw": "해리 포터 1 권", "expected": "해리포터 1권", "tags": ["ko","spacing","volume"] }
```

Fields:
- `q_raw`: original query.
- `expected`: expected corrected form.
- `tags`: list of tags (optional, used for filtering/analysis).

## Run (QS mode)

```bash
python scripts/eval/spell_eval.py --dataset data/eval/spell/golden.jsonl --out data/eval/reports --mode qs
```

## Run (MIS mode)

```bash
python scripts/eval/spell_eval.py --dataset data/eval/spell/hard.jsonl --out data/eval/reports --mode mis --mis-url http://localhost:8005
```

## Spell Model Enablement

For local dev with a real ONNX model, run:

```bash
./scripts/mis/run_mis_spell.sh
```

Then validate via:

```bash
./scripts/mis/spell_smoke_test.sh
```

## Outputs

- `data/eval/reports/spell_eval.json`
- `data/eval/reports/spell_eval.md`
- `data/eval/reports/spell_failures.jsonl`

## Regression gate

```bash
python scripts/eval/spell_eval.py --dataset data/eval/spell/golden.jsonl --gate \
  --min-exact-match 0.6 --min-token-preservation 0.95 --max-over-correction 0.1
```

To compare against a baseline report:

```bash
python scripts/eval/spell_eval.py --dataset data/eval/spell/golden.jsonl --gate \
  --baseline-report data/eval/reports/spell_eval.json --max-exact-drop 0.02
```

## Adding new cases

1. Append new jsonl lines to `data/eval/spell/golden.jsonl` or `data/eval/spell/hard.jsonl`.
2. Re-run the eval script.
3. Review `spell_failures.jsonl` for cases to add into the QS spell dictionary.
