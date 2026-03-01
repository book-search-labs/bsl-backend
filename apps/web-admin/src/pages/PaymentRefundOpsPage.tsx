import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Badge, Button, Card, Col, Form, Row, Spinner, Table } from "react-bootstrap";
import { fetchJson } from "../lib/api";
import { resolveAdminApiMode, resolveBffBaseUrl, routeRequest } from "../lib/apiRouter";

type Payment = {
  payment_id: number;
  order_id: number;
  status: string;
  amount: number;
  currency: string;
  provider?: string;
  method?: string;
  provider_payment_id?: string | null;
  checkout_session_id?: string | null;
  checkout_url?: string | null;
  failure_reason?: string | null;
  created_at?: string;
  updated_at?: string;
  captured_at?: string | null;
};

type WebhookEvent = {
  webhook_event_id: number;
  provider: string;
  event_id: string;
  payment_id: number | null;
  signature_ok: boolean;
  received_at?: string;
  processed_at?: string | null;
  process_status: string;
  error_message?: string | null;
  payload_json?: string | null;
  retry_count?: number | null;
  last_retry_at?: string | null;
  next_retry_at?: string | null;
};

type Refund = {
  refund_id: number;
  order_id: number;
  status: string;
  amount: number;
  reason_code?: string;
};

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, "")}${path}`;
}

export default function PaymentRefundOpsPage() {
  const apiMode = resolveAdminApiMode();
  const bffBaseUrl = resolveBffBaseUrl();

  const [payments, setPayments] = useState<Payment[]>([]);
  const [refunds, setRefunds] = useState<Refund[]>([]);
  const [selectedPaymentId, setSelectedPaymentId] = useState<number | null>(null);
  const [selectedPayment, setSelectedPayment] = useState<Payment | null>(null);
  const [webhookEvents, setWebhookEvents] = useState<WebhookEvent[]>([]);
  const [paymentStatusFilter, setPaymentStatusFilter] = useState("");
  const [providerFilter, setProviderFilter] = useState("");
  const [fromDateFilter, setFromDateFilter] = useState("");
  const [toDateFilter, setToDateFilter] = useState("");
  const [limit, setLimit] = useState("50");
  const [webhookQueueStatusFilter, setWebhookQueueStatusFilter] = useState("FAILED");
  const [webhookQueueProviderFilter, setWebhookQueueProviderFilter] = useState("");
  const [webhookQueueLimit, setWebhookQueueLimit] = useState("50");
  const [webhookQueueEvents, setWebhookQueueEvents] = useState<WebhookEvent[]>([]);
  const [loadingPaymentDetail, setLoadingPaymentDetail] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

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

  const paymentsPath = useMemo(() => {
    const params = new URLSearchParams();
    params.set("limit", limit || "50");
    if (paymentStatusFilter.trim()) {
      params.set("status", paymentStatusFilter.trim());
    }
    if (providerFilter.trim()) {
      params.set("provider", providerFilter.trim());
    }
    if (fromDateFilter.trim()) {
      params.set("from", fromDateFilter.trim());
    }
    if (toDateFilter.trim()) {
      params.set("to", toDateFilter.trim());
    }
    return `/admin/payments?${params.toString()}`;
  }, [limit, paymentStatusFilter, providerFilter, fromDateFilter, toDateFilter]);

  const loadPayments = useCallback(async () => {
    const paymentsResult = await callBff<{ items: Payment[] }>(paymentsPath);
    if (paymentsResult.result.ok) {
      setPayments(paymentsResult.result.data.items ?? []);
    } else {
      setErrorMessage("Failed to load payments");
    }
  }, [callBff, paymentsPath]);

  const loadRefunds = useCallback(async () => {
    const refundsResult = await callBff<{ items: Refund[] }>("/admin/refunds?limit=50");
    if (refundsResult.result.ok) {
      setRefunds(refundsResult.result.data.items ?? []);
    } else {
      setErrorMessage("Failed to load refunds");
    }
  }, [callBff]);

  const loadWebhookQueue = useCallback(async () => {
    const params = new URLSearchParams();
    params.set("limit", webhookQueueLimit || "50");
    if (webhookQueueStatusFilter.trim()) {
      params.set("status", webhookQueueStatusFilter.trim());
    }
    if (webhookQueueProviderFilter.trim()) {
      params.set("provider", webhookQueueProviderFilter.trim());
    }
    const result = await callBff<{ items: WebhookEvent[] }>(`/admin/payments/webhook-events?${params.toString()}`);
    if (result.result.ok) {
      setWebhookQueueEvents(result.result.data.items ?? []);
    } else {
      setErrorMessage("Failed to load webhook queue");
    }
  }, [callBff, webhookQueueLimit, webhookQueueProviderFilter, webhookQueueStatusFilter]);

  const loadPaymentDetail = useCallback(
    async (paymentId: number) => {
      setLoadingPaymentDetail(true);
      const paymentResult = await callBff<{ payment: Payment }>(`/admin/payments/${paymentId}`);
      if (paymentResult.result.ok) {
        setSelectedPayment(paymentResult.result.data.payment ?? null);
      } else {
        setErrorMessage("Failed to load payment detail");
      }

      const eventsResult = await callBff<{ items: WebhookEvent[] }>(
        `/admin/payments/${paymentId}/webhook-events?limit=100`
      );
      if (eventsResult.result.ok) {
        setWebhookEvents(eventsResult.result.data.items ?? []);
      } else {
        setErrorMessage("Failed to load webhook events");
      }
      setLoadingPaymentDetail(false);
    },
    [callBff]
  );

  useEffect(() => {
    loadPayments();
    loadRefunds();
    loadWebhookQueue();
  }, [loadPayments, loadRefunds, loadWebhookQueue]);

  useEffect(() => {
    if (selectedPaymentId != null) {
      loadPaymentDetail(selectedPaymentId);
    }
  }, [selectedPaymentId, loadPaymentDetail]);

  const refreshAll = async () => {
    setErrorMessage(null);
    setInfoMessage(null);
    await loadPayments();
    await loadRefunds();
    await loadWebhookQueue();
    if (selectedPaymentId != null) {
      await loadPaymentDetail(selectedPaymentId);
    }
  };

  const handleCancelPayment = async (paymentId: number) => {
    const { result } = await callBff(`/admin/payments/${paymentId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason: "ops_cancel" }),
    });
    if (!result.ok) {
      setErrorMessage("Failed to cancel payment");
      return;
    }
    setInfoMessage(`Canceled payment #${paymentId}`);
    await loadPayments();
    if (selectedPaymentId === paymentId) {
      await loadPaymentDetail(paymentId);
    }
  };

  const handleRetryWebhookEvent = async (eventId: string) => {
    const { result } = await callBff<{ status: string; event_id: string }>(
      `/admin/payments/webhook-events/${encodeURIComponent(eventId)}/retry`,
      { method: "POST" }
    );
    if (!result.ok) {
      setErrorMessage("Failed to retry webhook event");
      return;
    }
    setInfoMessage(`Retried webhook event ${eventId}`);
    await loadWebhookQueue();
    if (selectedPaymentId != null) {
      await loadPaymentDetail(selectedPaymentId);
    }
  };

  const handleApproveRefund = async (refundId: number) => {
    const { result } = await callBff(`/admin/refunds/${refundId}/approve`, { method: "POST" });
    if (!result.ok) {
      setErrorMessage("Failed to approve refund");
      return;
    }
    setInfoMessage(`Approved refund #${refundId}`);
    loadRefunds();
  };

  const handleProcessRefund = async (refundId: number) => {
    const { result } = await callBff(`/admin/refunds/${refundId}/process`, {
      method: "POST",
      body: JSON.stringify({ result: "SUCCESS" }),
    });
    if (!result.ok) {
      setErrorMessage("Failed to process refund");
      return;
    }
    setInfoMessage(`Processed refund #${refundId}`);
    loadRefunds();
  };

  const renderStatusBadge = (status: string) => {
    if (status === "CAPTURED" || status === "REFUNDED" || status === "PROCESSED") {
      return <Badge bg="success">{status}</Badge>;
    }
    if (status === "FAILED" || status === "ERROR") {
      return <Badge bg="danger">{status}</Badge>;
    }
    if (status === "PROCESSING" || status === "RECEIVED") {
      return <Badge bg="warning">{status}</Badge>;
    }
    return <Badge bg="secondary">{status}</Badge>;
  };

  return (
    <div className="d-flex flex-column gap-4">
      {errorMessage ? <Alert variant="danger">{errorMessage}</Alert> : null}
      {infoMessage ? <Alert variant="success">{infoMessage}</Alert> : null}

      <Card className="p-3">
        <h4 className="mb-3">Payment Monitor Filters</h4>
        <Row className="g-2 align-items-end">
          <Col md={3}>
            <Form.Label>Status</Form.Label>
            <Form.Control
              value={paymentStatusFilter}
              onChange={(event) => setPaymentStatusFilter(event.target.value)}
              placeholder="PROCESSING, CAPTURED, FAILED..."
            />
          </Col>
          <Col md={3}>
            <Form.Label>Provider</Form.Label>
            <Form.Control
              value={providerFilter}
              onChange={(event) => setProviderFilter(event.target.value)}
              placeholder="MOCK, LOCAL_SIM..."
            />
          </Col>
          <Col md={2}>
            <Form.Label>Limit</Form.Label>
            <Form.Control value={limit} onChange={(event) => setLimit(event.target.value)} />
          </Col>
          <Col md={2}>
            <Form.Label>From</Form.Label>
            <Form.Control
              type="date"
              value={fromDateFilter}
              onChange={(event) => setFromDateFilter(event.target.value)}
            />
          </Col>
          <Col md={2}>
            <Form.Label>To</Form.Label>
            <Form.Control type="date" value={toDateFilter} onChange={(event) => setToDateFilter(event.target.value)} />
          </Col>
          <Col md={12} className="d-flex gap-2 mt-2">
            <Button onClick={refreshAll}>Refresh</Button>
            <Button
              variant="outline-secondary"
              onClick={() => {
                setPaymentStatusFilter("");
                setProviderFilter("");
                setLimit("50");
                setFromDateFilter("");
                setToDateFilter("");
              }}
            >
              Reset
            </Button>
          </Col>
        </Row>
      </Card>

      <Card className="p-3">
        <div className="d-flex align-items-center justify-content-between mb-3">
          <h4 className="mb-0">Webhook Queue</h4>
          <Button variant="outline-primary" onClick={loadWebhookQueue}>
            Refresh Queue
          </Button>
        </div>
        <Row className="g-2 align-items-end mb-3">
          <Col md={2}>
            <Form.Label>Status</Form.Label>
            <Form.Control
              value={webhookQueueStatusFilter}
              onChange={(event) => setWebhookQueueStatusFilter(event.target.value)}
              placeholder="FAILED, RECEIVED..."
            />
          </Col>
          <Col md={2}>
            <Form.Label>Provider</Form.Label>
            <Form.Control
              value={webhookQueueProviderFilter}
              onChange={(event) => setWebhookQueueProviderFilter(event.target.value)}
              placeholder="MOCK, LOCAL_SIM..."
            />
          </Col>
          <Col md={2}>
            <Form.Label>Limit</Form.Label>
            <Form.Control value={webhookQueueLimit} onChange={(event) => setWebhookQueueLimit(event.target.value)} />
          </Col>
          <Col md={6} className="d-flex gap-2">
            <Button onClick={loadWebhookQueue}>Apply</Button>
            <Button
              variant="outline-secondary"
              onClick={() => {
                setWebhookQueueStatusFilter("FAILED");
                setWebhookQueueProviderFilter("");
                setWebhookQueueLimit("50");
              }}
            >
              Reset
            </Button>
          </Col>
        </Row>
        <Table bordered hover size="sm" className="mb-0">
          <thead>
            <tr>
              <th>ID</th>
              <th>Event ID</th>
              <th>Payment</th>
              <th>Status</th>
              <th>Retry</th>
              <th>Received</th>
              <th>Error</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {webhookQueueEvents.length === 0 ? (
              <tr>
                <td colSpan={8} className="text-center text-muted">
                  No webhook queue events
                </td>
              </tr>
            ) : (
              webhookQueueEvents.map((event) => (
                <tr key={`queue-${event.webhook_event_id}`}>
                  <td>{event.webhook_event_id}</td>
                  <td className="text-break">{event.event_id}</td>
                  <td>{event.payment_id ?? "-"}</td>
                  <td>{renderStatusBadge(event.process_status)}</td>
                  <td>{event.retry_count ?? 0}</td>
                  <td>{event.received_at ? new Date(event.received_at).toLocaleString() : "-"}</td>
                  <td className="text-break">{event.error_message ?? "-"}</td>
                  <td className="d-flex gap-2">
                    {event.payment_id ? (
                      <Button
                        size="sm"
                        variant="outline-primary"
                        onClick={async () => {
                          setSelectedPaymentId(event.payment_id ?? null);
                          if (event.payment_id) {
                            await loadPaymentDetail(event.payment_id);
                          }
                        }}
                      >
                        Open
                      </Button>
                    ) : null}
                    <Button
                      size="sm"
                      variant="outline-secondary"
                      onClick={() => handleRetryWebhookEvent(event.event_id)}
                    >
                      Retry
                    </Button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </Table>
      </Card>

      <Card className="p-3">
        <h4>Payments</h4>
        <Table bordered hover size="sm" className="mt-3">
          <thead>
            <tr>
              <th>ID</th>
              <th>Order</th>
              <th>Status</th>
              <th>Amount</th>
              <th>Provider</th>
              <th>Updated</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {payments.map((payment) => (
              <tr
                key={payment.payment_id}
                onClick={() => setSelectedPaymentId(payment.payment_id)}
                style={{ cursor: "pointer" }}
                className={selectedPaymentId === payment.payment_id ? "table-primary" : ""}
              >
                <td>{payment.payment_id}</td>
                <td>{payment.order_id}</td>
                <td>{renderStatusBadge(payment.status)}</td>
                <td>
                  {payment.amount} {payment.currency}
                </td>
                <td>{payment.provider ?? "-"}</td>
                <td>{payment.updated_at ? new Date(payment.updated_at).toLocaleString() : "-"}</td>
                <td>
                  <Button
                    size="sm"
                    variant="outline-danger"
                    onClick={(event) => {
                      event.stopPropagation();
                      handleCancelPayment(payment.payment_id);
                    }}
                  >
                    Cancel
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>

      {selectedPayment ? (
        <Card className="p-3">
          <div className="d-flex align-items-center justify-content-between">
            <h4 className="mb-0">Payment #{selectedPayment.payment_id}</h4>
            <Button size="sm" variant="outline-primary" onClick={() => loadPaymentDetail(selectedPayment.payment_id)}>
              Refresh Detail
            </Button>
          </div>
          {loadingPaymentDetail ? (
            <div className="text-muted small mt-3 d-flex align-items-center gap-2">
              <Spinner animation="border" size="sm" />
              Loading payment detail...
            </div>
          ) : (
            <>
              <Row className="mt-3 g-2">
                <Col md={3}>
                  <div className="text-muted small">Status</div>
                  <div>{renderStatusBadge(selectedPayment.status)}</div>
                </Col>
                <Col md={3}>
                  <div className="text-muted small">Provider</div>
                  <div>{selectedPayment.provider ?? "-"}</div>
                </Col>
                <Col md={3}>
                  <div className="text-muted small">Provider Payment ID</div>
                  <div>{selectedPayment.provider_payment_id ?? "-"}</div>
                </Col>
                <Col md={3}>
                  <div className="text-muted small">Checkout Session</div>
                  <div>{selectedPayment.checkout_session_id ?? "-"}</div>
                </Col>
              </Row>
              {selectedPayment.failure_reason ? (
                <Alert variant="warning" className="mt-3 mb-0 py-2">
                  failure_reason: {selectedPayment.failure_reason}
                </Alert>
              ) : null}
              <h6 className="mt-4">Webhook Events</h6>
              <Table bordered hover size="sm">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Event ID</th>
                    <th>Status</th>
                    <th>Signature</th>
                    <th>Received</th>
                    <th>Processed</th>
                    <th>Retry</th>
                    <th>Error</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {webhookEvents.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="text-center text-muted">
                        No webhook events
                      </td>
                    </tr>
                  ) : (
                    webhookEvents.map((event) => (
                      <tr key={event.webhook_event_id}>
                        <td>{event.webhook_event_id}</td>
                        <td className="text-break">{event.event_id}</td>
                        <td>{renderStatusBadge(event.process_status)}</td>
                        <td>{event.signature_ok ? "OK" : "FAIL"}</td>
                        <td>{event.received_at ? new Date(event.received_at).toLocaleString() : "-"}</td>
                        <td>{event.processed_at ? new Date(event.processed_at).toLocaleString() : "-"}</td>
                        <td>
                          {event.retry_count ?? 0}
                          {event.next_retry_at ? ` / next: ${new Date(event.next_retry_at).toLocaleString()}` : ""}
                        </td>
                        <td className="text-break">{event.error_message ?? "-"}</td>
                        <td>
                          <Button
                            size="sm"
                            variant="outline-secondary"
                            onClick={() => handleRetryWebhookEvent(event.event_id)}
                          >
                            Retry
                          </Button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </Table>
            </>
          )}
        </Card>
      ) : null}

      <Card className="p-3">
        <h4>Refunds</h4>
        <Table bordered hover size="sm" className="mt-3">
          <thead>
            <tr>
              <th>ID</th>
              <th>Order</th>
              <th>Status</th>
              <th>Amount</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {refunds.map((refund) => (
              <tr key={refund.refund_id}>
                <td>{refund.refund_id}</td>
                <td>{refund.order_id}</td>
                <td>{renderStatusBadge(refund.status)}</td>
                <td>{refund.amount}</td>
                <td className="d-flex gap-2">
                  <Button size="sm" variant="outline-primary" onClick={() => handleApproveRefund(refund.refund_id)}>
                    Approve
                  </Button>
                  <Button size="sm" variant="outline-success" onClick={() => handleProcessRefund(refund.refund_id)}>
                    Process
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </div>
  );
}
