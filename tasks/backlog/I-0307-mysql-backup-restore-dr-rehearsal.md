# I-0307 — MySQL backup/recovery + DR rehearsal script

## Goal
Canonical DB (MySQL)
- About Us
- Recovery Procedure
- DR Rehearsal
© Copyright 2019 EatinKorea. All Rights Reserved

## Why
- DB in data pipeline/operation is easy to be a single failure point
- “While it’s going to be rehearsal” is the core of the sea view.

## Scope
### 1) Backup Mode(v1)
- Port: Shenzhen
  - New  TBD   (Skinma+data) About Us
  - New  TBD   /   TBD  
- Browse By Tag News
  - Skip to main content

### 2) Recovery procedure (v1)
- Restore new MySQL instances
- Flyway migration reuse (required)
- App connection check + smoke test

### 3) DR Rehearsal
- Month 1 (or before release):
  - Restore from new containers with backup files
  - Core queries/index/search smoke test passed

### 4) Automation/Discovery
- backup result file checksum
- Back-up Success/Factor Notifications (simple log/metric)

### 5) Documents
- New  TBD  : Backup / Rehearsal step-by-step

## Non-goals
- Multi-Liquid/Multi-AZ Reproduction (Secretary)
- Completed PITR (extendable based on binlog)

## DoD
- Backup scripts run and generate archives + archives
- Repair scripts to restore normal to new DB
- DR Rehearsal checklist + Smoke test command documented
- Minimum 1 rehearsal execution record (log/memo)

## Codex Prompt
Add MySQL backup/restore + DR rehearsal:
- Provide scripts for backup (dump/backup tool) and restore into a fresh instance.
- Include checksum verification and retention rules.
- Write a DR runbook with a rehearsal procedure and smoke tests.
- Validate by performing a restore locally and confirming app queries succeed.
