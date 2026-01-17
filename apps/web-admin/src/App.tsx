import { Container, Nav, Navbar, Collapse } from "react-bootstrap";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";

import DashboardPage from "./pages/DashboardPage";
import PlaygroundPage from "./pages/PlaygroundPage";
import ComparePage from "./pages/ComparePage";
import SettingsPage from "./pages/SettingsPage";

type SidebarLeaf = {
  type: "leaf";
  key: string;
  label: string;
  icon?: string;
  to: string;
  end?: boolean;
};

type SidebarGroup = {
  type: "group";
  key: string;
  label: string;
  icon?: string;
  children: SidebarNode[];
};

type SidebarNode = SidebarLeaf | SidebarGroup;

function isGroup(node: SidebarNode): node is SidebarGroup {
  return node.type === "group";
}

function matchPath(pathname: string, target: string) {
  if (target === "/") return pathname === "/";
  return pathname === target || pathname.startsWith(target + "/");
}

function nodeContainsPath(node: SidebarNode, pathname: string): boolean {
  if (node.type === "leaf") return matchPath(pathname, node.to);
  return node.children.some((c) => nodeContainsPath(c, pathname));
}

function collectGroupKeys(nodes: SidebarNode[], acc: string[] = []) {
  for (const n of nodes) {
    if (isGroup(n)) {
      acc.push(n.key);
      collectGroupKeys(n.children, acc);
    }
  }
  return acc;
}

function SidebarTree({ items }: { items: SidebarNode[] }) {
  const location = useLocation();

  // URL에 해당하는 그룹은 자동으로 open
  const initialOpen = useMemo(() => {
    const open: Record<string, boolean> = {};
    const keys = collectGroupKeys(items);
    for (const k of keys) open[k] = false;

    // 현재 경로를 포함하는 그룹들을 open 처리
    const walk = (nodes: SidebarNode[]) => {
      for (const n of nodes) {
        if (isGroup(n)) {
          if (nodeContainsPath(n, location.pathname)) open[n.key] = true;
          walk(n.children);
        }
      }
    };
    walk(items);
    return open;
  }, [items, location.pathname]);

  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(initialOpen);

  useEffect(() => {
    // 새로고침 / 직접 URL 진입 시 열려야 하는 그룹을 보장
    setOpenGroups((prev) => ({ ...initialOpen, ...prev }));
  }, [initialOpen]);

  const toggleGroup = (key: string) => {
    setOpenGroups((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const renderNode = (node: SidebarNode, depth: 1 | 2 | 3) => {
    // depth 3에서는 group을 만들지 않는 게 UX상 보편적(필요하면 허용 가능)
    if (node.type === "leaf") {
      const paddingLeft = depth === 1 ? 12 : depth === 2 ? 24 : 36;

      return (
        <Nav.Link
          key={node.key}
          as={NavLink}
          to={node.to}
          end={node.end as any}
          className="sidebar-link d-flex align-items-center"
          style={{ paddingLeft }}
        >
          {node.icon ? <i className={`bi ${node.icon} me-2`} /> : null}
          <span>{node.label}</span>
        </Nav.Link>
      );
    }

    // group
    const isOpen = !!openGroups[node.key];
    const active = nodeContainsPath(node, location.pathname);
    const nextDepth = (Math.min(depth + 1, 3) as 2 | 3);

    const paddingLeft = depth === 1 ? 12 : depth === 2 ? 24 : 36;

    return (
      <div key={node.key} className="w-100">
        <button
          type="button"
          className={
            "btn w-100 text-start d-flex align-items-center justify-content-between rounded sidebar-group-btn " +
            (active ? "active" : "")
          }
          onClick={() => toggleGroup(node.key)}
          style={{ paddingLeft }}
        >
          <span className="d-flex align-items-center">
            {node.icon ? <i className={`bi ${node.icon} me-2`} /> : null}
            <span>{node.label}</span>
          </span>
          <i className={`bi bi-chevron-right sidebar-caret ${isOpen ? "open" : ""}`} />
        </button>

        <Collapse in={isOpen}>
          <div className="mt-1">
            <Nav className="flex-column gap-1">
              {node.children.map((c) => renderNode(c, nextDepth))}
            </Nav>
          </div>
        </Collapse>
      </div>
    );
  };

  return <Nav className="flex-column gap-1">{items.map((n) => renderNode(n, 1))}</Nav>;
}

function PlaceholderPage({ title }: { title: string }) {
  return (
    <div className="p-3 bg-white border rounded">
      <h4 className="mb-0">{title}</h4>
      <div className="text-muted small mt-2">TODO: implement</div>
    </div>
  );
}

export default function App() {
  // ✅ 3-depth 예시 구조
  const sidebarItems: SidebarNode[] = useMemo(
    () => [
      {
        type: "group",
        key: "dashboard",
        label: "Dashboard",
        icon: "bi-speedometer2",
        children: [
          { type: "leaf", key: "dash-v1", label: "Dashboard v1", to: "/dashboard/v1" },
          { type: "leaf", key: "dash-v2", label: "Dashboard v2", to: "/dashboard/v2" },
          { type: "leaf", key: "dash-v3", label: "Dashboard v3", to: "/dashboard/v3" },
        ],
      },
      {
        type: "group",
        key: "search-tools",
        label: "Search Tools",
        icon: "bi-search",
        children: [
          { type: "leaf", key: "playground", label: "Playground", to: "/playground" },
          { type: "leaf", key: "compare", label: "Compare", to: "/compare" },
        ],
      },
      {
        type: "group",
        key: "ops",
        label: "Ops",
        icon: "bi-gear",
        children: [
          {
            type: "group",
            key: "ops-index",
            label: "Index & Data",
            icon: "bi-database",
            children: [
              { type: "leaf", key: "indices", label: "Indices", to: "/ops/index/indices" },
              { type: "leaf", key: "docs", label: "Doc Lookup", to: "/ops/index/docs" },
            ],
          },
          {
            type: "group",
            key: "ops-jobs",
            label: "Jobs",
            icon: "bi-lightning",
            children: [
              { type: "leaf", key: "ingestion", label: "Ingestion", to: "/ops/jobs/ingestion" },
              { type: "leaf", key: "reindex", label: "Reindex", to: "/ops/jobs/reindex" },
            ],
          },
        ],
      },
      {
        type: "leaf",
        key: "settings",
        label: "Settings",
        icon: "bi-sliders",
        to: "/settings",
      },
    ],
    []
  );

  return (
    <div className="d-flex flex-column vh-100">
      {/* Topbar */}
      <Navbar bg="dark" variant="dark" className="px-3" expand={false}>
        <Navbar.Brand className="d-flex align-items-center gap-2">
          <i className="bi bi-book" />
          <span>도서검색 Admin</span>
        </Navbar.Brand>
        <div className="ms-auto text-white-50 small">Admin Frontend</div>
      </Navbar>

      {/* Body */}
      <div className="d-flex flex-grow-1 overflow-hidden">
        {/* Sidebar */}
        <aside className="border-end bg-light p-2" style={{ width: 280 }}>
          <div className="px-2 py-2 fw-semibold text-secondary small">MENU</div>
          <SidebarTree items={sidebarItems} />
        </aside>

        {/* Content */}
        <main className="flex-grow-1 overflow-auto bg-body-tertiary">
          <Container fluid className="py-3">
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/dashboard/v1" element={<DashboardPage />} />
              <Route path="/dashboard/v2" element={<DashboardPage />} />
              <Route path="/dashboard/v3" element={<DashboardPage />} />

              <Route path="/playground" element={<PlaygroundPage />} />
              <Route path="/compare" element={<ComparePage />} />

              {/* 3-depth placeholder routes */}
              <Route path="/ops/index/indices" element={<PlaceholderPage title="Ops / Index / Indices" />} />
              <Route path="/ops/index/docs" element={<PlaceholderPage title="Ops / Index / Doc Lookup" />} />
              <Route path="/ops/jobs/ingestion" element={<PlaceholderPage title="Ops / Jobs / Ingestion" />} />
              <Route path="/ops/jobs/reindex" element={<PlaceholderPage title="Ops / Jobs / Reindex" />} />

              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </Container>
        </main>
      </div>
    </div>
  );
}
