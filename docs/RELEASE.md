# Release & Deployment Strategy

This document defines the **production release** approach for BSL.

---

## 1) Environments

- **dev**: local + fast iteration
- **stage**: full stack, mirrors prod config
- **prod**: customer traffic only

**Rule:** no secrets in repo. Use env injection (SSM/Vault/K8s Secrets).

---

## 2) CI/CD Pipeline (minimum)

Pipeline stages:
1) **Lint/Validate** — contracts + feature spec
2) **Unit/Integration Tests** — Java + Python
3) **Build Artifacts** — Docker images with semantic tags
4) **Stage Deploy** — smoke tests + SLO gate
5) **Prod Deploy** — blue/green or canary

Release gates:
- p95 latency < target
- error rate < 1%
- health checks green

---

## 3) Blue/Green (serving services)

**Flow:**
1) Deploy **green** alongside **blue**
2) Warm caches + run smoke tests
3) Shift traffic (10% → 50% → 100%)
4) Monitor SLOs; rollback if error rate or p99 spikes

**Rollback:**
- Flip traffic back to blue
- Keep green for postmortem

---

## 4) Canary (riskier services)

- Start at 1–5% traffic
- Increase gradually when SLOs hold
- Abort on error rate > 1% or p99 threshold

---

## 5) Release Checklist (prod)

- [ ] Backups complete (MySQL + OpenSearch)
- [ ] Observability dashboards green
- [ ] New release smoke tests passed
- [ ] Rollback plan documented

