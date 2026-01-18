# T-0103 — Admin UI: Layout Shell + Router + Sidebar (MVP)

## Goal
Introduce a **shared Admin layout (Topbar + Sidebar + Content Outlet)** into `apps/web-admin`, and organize routing based on **React Router**.

After this is done:
- All pages use the same Admin Shell layout.
- The sidebar menu is rendered from data (SSOT).
- Route/menu/layout code is separated into maintainable modules.

Non-goals:
- No design polish (perfect responsiveness / dark mode / role-based menu control).
- No API integration (e.g., fetching dashboard metrics).
- No new UI library/design system. (Keep Bootstrap)

---

## Must Read (SSOT)
- `apps/web-admin/README.md` (if it exists)
- `apps/web-admin/.env.example` (check env var conventions)
- (if present) `AGENTS.md` (repo working rules)

---

## Scope

### Allowed
- `apps/web-admin/src/**`
- `apps/web-admin/index.html` (only if necessary)
- `apps/web-admin/README.md` (if adding run/routing notes)

### Forbidden
- Modifying other apps (`apps/web-user`, etc.)
- Modifying backend services/contracts/infra directories

---

## Current Context
Pages currently exist as `apps/web-admin/src/pages/*Page.tsx`:
- `DashboardPage.tsx`
- `PlaygroundPage.tsx`
- `ComparePage.tsx`
- `SettingsPage.tsx`

In this ticket, **keep the pages as-is** and only add/organize **layout + router + menu setup**.

---

## Implementation Plan

### 1) Add directories/files
Add the following structure (keep the existing `pages/`):

apps/web-admin/src/
app/
router.tsx
layout/
AdminLayout.tsx
Topbar.tsx
Sidebar.tsx
shared/
types/
nav.ts
components/
StatCard.tsx
PageHeader.tsx

> If you want the minimum implementation, `StatCard/PageHeader` are optional,
> but they’re useful for quickly shaping the dashboard into a “screenshot-like card layout”, so recommended.

---

### 2) Router setup (react-router-dom v7)
Use `createBrowserRouter` + `RouterProvider`.

Route requirements:
- `/` → redirect to `/dashboard`
- `/dashboard` → `DashboardPage`
- `/search/playground` → `PlaygroundPage`
- `/search/compare` → `ComparePage`
- `/settings` → `SettingsPage`

`AdminLayout` acts as the root layout and renders pages via `<Outlet />` internally.

---

### 3) Make the sidebar menu SSOT
Manage the menu definition in **exactly one place**.

- In `src/app/router.tsx` or `src/shared/types/nav.ts`:
  - define `navItems` (for Sidebar rendering)
  - define `router` (router definition)
  - either keep them together, or export the nav model from `router.tsx`

Menu requirements:
- Sections:
  - Dashboard (children: Dashboard v1/v2/v3 can be placeholder links for now, or only keep v1)
  - Search Tools (Playground, Compare)
  - Settings
- Highlight the current location (active)
- Group collapse/expand (accordion) is **optional**
  - For MVP, listing items is OK
  - For future extensibility, a Collapse-based structure is recommended

---

### 4) Layout (Shell) setup (Bootstrap-based)
Layout has 3 regions:
- Topbar: fixed at the top (logo + right-side text)
- Sidebar: fixed left navigation
- Content: main content area

Basic behavior:
- Desktop: fixed sidebar width (e.g., 280px)
- Content area has `margin-left` equal to the sidebar width
- Content has `padding-top` equal to the topbar height

Recommended Bootstrap components:
- Topbar: `Navbar`
- Sidebar: `Nav` + `NavLink` (react-router) combo
- Layout: handle fixed positioning + spacing via CSS

---

### 5) Dashboard MVP (for validating layout)
Make `DashboardPage` simple (no API) to verify layout correctness:
- Page title: “Dashboard”
- 4 stat cards (e.g., New Queries / Avg Latency / Zero Results / Rerank On)
- Values are hard-coded (150, 44ms, 12, 65%)

---

## Acceptance Tests

### 1) Run locally
```bash
cd apps/web-admin npm install npm run dev -- --port 5174
```

### 2) Verify behavior
- Visiting `http://localhost:5174/` redirects to `/dashboard`
- Left sidebar is visible, topbar is visible, and content does not overlap
- Clicking menu items navigates correctly:
  - `/dashboard`
  - `/search/playground`
  - `/search/compare`
  - `/settings`
- Current route is highlighted as active

✅ Done when:
- Layout/router/sidebar are organized into separate files and a clean structure
- The 4 routes work correctly and the Shell layout applies to all screens
- Dashboard shows minimal UI with a card layout

---

## Output (include in Dev Summary)
- List of changed/added files
- How to run
- Key route list
- Known limitations (MVP)

If you want, I can also convert this into a **T0103 Codex prompt** format (“Read this md and implement until DONE is satisfied”).
