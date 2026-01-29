# A-0120 — Web Admin: Convert API calls to BFF

## Goalkeeper
- Web Admin(5173)'s API call is pointed to the BFF single entry point**.
- Admin function (ops/reindex/policy/experiment/products, etc.) will endanger BFF.
- In the transition process, it can be recovered directly to fallback (short, Admin is conserved).

## Scope(Scope)
- Change all server API calls to BFF
  - ops task / reindex
  - Policies/Experiments
  - Catalog/Product(with Phase 8)
- Tag:
  - `VITE_ADMIN_API_MODE=bff_primary | bff_only`
  - direct fallback(optional): Allows for read-only screen, write/execute recommended fallback

## Copyright (c) 2014. All Rights Reserved.
- New *READ series(list/detail)**: Allows direct fallback when BFF failed
- New *WRITE/EXECUTE family (reindex execution/policy change/distribution/rollback)**: fallback ban
  - Reason: The operation risk operation should always be done by BFF, Auth/RBAC/Audit/RateLimit

## DoD
- [ ] All API calls for Admin BFF priority
- [ ] read-only can be fallback when disability, write/execute refuse fallback
- [ ] Direct-call removal from prod
- New News Admin hazards work is only called as a route left in audit log(B-0227 Integration)

## Codex Prompt
Convert all API calls from Web Admin(5173) to BFF.
- bff primary/bff only mode with env toggle.
- read-only call only fallback allowed, write/execute implement fallback ban.
- ops/policy/experiment/products
-  TBD   and add the operation transition/rollback document.
