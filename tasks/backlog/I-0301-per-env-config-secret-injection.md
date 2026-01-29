# I-0301 — per-env config (dev/stage/prod) + secret injection/rotation (extensible)

## Goal
Set/Set/Set by environment(dev/stage/prod),
New *Secret injection/rotation(rotation)** to create a scalable configuration system.

## Why
- When you go back to the local service to the operation stage, the first part is set/check
- BFF/MIS/LLM key/Kafka/DB/OS

## Scope
### 1) Setting layer
- New  TBD   directory standardization
  - `application-dev.yml`, `application-stage.yml`, `application-prod.yml` (Spring)
  - New  TBD  ,   TBD  ,   TBD   (FastAPI/etc)
- Common rules:
  - “Prohibiting Value Hardcoding on Code”
  - override by environment explicitly

### 2) Secret injection(초기 v1)
- dev:   TBD   + docker compose secrets
- stage/prod: 1 out of the below structure only
  - AWS SSM Parameter Store / Secrets Manager
  - Vault
  - Kubernetes Secret

### 3) Rotation design
- key/versioned secret support
  - Example:   TBD  ,   TBD  
- App can be reloaded without referring to “current active key” or reboot

### 4) Verification/guard
- When booting “required env missing” check (faster fail)
- secret value log output ban (masking)
- Documents:   TBD  + Providing a Example Template

## Non-goals
- IaC (Terraform) Complete (Cancel Ticket)
- Full uninterrupted secret rotation automation (starting with manual procedures in seconds)

## DoD
- set file/environmental variable system by dev/stage/prod is cleaned to repo
- fail-fast when each service loads config as the same rule
- secret value is not exposed to log/error
- “Exhibition Procedure” Documents are present and reproduced

## Codex Prompt
Create per-environment config & secret handling:
- Standardize config files and env var loading across services.
- Add fail-fast validation and log masking for secrets.
- Provide templates and documentation for dev/stage/prod.
- Define a rotation approach with versioned secrets and operational steps.
