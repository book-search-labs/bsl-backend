import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Badge, Button, Card, Col, Form, Row, Spinner, Table } from "react-bootstrap";
import { fetchJson } from "../lib/api";
import { resolveAdminApiMode, resolveBffBaseUrl, routeRequest } from "../lib/apiRouter";

type CheckoutStep = {
  step_name: string;
  status: string;
  step_category: string;
  recovery_policy: string;
  idempotency_key?: string;
  retry_count: number;
  max_retry_count: number;
  next_retry_at?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  request_payload?: unknown;
  response_payload?: unknown;
  started_at?: string | null;
  completed_at?: string | null;
  updated_at?: string | null;
};

type CheckoutSummary = {
  checkout_id: number;
  checkout_key: string;
  user_id: string;
  status: string;
  current_step?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  created_at?: string;
  updated_at?: string;
  steps?: CheckoutStep[];
  failed_steps?: CheckoutStep[];
  outbox_event_count?: number;
};

type OutboxEvent = {
  event_type: string;
  event_key: string;
  status: string;
  payload?: unknown;
  retry_count?: number;
  created_at?: string;
  updated_at?: string;
  published_at?: string | null;
};

type CheckoutDetail = CheckoutSummary & {
  request_payload?: unknown;
  context_payload?: unknown;
  steps: CheckoutStep[];
  outbox_events: OutboxEvent[];
};

type ActionResponse = {
  checkout_id: number;
  step_name?: string;
  before_status?: string;
  after_status?: string;
  status?: string;
  action?: string;
  reason?: string;
  operator_id?: string;
};

const STATUS_OPTIONS = [
  "",
  "PENDING",
  "PROCESSING",
  "SUCCEEDED",
  "FAILED_RETRYING",
  "MANUAL_REVIEW_REQUIRED",
  "CANCELLING",
  "CANCELLED",
  "CANCEL_FAILED",
];

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, "")}${path}`;
}

function statusVariant(status: string) {
  if (status === "SUCCEEDED" || status === "COMPENSATED" || status === "CANCELLED") return "success";
  if (status === "FAILED_RETRYING" || status === "UNKNOWN" || status === "PROCESSING" || status === "COMPENSATING") {
    return "warning";
  }
  if (status === "MANUAL_REVIEW_REQUIRED" || status === "CANCEL_FAILED" || status === "FAILED_PERMANENT") return "danger";
  return "secondary";
}

function formatJson(value: unknown) {
  if (value == null) return "-";
  return JSON.stringify(value, null, 2);
}

export default function CheckoutSagaOpsPage() {
  const apiMode = resolveAdminApiMode();
  const bffBaseUrl = resolveBffBaseUrl();
  const [statusFilter, setStatusFilter] = useState("MANUAL_REVIEW_REQUIRED");
  const [limit, setLimit] = useState("50");
  const [items, setItems] = useState<CheckoutSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<CheckoutDetail | null>(null);
  const [operatorReason, setOperatorReason] = useState("");
  const [approvalId, setApprovalId] = useState("");
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);
  const [lastAction, setLastAction] = useState<ActionResponse | null>(null);

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

  const listPath = useMemo(() => {
    const params = new URLSearchParams();
    params.set("limit", limit || "50");
    if (statusFilter.trim()) params.set("status", statusFilter.trim());
    return `/admin/checkouts?${params.toString()}`;
  }, [limit, statusFilter]);

  const loadList = useCallback(async () => {
    setLoading(true);
    setErrorMessage(null);
    const { result } = await callBff<{ items: CheckoutSummary[] }>(listPath);
    if (result.ok) {
      setItems(result.data.items ?? []);
    } else {
      setErrorMessage(`Failed to load checkout sagas (${result.status || result.statusText})`);
    }
    setLoading(false);
  }, [callBff, listPath]);

  const loadDetail = useCallback(
    async (checkoutId: number) => {
      setDetailLoading(true);
      setErrorMessage(null);
      const { result } = await callBff<CheckoutDetail>(`/admin/checkouts/${checkoutId}`);
      if (result.ok) {
        setDetail(result.data);
      } else {
        setErrorMessage(`Failed to load checkout #${checkoutId}`);
      }
      setDetailLoading(false);
    },
    [callBff]
  );

  useEffect(() => {
    loadList();
  }, [loadList]);

  useEffect(() => {
    if (selectedId != null) loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  const selectedHasPivotSuccess = useMemo(() => {
    return detail?.steps?.some((step) => step.step_category === "PIVOT" && step.status === "SUCCEEDED") ?? false;
  }, [detail]);

  const actionBody = () => {
    const reason = operatorReason.trim();
    if (!reason) {
      setErrorMessage("Operator reason is required.");
      return null;
    }
    const body: Record<string, string> = {
      reason,
      operator_id: localStorage.getItem("bsl.adminId") ?? "1",
    };
    if (approvalId.trim()) body.approval_id = approvalId.trim();
    return body;
  };

  const runAction = async (path: string, successMessage: string, requireApproval = false) => {
    setErrorMessage(null);
    setInfoMessage(null);
    setLastAction(null);
    if (requireApproval && !approvalId.trim()) {
      setErrorMessage("Pivot/reversal action requires approval_id.");
      return;
    }
    const body = actionBody();
    if (!body) return;
    const { result } = await callBff<ActionResponse>(path, {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (!result.ok) {
      setErrorMessage(`${successMessage} failed`);
      return;
    }
    setLastAction(result.data);
    setInfoMessage(successMessage);
    await loadList();
    if (selectedId != null) await loadDetail(selectedId);
  };

  const retryStep = (step: CheckoutStep) => {
    if (!detail) return;
    runAction(
      `/admin/checkouts/${detail.checkout_id}/steps/${step.step_name}/retry`,
      `Retry scheduled for ${step.step_name}`
    );
  };

  const reconcileStep = (step: CheckoutStep) => {
    if (!detail) return;
    runAction(
      `/admin/checkouts/${detail.checkout_id}/steps/${step.step_name}/reconcile`,
      `Reconciliation scheduled for ${step.step_name}`
    );
  };

  const cancelCheckout = () => {
    if (!detail) return;
    runAction(
      `/admin/checkouts/${detail.checkout_id}/cancel`,
      `Cancel requested for checkout #${detail.checkout_id}`,
      selectedHasPivotSuccess
    );
  };

  const renderStepAction = (step: CheckoutStep) => {
    if (step.status === "FAILED_RETRYING" || step.status === "MANUAL_REVIEW_REQUIRED") {
      return (
        <Button size="sm" variant="outline-primary" onClick={() => retryStep(step)}>
          Retry
        </Button>
      );
    }
    if (step.status === "UNKNOWN") {
      return (
        <Button size="sm" variant="outline-warning" onClick={() => reconcileStep(step)}>
          Reconcile
        </Button>
      );
    }
    return <span className="text-muted">-</span>;
  };

  return (
    <div>
      <div className="d-flex align-items-center justify-content-between mb-3">
        <div>
          <h2 className="mb-1">Checkout Saga Ops</h2>
          <p className="text-muted mb-0">Inspect saga state, retry failed steps, and trigger explicit compensation.</p>
        </div>
        <Button variant="outline-secondary" onClick={loadList} disabled={loading}>
          {loading ? <Spinner size="sm" /> : <i className="bi bi-arrow-clockwise me-1" />}
          Refresh
        </Button>
      </div>

      {errorMessage ? <Alert variant="danger">{errorMessage}</Alert> : null}
      {infoMessage ? <Alert variant="success">{infoMessage}</Alert> : null}
      {lastAction ? (
        <Alert variant="info">
          Action result: {lastAction.step_name ?? "checkout"} {lastAction.before_status ?? "-"} →{" "}
          {lastAction.after_status ?? lastAction.status ?? "-"}
        </Alert>
      ) : null}

      <Row className="g-3">
        <Col lg={5}>
          <Card>
            <Card.Header className="d-flex align-items-center justify-content-between">
              <strong>Sagas</strong>
              <Badge bg="secondary">{items.length}</Badge>
            </Card.Header>
            <Card.Body>
              <Row className="g-2 mb-3">
                <Col md={7}>
                  <Form.Label>Status</Form.Label>
                  <Form.Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                    {STATUS_OPTIONS.map((status) => (
                      <option key={status || "ALL"} value={status}>
                        {status || "ALL"}
                      </option>
                    ))}
                  </Form.Select>
                </Col>
                <Col md={5}>
                  <Form.Label>Limit</Form.Label>
                  <Form.Control value={limit} onChange={(e) => setLimit(e.target.value)} />
                </Col>
              </Row>

              <div className="table-responsive">
                <Table hover size="sm" className="align-middle">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Status</th>
                      <th>Current</th>
                      <th>Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((item) => (
                      <tr
                        key={item.checkout_id}
                        className={selectedId === item.checkout_id ? "table-active" : ""}
                        role="button"
                        onClick={() => setSelectedId(item.checkout_id)}
                      >
                        <td>
                          <div className="fw-semibold">#{item.checkout_id}</div>
                          <div className="text-muted small">{item.checkout_key}</div>
                        </td>
                        <td>
                          <Badge bg={statusVariant(item.status)}>{item.status}</Badge>
                          {item.failed_steps?.length ? (
                            <div className="small text-danger mt-1">{item.failed_steps.length} attention</div>
                          ) : null}
                        </td>
                        <td>{item.current_step ?? "-"}</td>
                        <td className="small text-muted">{item.updated_at ?? "-"}</td>
                      </tr>
                    ))}
                    {!items.length ? (
                      <tr>
                        <td colSpan={4} className="text-center text-muted py-4">
                          No checkout sagas.
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </Table>
              </div>
            </Card.Body>
          </Card>
        </Col>

        <Col lg={7}>
          <Card>
            <Card.Header className="d-flex align-items-center justify-content-between">
              <strong>Detail</strong>
              {detail ? <Badge bg={statusVariant(detail.status)}>{detail.status}</Badge> : null}
            </Card.Header>
            <Card.Body>
              {!selectedId ? <div className="text-muted">Select a checkout saga.</div> : null}
              {detailLoading ? <Spinner /> : null}
              {detail && !detailLoading ? (
                <>
                  <Row className="g-2 mb-3">
                    <Col md={4}>
                      <div className="text-muted small">Checkout</div>
                      <div className="fw-semibold">#{detail.checkout_id}</div>
                    </Col>
                    <Col md={4}>
                      <div className="text-muted small">User</div>
                      <div>{detail.user_id}</div>
                    </Col>
                    <Col md={4}>
                      <div className="text-muted small">Current Step</div>
                      <div>{detail.current_step ?? "-"}</div>
                    </Col>
                  </Row>

                  <Card className="mb-3">
                    <Card.Body>
                      <Row className="g-2 align-items-end">
                        <Col md={7}>
                          <Form.Label>Operator reason</Form.Label>
                          <Form.Control
                            value={operatorReason}
                            onChange={(e) => setOperatorReason(e.target.value)}
                            placeholder="Required for retry/reconcile/cancel"
                          />
                        </Col>
                        <Col md={3}>
                          <Form.Label>Approval ID</Form.Label>
                          <Form.Control
                            value={approvalId}
                            onChange={(e) => setApprovalId(e.target.value)}
                            placeholder="Required for pivot"
                          />
                        </Col>
                        <Col md={2}>
                          <Button variant="outline-danger" className="w-100" onClick={cancelCheckout}>
                            Cancel
                          </Button>
                        </Col>
                      </Row>
                      {selectedHasPivotSuccess ? (
                        <div className="text-danger small mt-2">
                          Pivot step already succeeded. Cancel requires explicit approval_id.
                        </div>
                      ) : null}
                    </Card.Body>
                  </Card>

                  <h5>Step timeline</h5>
                  <div className="table-responsive mb-3">
                    <Table size="sm" className="align-middle">
                      <thead>
                        <tr>
                          <th>Step</th>
                          <th>Status</th>
                          <th>Category</th>
                          <th>Recovery</th>
                          <th>Retry</th>
                          <th>Error</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.steps.map((step) => (
                          <tr key={step.step_name}>
                            <td className="fw-semibold">{step.step_name}</td>
                            <td>
                              <Badge bg={statusVariant(step.status)}>{step.status}</Badge>
                            </td>
                            <td>{step.step_category}</td>
                            <td>{step.recovery_policy}</td>
                            <td>
                              {step.retry_count}/{step.max_retry_count}
                              {step.next_retry_at ? <div className="small text-muted">{step.next_retry_at}</div> : null}
                            </td>
                            <td className="small">
                              {step.error_code ? <div className="text-danger">{step.error_code}</div> : "-"}
                              {step.error_message ? <div className="text-muted">{step.error_message}</div> : null}
                            </td>
                            <td>{renderStepAction(step)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </div>

                  <Row className="g-3">
                    <Col md={6}>
                      <h5>Request payload</h5>
                      <pre className="bg-light border rounded p-2 small text-start overflow-auto" style={{ maxHeight: 260 }}>
                        {formatJson(detail.request_payload)}
                      </pre>
                    </Col>
                    <Col md={6}>
                      <h5>Context payload</h5>
                      <pre className="bg-light border rounded p-2 small text-start overflow-auto" style={{ maxHeight: 260 }}>
                        {formatJson(detail.context_payload)}
                      </pre>
                    </Col>
                  </Row>

                  <h5 className="mt-3">Outbox events</h5>
                  <div className="table-responsive">
                    <Table size="sm" className="align-middle">
                      <thead>
                        <tr>
                          <th>Type</th>
                          <th>Status</th>
                          <th>Retry</th>
                          <th>Key</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.outbox_events.map((event) => (
                          <tr key={event.event_key}>
                            <td>{event.event_type}</td>
                            <td>
                              <Badge bg={statusVariant(event.status)}>{event.status}</Badge>
                            </td>
                            <td>{event.retry_count ?? 0}</td>
                            <td className="small text-muted">{event.event_key}</td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </div>
                </>
              ) : null}
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
