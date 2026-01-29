# Contracts

## Source of truth
- `contracts/*.schema.json` and `contracts/openapi/*` are the SSOT for payloads.
- Examples live in `contracts/examples/` and must validate against schemas.

## Versioning
- **SemVer** for each contract file.
  - **MAJOR**: breaking change
  - **MINOR**: backward-compatible additions
  - **PATCH**: docs/typos only

## Compatibility rules
- ✅ Add optional field
- ✅ Add new endpoint
- ❌ Remove field/endpoint
- ❌ Change type or shrink enum
- ❌ Make optional → required

## Validation & compatibility gate
- `scripts/validate_contracts.py` validates examples against schemas.
- `scripts/contract_compat_check.py` compares contracts against a base git ref and fails on breaking changes.

## How to run locally
```
python scripts/validate_contracts.py
BASE_REF=origin/develop python scripts/contract_compat_check.py
```
