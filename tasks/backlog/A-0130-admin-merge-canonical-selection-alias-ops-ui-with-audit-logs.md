# A-0130 — Admin Authority/Merge Ops UI (material merge, agent alias)

## Goal
Authority can be managed by the operator
- New *material merge(plated/recurer/set duplicate string + selected representative)* News
- New *Agent alias* News
- Provides operational UI based on change history/reduction log

## Background
- Large-scale LOD/NLK data fills redundancy/mark variations.
- Search quality (reverse exposure/click dispersion/CTR distortion) and operating stability (LTR feature).

## Scope
### 1) Material Merge Ops
- Select a page Select a page... id="menu-item-15">Home id="menu-item-1768">Past Issues id="menu-item-2447">Book Reviews id="menu-item-5885">UXPA
  - Author overlap
- Merge group
  - group material list
  - Select Material master id
  - merge reason/memo
- Action
  - merge approval / unmerge(rollback)
  - Gallery

### 2) Agent Authority Ops
- agent candidate group (name/label)
  - Example: “Kim Young-ha” vs “Kim Young-ha”
- alias mapping
  - canonical_agent_id ← variants[]
- Action
  - alias add/delete
  - canonical changes (required)

### 3 years Impact Preview (Optional)
- when applying merge/alias:
  - SERP Grouping Change (Sample queries)
  - index reindex

## Non-goals
- Implementation of automatic candidate creation algorithm (B-0221b/B-0300/B-0301 area)
- Practical reindex job execution UI(A-0113)

## Data / API (via BFF)
- `GET /admin/authority/material/merge-candidates`
- `GET /admin/authority/material/merge-groups/{group_id}`
- `POST /admin/authority/material/merge-groups/{group_id}/approve`
- `POST /admin/authority/material/merge-groups/{group_id}/rollback`
- `GET /admin/authority/agent/candidates`
- `POST /admin/authority/agent/aliases`

## Persistence (suggested)
- material_merge_group(group_id, status, master_id, members_json, created_at)
- agent_alias(canonical_agent_id, alias_text, source, created_at)
- All changes recorded audit log

## Security / Audit
- merge/rollback/CEO changed RBAC + audit log required
- (optional) 2 person approval workflow expandable

## DoD
- Can be selected by the operator to group the duplicate books
- Canonical can be bundled with author notation strain
- Change history/reduction logs can be left and rollbacked

## Codex Prompt
Implement the Authority/Merge operation UI in Admin(React).
Material merge candidates → group detail → approve/rollback
Agent alias candidates → canonical mapping management screen.
Call BFF API and apply audit log/RBAC prerequisites.
