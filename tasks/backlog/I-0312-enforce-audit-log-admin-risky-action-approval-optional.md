# I-0312 — Audit Log Force + Admin Assurance (Option) (Security/Ops)

## Goal
For the operation / policy / data change operations performed by Admin
1) New *Forcing 100% loading**
2) (Optional) **Admission for 2Dual-approval**

## Why
- If you do not leave “Who/Who/Who”, the operation will soon lead to accident
- reindex/merge/synonym deployment/replacement changes must be especially dangerous → minimum tracking

## Scope
### 1) Audit Log Force(Required)
- Record Target(min):
  - RBAC Change (Registration/Registration)
  - Reindex/Index Ops Trigger
  - Change/Distribution of Member/Normalization Set
  - Authority merge
  - Copyright (c) 2015 SHINSEGAE LANGUAGE SCHOOL. All Rights Reserved.
  - (Extra) Commerce operation (Refund/Cancel/Rego Force)
- Record Field (Ne skimmer standard):
  - actor_admin_id, action, resource_type/resource_id
  - before json/after json
  - request_id/trace_id/ip/user_agent

### 2) Classification and Policy
- Manage risk job lists to config:
  - e.g. `REINDEX_TRIGGER`, `ALIAS_SWAP`, `SYNONYM_DEPLOY`, `AUTHORITY_MERGE`, `RBAC_CHANGE`
- Risk Working Min:
  - Admin RBAC authority + audit log record is required

### 3) 2 person approval (optional)
- Flow:
  1) Create a request for a request for a request (status: PENDING APPROVAL)
  2) Approve (Admin B) after approval
  3) Record of execution results (SUCCESS/FAILED)
- Storage:
  -  TBD  in   TBD  ,   TBD  ,   TBD  field added (or separate approval table)

### 4) UI linkage
- Admin UI(A-0113/A-0130 etc.):
  - Audit log view/filter
  - Approval Standby List/Rail Button(Option)

## Non-goals
- Complete SOX level control (outer range)
- External SIEM Integration (Extra)

## DoD
- BFF’s Admin write endpoint not missing audit log records (powered by middleware/interceptor)
- If you turn on the “required to win” option, you cannot run without approval
- Audit log query API + Admin can be viewed on screen (minimum)
- Sample scenario validation (e.g. reindex → approval → execution → log confirmation)

## Codex Prompt
Implement admin audit & optional dual-approval:
- Enforce audit_log writes for all admin mutating endpoints in BFF.
- Define a risk-action policy list and block risky actions unless approved (optional feature flag).
- Extend ops_task (or new table) to support approvals and track approver/ timestamps.
- Add minimal APIs + admin UI hooks to view logs and approve tasks.
