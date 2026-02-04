import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Form, Spinner } from "react-bootstrap";

import { fetchJson } from "../lib/api";
import { createRequestContext, resolveBffBaseUrl } from "../lib/apiRouter";

type KdcNode = {
  id?: number;
  code?: string;
  name?: string;
  depth?: number;
  children?: KdcNode[];
};

type KdcResponse = {
  version?: string;
  trace_id?: string;
  request_id?: string;
  categories?: KdcNode[];
};

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, "")}${path}`;
}

function hasChildren(node: KdcNode) {
  return Array.isArray(node.children) && node.children.length > 0;
}

export default function KdcViewerPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [categories, setCategories] = useState<KdcNode[]>([]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [query, setQuery] = useState("");

  const bffBaseUrl = resolveBffBaseUrl();

  useEffect(() => {
    const context = createRequestContext();
    setLoading(true);
    setError(null);

    fetchJson<KdcResponse>(joinUrl(bffBaseUrl, "/categories/kdc"), {
      method: "GET",
      headers: context.headers,
    })
      .then((result) => {
        if (!result.ok) {
          setError(`Failed to load categories (HTTP ${result.status})`);
          setCategories([]);
          return;
        }
        const items = Array.isArray(result.data?.categories) ? result.data.categories : [];
        setCategories(items);
        const nextExpanded: Record<string, boolean> = {};
        for (const item of items) {
          if (item.code) nextExpanded[item.code] = true;
        }
        setExpanded(nextExpanded);
      })
      .catch((err) => {
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [bffBaseUrl]);

  const filtered = useMemo(() => {
    const trimmed = query.trim().toLowerCase();
    if (!trimmed) return categories;

    const filterTree = (nodes: KdcNode[]): KdcNode[] => {
      const matched: KdcNode[] = [];
      for (const node of nodes) {
        const children = Array.isArray(node.children) ? filterTree(node.children) : [];
        const label = `${node.code ?? ""} ${node.name ?? ""}`.toLowerCase();
        if (label.includes(trimmed) || children.length > 0) {
          matched.push({ ...node, children });
        }
      }
      return matched;
    };

    return filterTree(categories);
  }, [categories, query]);

  const toggle = (code?: string) => {
    if (!code) return;
    setExpanded((prev) => ({ ...prev, [code]: !prev[code] }));
  };

  const renderNode = (node: KdcNode, level: number) => {
    const code = node.code ?? `node-${level}-${node.id ?? 0}`;
    const open = expanded[code] ?? level < 1;
    const children = Array.isArray(node.children) ? node.children : [];

    return (
      <div key={code} style={{ marginLeft: level * 16 }} className="mb-2">
        <div className="d-flex align-items-center gap-2">
          {hasChildren(node) ? (
            <Button variant="outline-secondary" size="sm" onClick={() => toggle(node.code)}>
              {open ? "-" : "+"}
            </Button>
          ) : (
            <span style={{ width: 32 }} />
          )}
          <span className="fw-semibold">{node.code ?? "---"}</span>
          <span>{node.name ?? "(no name)"}</span>
          <span className="text-muted small">depth={node.depth ?? "-"}</span>
        </div>
        {open && children.length > 0 && (
          <div className="mt-2">{children.map((child) => renderNode(child, level + 1))}</div>
        )}
      </div>
    );
  };

  return (
    <div className="d-grid gap-3">
      <Card className="shadow-sm">
        <Card.Header className="fw-semibold">KDC Tree Viewer</Card.Header>
        <Card.Body>
          <Form.Group className="mb-3" controlId="kdc-filter-query">
            <Form.Label>Filter by code/name</Form.Label>
            <Form.Control
              type="search"
              placeholder="e.g. 813, 문학"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </Form.Group>

          {loading && (
            <div className="d-flex align-items-center gap-2 text-muted">
              <Spinner animation="border" size="sm" /> Loading categories...
            </div>
          )}

          {!loading && error && <Alert variant="danger">{error}</Alert>}

          {!loading && !error && filtered.length === 0 && (
            <Alert variant="secondary" className="mb-0">
              No category matched the current filter.
            </Alert>
          )}

          {!loading && !error && filtered.length > 0 && <div>{filtered.map((node) => renderNode(node, 0))}</div>}
        </Card.Body>
      </Card>
    </div>
  );
}
