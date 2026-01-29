# I-0344 — PII Masque/Logic Policy (field level) + Keeping cycle/delete (optional)

## Goal
controls personal information (PII) entering log/Event/OLAP,
Copyright (C) 2015 SHINSEGAE LANGUAGE SCHOOL. All Rights Reserved.

## Why
- Request/trace/log
- “Originity” and “Proverbs” balanced operation

## Scope
### 1) PII Classification/Policy
- PII:
  - user id(name), session id, ip, user-agent, email/phone(end)
  - chat prompt(especially risk)
- Gallery News
  - ip masking/hash
  - user id Internal surrogate key + external exposure ban
  - Chat prompt prohibits the basic storage (sampling/painting with options)

### 2) Field Level Masking
- Automatic masking specific field in structured logging
- PII Removal/Resolution before loading Kafka/OLAP

### 3) Storage cycle/detection
- raw log retention(e.g. 7~30days)
- OLAP is a long-term storage after aggregate / profit
- Delete Batch(e.g.   TBD  )

### 4) Documentation
- “What data is stored” data map
- Operator Action (Deletion Request/Sago Response)

## Non-goals
- Full of legal compliance (e.g. GDPR full) completed (extra extension)

## DoD
- PII in Log/Event is Masque/Removed (Sample Verification)
- retention job is running and there are indicators/alams
- Data map documents exist

## Codex Prompt
Add PII masking & retention:
- Define PII fields and implement field-level masking in logs and event pipelines.
- Add retention/deletion jobs for logs and raw data.
- Document a data map and verify with sampling tests.
