import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Badge, Button, Card, Col, Form, Row, Spinner, Table } from "react-bootstrap";
import { fetchJson } from "../lib/api";
import { resolveAdminApiMode, resolveBffBaseUrl, routeRequest } from "../lib/apiRouter";

type MergeGroup = {
  group_id: number;
  status: string;
  rule_version: string;
  group_key: string;
  master_material_id?: string | null;
  members?: unknown;
  updated_at?: string | null;
};

type MergeGroupListResponse = {
  version: string;
  trace_id: string;
  request_id: string;
  count: number;
  items: MergeGroup[];
};

type MergeGroupResolveRequest = {
  master_material_id: string;
  status?: string;
};

type AgentAlias = {
  alias_id: number;
  alias_name: string;
  canonical_name: string;
  canonical_agent_id?: string | null;
  status: string;
  updated_at?: string | null;
};

type AgentAliasListResponse = {
  version: string;
  trace_id: string;
  request_id: string;
  count: number;
  items: AgentAlias[];
};

type AgentAliasUpsertRequest = {
  alias_name: string;
  canonical_name: string;
  canonical_agent_id?: string | null;
};

type AgentAliasResponse = {
  version: string;
  trace_id: string;
  request_id: string;
  alias: AgentAlias;
};

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, "")}${path}`;
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export default function AuthorityOpsPage() {
  const apiMode = resolveAdminApiMode();
  const bffBaseUrl = resolveBffBaseUrl();

  const [mergeGroups, setMergeGroups] = useState<MergeGroup[]>([]);
  const [aliasEntries, setAliasEntries] = useState<AgentAlias[]>([]);
  const [loadingMerge, setLoadingMerge] = useState(false);
  const [loadingAlias, setLoadingAlias] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [mergeStatus, setMergeStatus] = useState("");
  const [aliasQuery, setAliasQuery] = useState("");
  const [aliasName, setAliasName] = useState("");
  const [canonicalName, setCanonicalName] = useState("");
  const [canonicalAgentId, setCanonicalAgentId] = useState("");

  const callBff = useCallback(
    async <T,>(path: string, init?: RequestInit) => {
      return routeRequest<T>({
        route: path,
        mode: apiMode,
        allowFallback: false,
        bff: (context) =>
          fetchJson<T>(joinUrl(bffBaseUrl, path), {
            ...init,
            headers: { ...context.headers, ...(init?.headers ?? {}) },
          }),
        direct: (context) =>
          fetchJson<T>(joinUrl(bffBaseUrl, path), {
            ...init,
            headers: { ...context.headers, ...(init?.headers ?? {}) },
          }),
      });
    },
    [apiMode, bffBaseUrl]
  );

  const loadMergeGroups = useCallback(async () => {
    setLoadingMerge(true);
    setErrorMessage(null);
    const params = new URLSearchParams();
    params.set("limit", "50");
    if (mergeStatus.trim()) params.set("status", mergeStatus.trim());
    const { result } = await callBff<MergeGroupListResponse>(`/admin/authority/merge-groups?${params}`);
    if (result.ok) {
      setMergeGroups(result.data.items ?? []);
    } else {
      setErrorMessage(`Failed to load merge groups (${result.status || result.statusText}).`);
    }
    setLoadingMerge(false);
  }, [callBff, mergeStatus]);

  const loadAliases = useCallback(async () => {
    setLoadingAlias(true);
    setErrorMessage(null);
    const params = new URLSearchParams();
    params.set("limit", "100");
    if (aliasQuery.trim()) params.set("q", aliasQuery.trim());
    const { result } = await callBff<AgentAliasListResponse>(`/admin/authority/agent-aliases?${params}`);
    if (result.ok) {
      setAliasEntries(result.data.items ?? []);
    } else {
      setErrorMessage(`Failed to load aliases (${result.status || result.statusText}).`);
    }
    setLoadingAlias(false);
  }, [aliasQuery, callBff]);

  const handleResolveGroup = useCallback(
    async (group: MergeGroup) => {
      const master = window.prompt("Master material_id", group.master_material_id ?? "");
      if (!master) return;
      const payload: MergeGroupResolveRequest = { master_material_id: master };
      const { result } = await callBff<unknown>(`/admin/authority/merge-groups/${group.group_id}/resolve`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (result.ok) {
        loadMergeGroups();
      } else {
        setErrorMessage(`Failed to resolve group (${result.status || result.statusText}).`);
      }
    },
    [callBff, loadMergeGroups]
  );

  const handleUpsertAlias = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      if (!aliasName.trim() || !canonicalName.trim()) return;
      const payload: AgentAliasUpsertRequest = {
        alias_name: aliasName.trim(),
        canonical_name: canonicalName.trim(),
        canonical_agent_id: canonicalAgentId.trim() || undefined,
      };
      const { result } = await callBff<AgentAliasResponse>(`/admin/authority/agent-aliases`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (result.ok) {
        setAliasName("");
        setCanonicalName("");
        setCanonicalAgentId("");
        loadAliases();
      } else {
        setErrorMessage(`Failed to upsert alias (${result.status || result.statusText}).`);
      }
    },
    [aliasName, canonicalAgentId, canonicalName, callBff, loadAliases]
  );

  const handleDeleteAlias = useCallback(
    async (alias: AgentAlias) => {
      if (!window.confirm(`Delete alias "${alias.alias_name}"?`)) return;
      const { result } = await callBff<AgentAliasResponse>(`/admin/authority/agent-aliases/${alias.alias_id}`, {
        method: "DELETE",
      });
      if (result.ok) {
        loadAliases();
      } else {
        setErrorMessage(`Failed to delete alias (${result.status || result.statusText}).`);
      }
    },
    [callBff, loadAliases]
  );

  useEffect(() => {
    loadMergeGroups();
  }, [loadMergeGroups]);

  useEffect(() => {
    loadAliases();
  }, [loadAliases]);

  const mergeCount = useMemo(() => mergeGroups.length, [mergeGroups]);
  const aliasCount = useMemo(() => aliasEntries.length, [aliasEntries]);

  return (
    <div className="d-flex flex-column gap-4">
      <div>
        <h2 className="mb-1">Authority Ops</h2>
        <p className="text-muted mb-0">Manage canonical material groups and author alias dictionaries.</p>
      </div>

      {errorMessage ? <Alert variant="danger">{errorMessage}</Alert> : null}

      <Card>
        <Card.Header className="d-flex justify-content-between align-items-center">
          <div>
            <strong>Merge Groups</strong>
            <div className="text-muted small">Material canonical selection queue</div>
          </div>
          <div className="d-flex align-items-center gap-2">
            <Badge bg="secondary">{mergeCount} groups</Badge>
            <Button size="sm" variant="outline-primary" onClick={loadMergeGroups} disabled={loadingMerge}>
              Refresh
            </Button>
          </div>
        </Card.Header>
        <Card.Body>
          <Form className="mb-3">
            <Row className="g-2 align-items-end">
              <Col md={3}>
                <Form.Label>Status</Form.Label>
                <Form.Select value={mergeStatus} onChange={(e) => setMergeStatus(e.target.value)}>
                  <option value="">All</option>
                  <option value="OPEN">OPEN</option>
                  <option value="RESOLVED">RESOLVED</option>
                </Form.Select>
              </Col>
              <Col>
                <Button variant="primary" onClick={loadMergeGroups} disabled={loadingMerge}>
                  {loadingMerge ? <Spinner animation="border" size="sm" /> : "Apply"}
                </Button>
              </Col>
            </Row>
          </Form>

          {loadingMerge ? (
            <div className="text-center py-4">
              <Spinner animation="border" />
            </div>
          ) : (
            <Table hover responsive size="sm">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Status</th>
                  <th>Rule</th>
                  <th>Master</th>
                  <th>Members</th>
                  <th>Updated</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {mergeGroups.map((group) => (
                  <tr key={group.group_id}>
                    <td>{group.group_id}</td>
                    <td>
                      <Badge bg={group.status === "RESOLVED" ? "success" : "warning"}>{group.status}</Badge>
                    </td>
                    <td>{group.rule_version}</td>
                    <td>{group.master_material_id ?? "-"}</td>
                    <td>
                      <code className="small text-muted">
                        {group.members ? JSON.stringify(group.members).slice(0, 120) : "-"}
                      </code>
                    </td>
                    <td>{formatDate(group.updated_at)}</td>
                    <td className="text-end">
                      <Button size="sm" variant="outline-secondary" onClick={() => handleResolveGroup(group)}>
                        Resolve
                      </Button>
                    </td>
                  </tr>
                ))}
                {mergeGroups.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center text-muted">
                      No groups found.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </Table>
          )}
        </Card.Body>
      </Card>

      <Card>
        <Card.Header className="d-flex justify-content-between align-items-center">
          <div>
            <strong>Author Alias Dictionary</strong>
            <div className="text-muted small">Normalize agent name variants</div>
          </div>
          <div className="d-flex align-items-center gap-2">
            <Badge bg="secondary">{aliasCount} aliases</Badge>
            <Button size="sm" variant="outline-primary" onClick={loadAliases} disabled={loadingAlias}>
              Refresh
            </Button>
          </div>
        </Card.Header>
        <Card.Body>
          <Form className="mb-3" onSubmit={handleUpsertAlias}>
            <Row className="g-2 align-items-end">
              <Col md={3}>
                <Form.Label>Alias</Form.Label>
                <Form.Control value={aliasName} onChange={(e) => setAliasName(e.target.value)} />
              </Col>
              <Col md={3}>
                <Form.Label>Canonical</Form.Label>
                <Form.Control value={canonicalName} onChange={(e) => setCanonicalName(e.target.value)} />
              </Col>
              <Col md={3}>
                <Form.Label>Canonical Agent ID</Form.Label>
                <Form.Control value={canonicalAgentId} onChange={(e) => setCanonicalAgentId(e.target.value)} />
              </Col>
              <Col md={2}>
                <Button variant="primary" type="submit">
                  Upsert
                </Button>
              </Col>
            </Row>
          </Form>

          <Form className="mb-3">
            <Row className="g-2 align-items-end">
              <Col md={4}>
                <Form.Label>Search alias</Form.Label>
                <Form.Control value={aliasQuery} onChange={(e) => setAliasQuery(e.target.value)} />
              </Col>
              <Col>
                <Button variant="outline-secondary" onClick={loadAliases} disabled={loadingAlias}>
                  Filter
                </Button>
              </Col>
            </Row>
          </Form>

          {loadingAlias ? (
            <div className="text-center py-4">
              <Spinner animation="border" />
            </div>
          ) : (
            <Table hover responsive size="sm">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Alias</th>
                  <th>Canonical</th>
                  <th>Agent ID</th>
                  <th>Status</th>
                  <th>Updated</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {aliasEntries.map((alias) => (
                  <tr key={alias.alias_id}>
                    <td>{alias.alias_id}</td>
                    <td>{alias.alias_name}</td>
                    <td>{alias.canonical_name}</td>
                    <td>{alias.canonical_agent_id ?? "-"}</td>
                    <td>
                      <Badge bg={alias.status === "ACTIVE" ? "success" : "secondary"}>{alias.status}</Badge>
                    </td>
                    <td>{formatDate(alias.updated_at)}</td>
                    <td className="text-end">
                      <Button size="sm" variant="outline-danger" onClick={() => handleDeleteAlias(alias)}>
                        Delete
                      </Button>
                    </td>
                  </tr>
                ))}
                {aliasEntries.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center text-muted">
                      No aliases found.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </Table>
          )}
        </Card.Body>
      </Card>
    </div>
  );
}
