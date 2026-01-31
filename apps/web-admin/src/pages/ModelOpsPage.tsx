import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Badge, Button, Card, Col, Form, Row, Spinner, Table } from "react-bootstrap";
import { fetchJson } from "../lib/api";
import { resolveAdminApiMode, resolveBffBaseUrl, routeRequest } from "../lib/apiRouter";

type ModelInfo = {
  id: string;
  task: string;
  status?: string;
  backend?: string;
  active?: boolean;
  canary?: boolean;
  canary_weight?: number;
  artifact_uri?: string;
  loaded?: boolean;
  updated_at?: string;
};

type ModelsResponse = {
  version: string;
  trace_id: string;
  request_id: string;
  models: ModelInfo[];
};

type EvalRunReport = {
  run_id: string;
  generated_at?: string;
  baseline_id?: string;
  sets?: Record<string, Record<string, number>>;
  overall?: Record<string, number>;
};

type EvalRunsResponse = {
  version: string;
  trace_id: string;
  request_id: string;
  count: number;
  items: EvalRunReport[];
};

const DEFAULT_LIMIT = 10;
const METRIC_ORDER = ["ndcg_10", "mrr_10", "recall_100", "zero_result_rate", "latency_proxy", "query_count"];

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, "")}${path}`;
}

function formatMetric(key: string, value?: number) {
  if (value === null || value === undefined) return "-";
  if (key === "query_count") return String(value);
  if (key === "latency_proxy") return value.toFixed(2);
  return value.toFixed(4);
}

function formatDate(value?: string) {
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

export default function ModelOpsPage() {
  const apiMode = resolveAdminApiMode();
  const bffBaseUrl = resolveBffBaseUrl();

  const [models, setModels] = useState<ModelInfo[]>([]);
  const [evalRuns, setEvalRuns] = useState<EvalRunReport[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [loadingModels, setLoadingModels] = useState(false);
  const [loadingEvalRuns, setLoadingEvalRuns] = useState(false);
  const [updatingModelId, setUpdatingModelId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [canaryWeights, setCanaryWeights] = useState<Record<string, string>>({});

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

  const loadModels = useCallback(async () => {
    setLoadingModels(true);
    setErrorMessage(null);
    const { result } = await callBff<ModelsResponse>("/admin/models/registry");
    if (result.ok) {
      const nextModels = result.data.models ?? [];
      setModels(nextModels);
      const weights: Record<string, string> = {};
      nextModels.forEach((model) => {
        if (model.id) {
          weights[model.id] = model.canary_weight?.toString() ?? "0.05";
        }
      });
      setCanaryWeights(weights);
    } else {
      setErrorMessage(`Failed to load model registry (${result.status || result.statusText}).`);
    }
    setLoadingModels(false);
  }, [callBff]);

  const loadEvalRuns = useCallback(async () => {
    setLoadingEvalRuns(true);
    setErrorMessage(null);
    const params = new URLSearchParams({ limit: String(DEFAULT_LIMIT) });
    const { result } = await callBff<EvalRunsResponse>(`/admin/models/eval-runs?${params}`);
    if (result.ok) {
      const items = result.data.items ?? [];
      setEvalRuns(items);
      if (items.length > 0) {
        setSelectedRunId(items[0].run_id);
      }
    } else {
      setErrorMessage(`Failed to load eval runs (${result.status || result.statusText}).`);
    }
    setLoadingEvalRuns(false);
  }, [callBff]);

  useEffect(() => {
    loadModels();
    loadEvalRuns();
  }, [loadModels, loadEvalRuns]);

  const selectedRun = useMemo(
    () => evalRuns.find((run) => run.run_id === selectedRunId),
    [evalRuns, selectedRunId]
  );

  const handleActivate = useCallback(
    async (model: ModelInfo) => {
      if (!model.id) return;
      setUpdatingModelId(model.id);
      setErrorMessage(null);
      const { result } = await callBff<{ status: string }>("/admin/models/registry/activate", {
        method: "POST",
        body: JSON.stringify({ model_id: model.id, task: model.task }),
        headers: { "Content-Type": "application/json" },
      });
      if (!result.ok) {
        setErrorMessage(`Activate failed (${result.status || result.statusText}).`);
      } else {
        await loadModels();
      }
      setUpdatingModelId(null);
    },
    [callBff, loadModels]
  );

  const handleCanary = useCallback(
    async (model: ModelInfo, weight: number) => {
      if (!model.id) return;
      setUpdatingModelId(model.id);
      setErrorMessage(null);
      const { result } = await callBff<{ status: string }>("/admin/models/registry/canary", {
        method: "POST",
        body: JSON.stringify({ model_id: model.id, task: model.task, canary_weight: weight }),
        headers: { "Content-Type": "application/json" },
      });
      if (!result.ok) {
        setErrorMessage(`Canary update failed (${result.status || result.statusText}).`);
      } else {
        await loadModels();
      }
      setUpdatingModelId(null);
    },
    [callBff, loadModels]
  );

  return (
    <div className="d-flex flex-column gap-3">
      <Row className="g-3">
        <Col xl={12}>
          <Card>
            <Card.Header className="d-flex align-items-center justify-content-between">
              <div>
                <strong>Model Registry</strong>
                <div className="text-muted small">Active/canary routing + rollout/rollback</div>
              </div>
              <Button variant="outline-secondary" size="sm" onClick={loadModels} disabled={loadingModels}>
                {loadingModels ? <Spinner size="sm" /> : "Refresh"}
              </Button>
            </Card.Header>
            <Card.Body>
              {errorMessage ? <Alert variant="danger">{errorMessage}</Alert> : null}
              <Table responsive bordered hover size="sm" className="align-middle mb-0">
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>Task</th>
                    <th>Status</th>
                    <th>Active</th>
                    <th>Canary</th>
                    <th>Weight</th>
                    <th>Updated</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {models.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="text-center text-muted">
                        {loadingModels ? "Loading..." : "No models found"}
                      </td>
                    </tr>
                  ) : (
                    models.map((model) => (
                      <tr key={model.id}>
                        <td>
                          <div className="fw-semibold">{model.id}</div>
                          <div className="text-muted small">{model.backend || "-"}</div>
                        </td>
                        <td>{model.task || "-"}</td>
                        <td>
                          <Badge bg={model.status === "ready" ? "success" : "secondary"}>
                            {model.status || "unknown"}
                          </Badge>
                        </td>
                        <td>{model.active ? "✅" : "—"}</td>
                        <td>{model.canary ? "🟡" : "—"}</td>
                        <td style={{ minWidth: 120 }}>
                          <Form.Control
                            size="sm"
                            type="number"
                            step="0.01"
                            min="0"
                            max="1"
                            value={canaryWeights[model.id] ?? "0.05"}
                            onChange={(event) =>
                              setCanaryWeights((prev) => ({
                                ...prev,
                                [model.id]: event.target.value,
                              }))
                            }
                          />
                        </td>
                        <td>{formatDate(model.updated_at)}</td>
                        <td className="d-flex gap-2">
                          <Button
                            size="sm"
                            variant={model.active ? "secondary" : "primary"}
                            onClick={() => handleActivate(model)}
                            disabled={updatingModelId === model.id}
                          >
                            {model.active ? "Active" : "Activate"}
                          </Button>
                          <Button
                            size="sm"
                            variant="outline-warning"
                            onClick={() =>
                              handleCanary(model, Number(canaryWeights[model.id] ?? "0"))
                            }
                            disabled={updatingModelId === model.id}
                          >
                            Canary
                          </Button>
                          <Button
                            size="sm"
                            variant="outline-secondary"
                            onClick={() => handleCanary(model, 0)}
                            disabled={updatingModelId === model.id}
                          >
                            Disable
                          </Button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </Table>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Row className="g-3">
        <Col xl={12}>
          <Card>
            <Card.Header className="d-flex align-items-center justify-content-between">
              <div>
                <strong>Eval Reports</strong>
                <div className="text-muted small">Golden/Shadow/Hard sets with regression metrics</div>
              </div>
              <Button variant="outline-secondary" size="sm" onClick={loadEvalRuns} disabled={loadingEvalRuns}>
                {loadingEvalRuns ? <Spinner size="sm" /> : "Refresh"}
              </Button>
            </Card.Header>
            <Card.Body className="d-flex flex-column gap-3">
              {evalRuns.length > 0 ? (
                <Form.Select
                  value={selectedRunId}
                  onChange={(event) => setSelectedRunId(event.target.value)}
                >
                  {evalRuns.map((run) => (
                    <option key={run.run_id} value={run.run_id}>
                      {run.run_id} {run.generated_at ? `(${formatDate(run.generated_at)})` : ""}
                    </option>
                  ))}
                </Form.Select>
              ) : (
                <div className="text-muted">No eval runs found.</div>
              )}

              {selectedRun ? (
                <Table responsive bordered size="sm" className="align-middle mb-0">
                  <thead>
                    <tr>
                      <th>Set</th>
                      {METRIC_ORDER.map((metric) => (
                        <th key={metric}>{metric}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {selectedRun.sets
                      ? Object.entries(selectedRun.sets).map(([setName, metrics]) => (
                          <tr key={setName}>
                            <td className="fw-semibold">{setName}</td>
                            {METRIC_ORDER.map((metric) => (
                              <td key={metric}>{formatMetric(metric, metrics?.[metric])}</td>
                            ))}
                          </tr>
                        ))
                      : null}
                    {selectedRun.overall ? (
                      <tr>
                        <td className="fw-semibold">overall</td>
                        {METRIC_ORDER.map((metric) => (
                          <td key={metric}>{formatMetric(metric, selectedRun.overall?.[metric])}</td>
                        ))}
                      </tr>
                    ) : null}
                  </tbody>
                </Table>
              ) : null}
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
