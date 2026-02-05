import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Form,
  Row,
  Spinner,
  Tab,
  Table,
  Tabs,
} from "react-bootstrap";
import { fetchJson } from "../lib/api";
import { resolveAdminApiMode, resolveBffBaseUrl, routeRequest } from "../lib/apiRouter";

type AutocompleteSuggestion = {
  suggest_id: string;
  text: string;
  type: string;
  lang?: string | null;
  target_id?: string | null;
  target_doc_id?: string | null;
  weight?: number | null;
  ctr_7d?: number | null;
  popularity_7d?: number | null;
  is_blocked?: boolean | null;
};

type SuggestionsResponse = {
  version: string;
  trace_id: string;
  request_id: string;
  took_ms: number;
  suggestions: AutocompleteSuggestion[];
};

type UpdateRequest = {
  weight?: number;
  is_blocked?: boolean;
};

type UpdateResponse = {
  version: string;
  trace_id: string;
  request_id: string;
  suggestion: AutocompleteSuggestion;
};

type TrendItem = {
  suggest_id: string;
  text: string;
  type: string;
  lang?: string | null;
  impressions_7d?: number | null;
  clicks_7d?: number | null;
  ctr_7d?: number | null;
  popularity_7d?: number | null;
  last_seen_at?: string | null;
  updated_at?: string | null;
};

type TrendsResponse = {
  version: string;
  trace_id: string;
  request_id: string;
  metric?: string;
  count: number;
  items: TrendItem[];
};

const DEFAULT_LIMIT = 50;

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, "")}${path}`;
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined) return "-";
  return value.toFixed(3);
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

export default function OpsAutocompletePage() {
  const apiMode = resolveAdminApiMode();
  const bffBaseUrl = resolveBffBaseUrl();

  const [query, setQuery] = useState("");
  const [size, setSize] = useState(20);
  const [includeBlocked, setIncludeBlocked] = useState(false);
  const [suggestions, setSuggestions] = useState<AutocompleteSuggestion[]>([]);
  const [trends, setTrends] = useState<TrendItem[]>([]);
  const [trendMetric, setTrendMetric] = useState("ctr");
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [loadingTrends, setLoadingTrends] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [weightEdits, setWeightEdits] = useState<Record<string, string>>({});

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

  const resolvedSize = useMemo(() => {
    if (!size || Number.isNaN(size)) return 20;
    return Math.min(Math.max(size, 1), 200);
  }, [size]);

  const loadSuggestions = useCallback(async () => {
    if (!query.trim()) {
      setSuggestions([]);
      return;
    }
    setLoadingSuggestions(true);
    setErrorMessage(null);
    const params = new URLSearchParams({
      q: query.trim(),
      size: String(resolvedSize),
      include_blocked: includeBlocked ? "true" : "false",
    });
    const { result } = await callBff<SuggestionsResponse>(`/admin/ops/autocomplete/suggestions?${params}`);
    if (result.ok) {
      setSuggestions(result.data.suggestions ?? []);
      setWeightEdits({});
    } else {
      setErrorMessage(`Failed to load suggestions (${result.status || result.statusText}).`);
    }
    setLoadingSuggestions(false);
  }, [callBff, includeBlocked, query, resolvedSize]);

  const loadTrends = useCallback(async () => {
    setLoadingTrends(true);
    setErrorMessage(null);
    const params = new URLSearchParams({
      metric: trendMetric,
      limit: String(DEFAULT_LIMIT),
    });
    const { result } = await callBff<TrendsResponse>(`/admin/ops/autocomplete/trends?${params}`);
    if (result.ok) {
      setTrends(result.data.items ?? []);
    } else {
      setErrorMessage(`Failed to load trends (${result.status || result.statusText}).`);
    }
    setLoadingTrends(false);
  }, [callBff, trendMetric]);

  const handleUpdate = useCallback(
    async (suggestion: AutocompleteSuggestion, payload: UpdateRequest) => {
      if (!suggestion.suggest_id) return;
      setUpdatingId(suggestion.suggest_id);
      setErrorMessage(null);
      const { result } = await callBff<UpdateResponse>(
        `/admin/ops/autocomplete/suggestions/${suggestion.suggest_id}`,
        {
          method: "POST",
          body: JSON.stringify(payload),
          headers: { "Content-Type": "application/json" },
        }
      );
      if (result.ok) {
        const updated = result.data.suggestion;
        setSuggestions((prev) =>
          prev.map((item) => (item.suggest_id === updated.suggest_id ? updated : item))
        );
      } else {
        setErrorMessage(`Failed to update suggestion (${result.status || result.statusText}).`);
      }
      setUpdatingId(null);
    },
    [callBff]
  );

  useEffect(() => {
    loadTrends();
  }, [loadTrends]);

  return (
    <>
      <h3 className="mb-3">Autocomplete Ops</h3>
      {errorMessage ? (
        <Alert variant="danger" className="mb-3">
          {errorMessage}
        </Alert>
      ) : null}

      <Tabs defaultActiveKey="suggestions" className="mb-3">
        <Tab eventKey="suggestions" title="Suggestions">
          <Card className="shadow-sm mb-3">
            <Card.Body>
              <Form onSubmit={(event) => event.preventDefault()}>
                <Row className="g-3 align-items-end">
                  <Col lg={5}>
                    <Form.Label>Query</Form.Label>
                    <Form.Control
                      type="search"
                      value={query}
                      placeholder="Search suggestions by prefix"
                      onChange={(event) => setQuery(event.target.value)}
                    />
                  </Col>
                  <Col lg={2}>
                    <Form.Label>Size</Form.Label>
                    <Form.Control
                      type="number"
                      value={size}
                      min={1}
                      max={200}
                      onChange={(event) => setSize(Number(event.target.value))}
                    />
                  </Col>
                  <Col lg={3}>
                    <Form.Check
                      type="checkbox"
                      label="Include blocked"
                      checked={includeBlocked}
                      onChange={(event) => setIncludeBlocked(event.target.checked)}
                    />
                  </Col>
                  <Col lg={2}>
                    <Button variant="primary" onClick={loadSuggestions} disabled={loadingSuggestions}>
                      {loadingSuggestions ? <Spinner size="sm" /> : "Search"}
                    </Button>
                  </Col>
                </Row>
              </Form>
            </Card.Body>
          </Card>

          <Card className="shadow-sm">
            <Card.Body>
              {loadingSuggestions ? (
                <div className="text-muted">
                  <Spinner size="sm" /> Loading suggestions...
                </div>
              ) : (
                <Table responsive hover className="mb-0">
                  <thead>
                    <tr>
                      <th>Text</th>
                      <th>Type</th>
                      <th>Weight</th>
                      <th>CTR</th>
                      <th>Popularity</th>
                      <th>Status</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {suggestions.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="text-muted">
                          No suggestions loaded.
                        </td>
                      </tr>
                    ) : (
                      suggestions.map((suggestion) => {
                        const weightValue =
                          weightEdits[suggestion.suggest_id] ?? String(suggestion.weight ?? "");
                        const isUpdating = updatingId === suggestion.suggest_id;
                        return (
                          <tr key={suggestion.suggest_id}>
                            <td>
                              <div className="fw-semibold">{suggestion.text}</div>
                              <small className="text-muted">{suggestion.suggest_id}</small>
                            </td>
                            <td>{suggestion.type}</td>
                            <td style={{ minWidth: 120 }}>
                              <Form.Control
                                size="sm"
                                type="number"
                                value={weightValue}
                                onChange={(event) =>
                                  setWeightEdits((prev) => ({
                                    ...prev,
                                    [suggestion.suggest_id]: event.target.value,
                                  }))
                                }
                              />
                            </td>
                            <td>{formatNumber(suggestion.ctr_7d)}</td>
                            <td>{formatNumber(suggestion.popularity_7d)}</td>
                            <td>
                              {suggestion.is_blocked ? (
                                <Badge bg="danger">Blocked</Badge>
                              ) : (
                                <Badge bg="success">Active</Badge>
                              )}
                            </td>
                            <td>
                              <div className="d-flex gap-2 flex-wrap">
                                <Button
                                  size="sm"
                                  variant="outline-primary"
                                  disabled={isUpdating}
                                  onClick={() => {
                                    const parsed = Number(weightValue);
                                    if (!Number.isNaN(parsed)) {
                                      handleUpdate(suggestion, { weight: parsed });
                                    }
                                  }}
                                >
                                  Save
                                </Button>
                                <Button
                                  size="sm"
                                  variant={suggestion.is_blocked ? "outline-success" : "outline-danger"}
                                  disabled={isUpdating}
                                  onClick={() =>
                                    handleUpdate(suggestion, { is_blocked: !suggestion.is_blocked })
                                  }
                                >
                                  {suggestion.is_blocked ? "Unblock" : "Block"}
                                </Button>
                              </div>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </Table>
              )}
            </Card.Body>
          </Card>
        </Tab>
        <Tab eventKey="trends" title="Trends">
          <Card className="shadow-sm mb-3">
            <Card.Body>
              <Row className="g-3 align-items-end">
                <Col lg={3}>
                  <Form.Label>Metric</Form.Label>
                  <Form.Select value={trendMetric} onChange={(event) => setTrendMetric(event.target.value)}>
                    <option value="ctr">CTR</option>
                    <option value="popularity">Popularity</option>
                    <option value="impressions">Impressions</option>
                  </Form.Select>
                </Col>
                <Col lg={2}>
                  <Button variant="primary" onClick={loadTrends} disabled={loadingTrends}>
                    {loadingTrends ? <Spinner size="sm" /> : "Refresh"}
                  </Button>
                </Col>
              </Row>
            </Card.Body>
          </Card>

          <Card className="shadow-sm">
            <Card.Body>
              {loadingTrends ? (
                <div className="text-muted">
                  <Spinner size="sm" /> Loading trends...
                </div>
              ) : (
                <Table responsive hover className="mb-0">
                  <thead>
                    <tr>
                      <th>Text</th>
                      <th>Type</th>
                      <th>Impressions</th>
                      <th>Clicks</th>
                      <th>CTR</th>
                      <th>Popularity</th>
                      <th>Last Seen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trends.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="text-muted">
                          No trend data yet.
                        </td>
                      </tr>
                    ) : (
                      trends.map((item) => (
                        <tr key={item.suggest_id}>
                          <td>
                            <div className="fw-semibold">{item.text}</div>
                            <small className="text-muted">{item.suggest_id}</small>
                          </td>
                          <td>{item.type}</td>
                          <td>{formatNumber(item.impressions_7d)}</td>
                          <td>{formatNumber(item.clicks_7d)}</td>
                          <td>{formatNumber(item.ctr_7d)}</td>
                          <td>{formatNumber(item.popularity_7d)}</td>
                          <td>{formatDate(item.last_seen_at)}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </Table>
              )}
            </Card.Body>
          </Card>
        </Tab>
      </Tabs>
    </>
  );
}
