import { useEffect, useMemo, useState } from "react";
import { Collapse, Container, Nav, Navbar } from "react-bootstrap";
import { NavLink, Outlet, useLocation } from "react-router-dom";

type SidebarLeaf = {
  type: "leaf";
  key: string;
  label: string;
  icon?: string;
  to: string;
  end?: boolean;
  aliases?: string[];
};

type SidebarGroup = {
  type: "group";
  key: string;
  label: string;
  icon?: string;
  children: SidebarNode[];
};

type SidebarNode = SidebarLeaf | SidebarGroup;

const sidebarItems: SidebarNode[] = [
  {
    type: "group",
    key: "dashboard",
    label: "Dashboard",
    icon: "bi-speedometer2",
    children: [
      {
        type: "leaf",
        key: "dash-v1",
        label: "Dashboard v1",
        to: "/dashboard/v1",
        aliases: ["/dashboard"],
      },
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
      { type: "leaf", key: "search-playground", label: "Search Playground", to: "/search-playground" },
      { type: "leaf", key: "compare", label: "Compare", to: "/tools/compare" },
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
          { type: "leaf", key: "doc-lookup", label: "Doc Lookup", to: "/ops/index/doc-lookup" },
        ],
      },
      { type: "leaf", key: "ops-jobs", label: "Jobs", icon: "bi-lightning", to: "/ops/jobs" },
    ],
  },
  { type: "leaf", key: "settings", label: "Settings", icon: "bi-sliders", to: "/settings" },
];

function isGroup(node: SidebarNode): node is SidebarGroup {
  return node.type === "group";
}

function matchPath(pathname: string, target: string, end?: boolean) {
  if (target === "/") return pathname === "/";
  if (end) return pathname === target;
  return pathname === target || pathname.startsWith(target + "/");
}

function leafMatchesPath(node: SidebarLeaf, pathname: string) {
  if (matchPath(pathname, node.to, node.end)) return true;
  if (!node.aliases?.length) return false;
  return node.aliases.some((alias) => matchPath(pathname, alias, true));
}

function nodeContainsPath(node: SidebarNode, pathname: string): boolean {
  if (node.type === "leaf") return leafMatchesPath(node, pathname);
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

  const initialOpen = useMemo(() => {
    const open: Record<string, boolean> = {};
    const keys = collectGroupKeys(items);
    for (const k of keys) open[k] = false;

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
    setOpenGroups((prev) => {
      const next = { ...prev };
      for (const [key, value] of Object.entries(initialOpen)) {
        if (value) next[key] = true;
      }
      return next;
    });
  }, [initialOpen]);

  const toggleGroup = (key: string) => {
    setOpenGroups((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const renderNode = (node: SidebarNode, depth: 1 | 2 | 3) => {
    if (node.type === "leaf") {
      const paddingLeft = depth === 1 ? 12 : depth === 2 ? 24 : 36;
      const active = leafMatchesPath(node, location.pathname);
      const linkClassName = [
        "sidebar-link",
        "nav-link",
        "d-flex",
        "align-items-center",
        active ? "active" : "",
      ]
        .filter(Boolean)
        .join(" ");

      return (
        <NavLink
          key={node.key}
          to={node.to}
          end={node.end}
          className={linkClassName}
          style={{ paddingLeft }}
        >
          {node.icon ? <i className={`bi ${node.icon} me-2`} /> : null}
          <span>{node.label}</span>
        </NavLink>
      );
    }

    const isOpen = !!openGroups[node.key];
    const active = nodeContainsPath(node, location.pathname);
    const nextDepth = (Math.min(depth + 1, 3) as 2 | 3);
    const paddingLeft = depth === 1 ? 12 : depth === 2 ? 24 : 36;

    return (
      <div key={node.key} className="w-100">
        <button
          type="button"
          className={[
            "sidebar-group-btn",
            "w-100",
            "text-start",
            "d-flex",
            "align-items-center",
            "justify-content-between",
            active ? "active" : "",
          ]
            .filter(Boolean)
            .join(" ")}
          onClick={() => toggleGroup(node.key)}
          style={{ paddingLeft }}
          aria-expanded={isOpen}
        >
          <span className="d-flex align-items-center">
            {node.icon ? <i className={`bi ${node.icon} me-2`} /> : null}
            <span>{node.label}</span>
          </span>
          <i className={`bi bi-chevron-right sidebar-caret ${isOpen ? "open" : ""}`} />
        </button>

        <Collapse in={isOpen}>
          <div className="mt-1">
            <Nav className="flex-column gap-1">{node.children.map((c) => renderNode(c, nextDepth))}</Nav>
          </div>
        </Collapse>
      </div>
    );
  };

  return <Nav className="flex-column gap-1">{items.map((n) => renderNode(n, 1))}</Nav>;
}

export default function AdminLayout() {
  return (
    <div className="admin-shell d-flex flex-column vh-100">
      <Navbar bg="dark" variant="dark" className="px-3">
        <Navbar.Brand className="d-flex align-items-center gap-2">
          <i className="bi bi-book" />
          <span>도서검색 Admin</span>
        </Navbar.Brand>
        <div className="ms-auto text-white-50 small">Admin Frontend</div>
      </Navbar>

      <div className="d-flex flex-grow-1 overflow-hidden">
        <aside className="admin-sidebar border-end d-flex flex-column">
          <div className="px-3 pt-3 pb-2 text-uppercase text-muted small fw-semibold">Menu</div>
          <div className="flex-grow-1 overflow-auto px-2 pb-3">
            <SidebarTree items={sidebarItems} />
          </div>
        </aside>

        <main className="admin-content flex-grow-1 overflow-auto">
          <Container fluid className="py-3">
            <Outlet />
          </Container>
        </main>
      </div>
    </div>
  );
}
