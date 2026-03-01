import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Badge, Button, Card, Col, Form, Row, Table } from "react-bootstrap";
import { fetchJson } from "../lib/api";
import { resolveAdminApiMode, resolveBffBaseUrl, routeRequest } from "../lib/apiRouter";

type SettlementCycle = {
  cycle_id: number;
  start_date: string;
  end_date: string;
  status: string;
  generated_at?: string;
  created_at?: string;
  updated_at?: string;
};

type SettlementLine = {
  settlement_line_id: number;
  cycle_id: number;
  seller_id: number;
  gross_sales: number;
  total_fees: number;
  net_amount: number;
  status: string;
  created_at?: string;
  updated_at?: string;
};

type Payout = {
  payout_id: number;
  settlement_line_id: number;
  status: string;
  paid_at?: string | null;
  failure_reason?: string | null;
  cycle_id?: number;
  seller_id?: number;
  net_amount?: number;
  line_status?: string;
  created_at?: string;
  updated_at?: string;
};

type ReconciliationItem = {
  payment_id: number;
  order_id: number;
  payment_amount: number;
  sale_amount: number;
  pg_fee_amount?: number;
  platform_fee_amount?: number;
  refund_amount?: number;
  ledger_entry_count: number;
  currency?: string;
  provider?: string;
  created_at?: string;
};

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, "")}${path}`;
}

function toLocalDateInput(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export default function SettlementOpsPage() {
  const apiMode = resolveAdminApiMode();
  const bffBaseUrl = resolveBffBaseUrl();
  const today = useMemo(() => new Date(), []);

  const [startDate, setStartDate] = useState(toLocalDateInput(new Date(today.getFullYear(), today.getMonth(), 1)));
  const [endDate, setEndDate] = useState(toLocalDateInput(today));
  const [lookupCycleId, setLookupCycleId] = useState("");
  const [cycleStatusFilter, setCycleStatusFilter] = useState("");
  const [cycleFromFilter, setCycleFromFilter] = useState("");
  const [cycleToFilter, setCycleToFilter] = useState("");
  const [cycleLimit, setCycleLimit] = useState("50");
  const [payoutQueueStatusFilter, setPayoutQueueStatusFilter] = useState("FAILED");
  const [payoutQueueLimit, setPayoutQueueLimit] = useState("50");
  const [reconFromFilter, setReconFromFilter] = useState(toLocalDateInput(new Date(today.getFullYear(), today.getMonth(), 1)));
  const [reconToFilter, setReconToFilter] = useState(toLocalDateInput(today));
  const [reconLimit, setReconLimit] = useState("50");

  const [cycles, setCycles] = useState<SettlementCycle[]>([]);
  const [payoutQueueItems, setPayoutQueueItems] = useState<Payout[]>([]);
  const [reconciliationItems, setReconciliationItems] = useState<ReconciliationItem[]>([]);
  const [cycle, setCycle] = useState<SettlementCycle | null>(null);
  const [lines, setLines] = useState<SettlementLine[]>([]);
  const [payouts, setPayouts] = useState<Payout[]>([]);

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

  const renderStatusBadge = (status: string) => {
    if (status === "PAID" || status === "GENERATED" || status === "UNPAID") {
      return <Badge bg={status === "PAID" ? "success" : "primary"}>{status}</Badge>;
    }
    if (status === "FAILED") {
      return <Badge bg="danger">{status}</Badge>;
    }
    return <Badge bg="secondary">{status}</Badge>;
  };

  const loadCycles = useCallback(async () => {
    const params = new URLSearchParams();
    params.set("limit", cycleLimit || "50");
    if (cycleStatusFilter.trim()) {
      params.set("status", cycleStatusFilter.trim());
    }
    if (cycleFromFilter.trim()) {
      params.set("from", cycleFromFilter.trim());
    }
    if (cycleToFilter.trim()) {
      params.set("to", cycleToFilter.trim());
    }
    const { result } = await callBff<{ items: SettlementCycle[] }>(`/admin/settlements/cycles?${params.toString()}`);
    if (!result.ok) {
      setErrorMessage("Failed to load settlement cycles");
      return;
    }
    setCycles(result.data.items ?? []);
  }, [callBff, cycleLimit, cycleStatusFilter, cycleFromFilter, cycleToFilter]);

  const loadPayoutQueue = useCallback(async () => {
    const params = new URLSearchParams();
    params.set("limit", payoutQueueLimit || "50");
    if (payoutQueueStatusFilter.trim()) {
      params.set("status", payoutQueueStatusFilter.trim());
    }
    const { result } = await callBff<{ items: Payout[] }>(`/admin/settlements/payouts?${params.toString()}`);
    if (!result.ok) {
      setErrorMessage("Failed to load payout queue");
      return;
    }
    setPayoutQueueItems(result.data.items ?? []);
  }, [callBff, payoutQueueLimit, payoutQueueStatusFilter]);

  const loadReconciliation = useCallback(async () => {
    const params = new URLSearchParams();
    params.set("limit", reconLimit || "50");
    if (reconFromFilter.trim()) {
      params.set("from", reconFromFilter.trim());
    }
    if (reconToFilter.trim()) {
      params.set("to", reconToFilter.trim());
    }
    const { result } = await callBff<{ items: ReconciliationItem[] }>(
      `/admin/settlements/reconciliation?${params.toString()}`
    );
    if (!result.ok) {
      setErrorMessage("Failed to load reconciliation mismatches");
      return;
    }
    setReconciliationItems(result.data.items ?? []);
  }, [callBff, reconFromFilter, reconLimit, reconToFilter]);

  const loadCycleDetail = useCallback(
    async (cycleId: number) => {
      const detailResult = await callBff<{ cycle: SettlementCycle; lines: SettlementLine[] }>(
        `/admin/settlements/cycles/${cycleId}`
      );
      if (!detailResult.result.ok) {
        setErrorMessage("Failed to load settlement cycle");
        return;
      }
      setCycle(detailResult.result.data.cycle ?? null);
      setLines(detailResult.result.data.lines ?? []);
      setPayouts([]);

      const linesResult = await callBff<{ items: SettlementLine[] }>(`/admin/settlements/cycles/${cycleId}/lines`);
      if (linesResult.result.ok) {
        setLines(linesResult.result.data.items ?? []);
      }
    },
    [callBff]
  );

  useEffect(() => {
    loadCycles();
    loadPayoutQueue();
    loadReconciliation();
  }, [loadCycles, loadPayoutQueue, loadReconciliation]);

  const handleCreateCycle = async () => {
    setErrorMessage(null);
    setInfoMessage(null);
    const { result } = await callBff<{ cycle: SettlementCycle; lines: SettlementLine[] }>(
      "/admin/settlements/cycles",
      {
        method: "POST",
        body: JSON.stringify({
          startDate,
          endDate,
        }),
      }
    );
    if (!result.ok) {
      setErrorMessage("Failed to create settlement cycle");
      return;
    }
    setCycle(result.data.cycle ?? null);
    setLines(result.data.lines ?? []);
    setPayouts([]);
    if (result.data.cycle?.cycle_id) {
      setLookupCycleId(String(result.data.cycle.cycle_id));
    }
    await loadCycles();
    await loadPayoutQueue();
    await loadReconciliation();
    setInfoMessage("Settlement cycle created");
  };

  const handleLoadCycle = async () => {
    setErrorMessage(null);
    setInfoMessage(null);
    const cycleId = Number(lookupCycleId);
    if (!Number.isFinite(cycleId) || cycleId <= 0) {
      setErrorMessage("Enter valid cycle id");
      return;
    }
    await loadCycleDetail(cycleId);
    setInfoMessage(`Loaded cycle #${cycleId}`);
  };

  const handleRunPayouts = async () => {
    if (!cycle) {
      setErrorMessage("Select settlement cycle first");
      return;
    }
    setErrorMessage(null);
    setInfoMessage(null);
    const { result } = await callBff<{ cycle: SettlementCycle; payouts: Payout[] }>(
      `/admin/settlements/cycles/${cycle.cycle_id}/payouts`,
      { method: "POST" }
    );
    if (!result.ok) {
      setErrorMessage("Failed to run payouts");
      return;
    }
    const payoutItems = result.data.payouts ?? [];
    setCycle(result.data.cycle ?? cycle);
    await loadCycleDetail(cycle.cycle_id);
    setPayouts(payoutItems);
    await loadPayoutQueue();
    await loadReconciliation();
    setInfoMessage(`Payouts executed for cycle #${cycle.cycle_id}`);
  };

  const handleRetryPayout = async (payoutId: number, cycleIdHint?: number) => {
    const targetCycleId = cycleIdHint ?? cycle?.cycle_id;
    if (!targetCycleId) {
      setErrorMessage("Select settlement cycle first");
      return;
    }
    setErrorMessage(null);
    setInfoMessage(null);
    const { result } = await callBff<{ cycle: SettlementCycle; payout: Payout; payouts: Payout[] }>(
      `/admin/settlements/payouts/${payoutId}/retry`,
      { method: "POST" }
    );
    if (!result.ok) {
      setErrorMessage(`Failed to retry payout #${payoutId}`);
      return;
    }
    const payoutItems = result.data.payouts ?? [];
    setCycle(result.data.cycle ?? cycle ?? null);
    await loadCycleDetail(targetCycleId);
    setPayouts(payoutItems);
    await loadPayoutQueue();
    await loadReconciliation();
    setInfoMessage(`Retried payout #${payoutId}`);
  };

  return (
    <div className="d-flex flex-column gap-4">
      {errorMessage ? <Alert variant="danger">{errorMessage}</Alert> : null}
      {infoMessage ? <Alert variant="success">{infoMessage}</Alert> : null}

      <Card className="p-3">
        <h4 className="mb-3">Settlement Cycle</h4>
        <Row className="g-2 align-items-end">
          <Col md={3}>
            <Form.Label>Start Date</Form.Label>
            <Form.Control type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
          </Col>
          <Col md={3}>
            <Form.Label>End Date</Form.Label>
            <Form.Control type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
          </Col>
          <Col md={2}>
            <Button onClick={handleCreateCycle}>Create Cycle</Button>
          </Col>
          <Col md={2}>
            <Form.Label>Cycle ID</Form.Label>
            <Form.Control value={lookupCycleId} onChange={(event) => setLookupCycleId(event.target.value)} />
          </Col>
          <Col md={2}>
            <Button variant="outline-primary" onClick={handleLoadCycle}>
              Load Cycle
            </Button>
          </Col>
        </Row>
      </Card>

      <Card className="p-3">
        <div className="d-flex justify-content-between align-items-center mb-3">
          <h4 className="mb-0">Payout Queue</h4>
          <Button variant="outline-primary" onClick={loadPayoutQueue}>
            Refresh Queue
          </Button>
        </div>
        <Row className="g-2 align-items-end mb-3">
          <Col md={2}>
            <Form.Label>Status</Form.Label>
            <Form.Control
              value={payoutQueueStatusFilter}
              onChange={(event) => setPayoutQueueStatusFilter(event.target.value)}
              placeholder="FAILED, PAID..."
            />
          </Col>
          <Col md={2}>
            <Form.Label>Limit</Form.Label>
            <Form.Control value={payoutQueueLimit} onChange={(event) => setPayoutQueueLimit(event.target.value)} />
          </Col>
          <Col md={8} className="d-flex gap-2">
            <Button onClick={loadPayoutQueue}>Apply</Button>
            <Button
              variant="outline-secondary"
              onClick={() => {
                setPayoutQueueStatusFilter("FAILED");
                setPayoutQueueLimit("50");
              }}
            >
              Reset
            </Button>
          </Col>
        </Row>
        <Table bordered hover size="sm" className="mb-0">
          <thead>
            <tr>
              <th>Payout ID</th>
              <th>Cycle</th>
              <th>Seller</th>
              <th>Net</th>
              <th>Status</th>
              <th>Failure</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {payoutQueueItems.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center text-muted">
                  No payout queue items
                </td>
              </tr>
            ) : (
              payoutQueueItems.map((item) => (
                <tr key={`queue-${item.payout_id}`}>
                  <td>{item.payout_id}</td>
                  <td>{item.cycle_id ?? "-"}</td>
                  <td>{item.seller_id ?? "-"}</td>
                  <td>{item.net_amount ?? "-"}</td>
                  <td>{renderStatusBadge(item.status)}</td>
                  <td>{item.failure_reason ?? "-"}</td>
                  <td className="d-flex gap-2">
                    {item.cycle_id ? (
                      <Button
                        size="sm"
                        variant="outline-primary"
                        onClick={async () => {
                          setLookupCycleId(String(item.cycle_id));
                          await loadCycleDetail(item.cycle_id as number);
                          setInfoMessage(`Loaded cycle #${item.cycle_id}`);
                        }}
                      >
                        Open
                      </Button>
                    ) : null}
                    {item.status === "FAILED" ? (
                      <Button
                        size="sm"
                        variant="outline-warning"
                        onClick={() => handleRetryPayout(item.payout_id, item.cycle_id)}
                      >
                        Retry
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </Table>
      </Card>

      <Card className="p-3">
        <div className="d-flex justify-content-between align-items-center mb-3">
          <h4 className="mb-0">Reconciliation (Captured vs Ledger)</h4>
          <Button variant="outline-primary" onClick={loadReconciliation}>
            Refresh Reconciliation
          </Button>
        </div>
        <Row className="g-2 align-items-end mb-3">
          <Col md={2}>
            <Form.Label>From</Form.Label>
            <Form.Control type="date" value={reconFromFilter} onChange={(event) => setReconFromFilter(event.target.value)} />
          </Col>
          <Col md={2}>
            <Form.Label>To</Form.Label>
            <Form.Control type="date" value={reconToFilter} onChange={(event) => setReconToFilter(event.target.value)} />
          </Col>
          <Col md={2}>
            <Form.Label>Limit</Form.Label>
            <Form.Control value={reconLimit} onChange={(event) => setReconLimit(event.target.value)} />
          </Col>
          <Col md={8} className="d-flex gap-2">
            <Button onClick={loadReconciliation}>Apply</Button>
            <Button
              variant="outline-secondary"
              onClick={() => {
                setReconFromFilter(toLocalDateInput(new Date(today.getFullYear(), today.getMonth(), 1)));
                setReconToFilter(toLocalDateInput(today));
                setReconLimit("50");
              }}
            >
              Reset
            </Button>
          </Col>
        </Row>

        <Table bordered hover size="sm" className="mb-0">
          <thead>
            <tr>
              <th>Payment ID</th>
              <th>Order</th>
              <th>Payment</th>
              <th>Sale</th>
              <th>Delta</th>
              <th>Ledger Entries</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {reconciliationItems.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center text-muted">
                  No mismatches
                </td>
              </tr>
            ) : (
              reconciliationItems.map((item) => (
                <tr key={`recon-${item.payment_id}`}>
                  <td>{item.payment_id}</td>
                  <td>{item.order_id}</td>
                  <td>
                    {item.payment_amount} {item.currency ?? ""}
                  </td>
                  <td>{item.sale_amount}</td>
                  <td>{item.sale_amount - item.payment_amount}</td>
                  <td>{item.ledger_entry_count}</td>
                  <td>{item.created_at ? new Date(item.created_at).toLocaleString() : "-"}</td>
                </tr>
              ))
            )}
          </tbody>
        </Table>
      </Card>

      <Card className="p-3">
        <div className="d-flex justify-content-between align-items-center mb-3">
          <h4 className="mb-0">Settlement Cycles</h4>
          <Button variant="outline-primary" onClick={loadCycles}>
            Refresh Cycles
          </Button>
        </div>
        <Row className="g-2 align-items-end mb-3">
          <Col md={2}>
            <Form.Label>Status</Form.Label>
            <Form.Control
              value={cycleStatusFilter}
              onChange={(event) => setCycleStatusFilter(event.target.value)}
              placeholder="GENERATED, PAID..."
            />
          </Col>
          <Col md={2}>
            <Form.Label>From</Form.Label>
            <Form.Control type="date" value={cycleFromFilter} onChange={(event) => setCycleFromFilter(event.target.value)} />
          </Col>
          <Col md={2}>
            <Form.Label>To</Form.Label>
            <Form.Control type="date" value={cycleToFilter} onChange={(event) => setCycleToFilter(event.target.value)} />
          </Col>
          <Col md={2}>
            <Form.Label>Limit</Form.Label>
            <Form.Control value={cycleLimit} onChange={(event) => setCycleLimit(event.target.value)} />
          </Col>
          <Col md={4} className="d-flex gap-2">
            <Button onClick={loadCycles}>Apply</Button>
            <Button
              variant="outline-secondary"
              onClick={() => {
                setCycleStatusFilter("");
                setCycleFromFilter("");
                setCycleToFilter("");
                setCycleLimit("50");
              }}
            >
              Reset
            </Button>
          </Col>
        </Row>

        <Table bordered hover size="sm" className="mb-0">
          <thead>
            <tr>
              <th>Cycle ID</th>
              <th>Period</th>
              <th>Status</th>
              <th>Generated</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {cycles.length === 0 ? (
              <tr>
                <td colSpan={5} className="text-center text-muted">
                  No cycles
                </td>
              </tr>
            ) : (
              cycles.map((item) => (
                <tr key={item.cycle_id}>
                  <td>{item.cycle_id}</td>
                  <td>
                    {item.start_date} ~ {item.end_date}
                  </td>
                  <td>{renderStatusBadge(item.status)}</td>
                  <td>{item.generated_at ? new Date(item.generated_at).toLocaleString() : "-"}</td>
                  <td>
                    <Button
                      size="sm"
                      variant="outline-primary"
                      onClick={async () => {
                        setLookupCycleId(String(item.cycle_id));
                        await loadCycleDetail(item.cycle_id);
                        setInfoMessage(`Loaded cycle #${item.cycle_id}`);
                      }}
                    >
                      View
                    </Button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </Table>
      </Card>

      {cycle ? (
        <Card className="p-3">
          <div className="d-flex justify-content-between align-items-center">
            <h4 className="mb-0">Cycle #{cycle.cycle_id}</h4>
            <Button variant="outline-success" onClick={handleRunPayouts}>
              Run Payouts
            </Button>
          </div>
          <Row className="g-2 mt-2">
            <Col md={3}>
              <div className="text-muted small">Period</div>
              <div>
                {cycle.start_date} ~ {cycle.end_date}
              </div>
            </Col>
            <Col md={2}>
              <div className="text-muted small">Status</div>
              <div>{renderStatusBadge(cycle.status)}</div>
            </Col>
            <Col md={3}>
              <div className="text-muted small">Generated</div>
              <div>{cycle.generated_at ? new Date(cycle.generated_at).toLocaleString() : "-"}</div>
            </Col>
            <Col md={4}>
              <div className="text-muted small">Updated</div>
              <div>{cycle.updated_at ? new Date(cycle.updated_at).toLocaleString() : "-"}</div>
            </Col>
          </Row>

          <h6 className="mt-4">Settlement Lines</h6>
          <Table bordered hover size="sm">
            <thead>
              <tr>
                <th>Line ID</th>
                <th>Seller</th>
                <th>Gross</th>
                <th>Fees</th>
                <th>Net</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {lines.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center text-muted">
                    No settlement lines
                  </td>
                </tr>
              ) : (
                lines.map((line) => (
                  <tr key={line.settlement_line_id}>
                    <td>{line.settlement_line_id}</td>
                    <td>{line.seller_id}</td>
                    <td>{line.gross_sales}</td>
                    <td>{line.total_fees}</td>
                    <td>{line.net_amount}</td>
                    <td>{renderStatusBadge(line.status)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </Table>

          <h6 className="mt-4">Payouts</h6>
          <Table bordered hover size="sm">
            <thead>
              <tr>
                <th>Payout ID</th>
                <th>Line ID</th>
                <th>Status</th>
                <th>Paid At</th>
                <th>Failure Reason</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {payouts.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center text-muted">
                    Run payouts to populate this table
                  </td>
                </tr>
              ) : (
                payouts.map((payout) => (
                  <tr key={payout.payout_id}>
                    <td>{payout.payout_id}</td>
                    <td>{payout.settlement_line_id}</td>
                    <td>{renderStatusBadge(payout.status)}</td>
                    <td>{payout.paid_at ? new Date(payout.paid_at).toLocaleString() : "-"}</td>
                    <td>{payout.failure_reason ?? "-"}</td>
                    <td>
                      {payout.status === "FAILED" ? (
                        <Button
                          size="sm"
                          variant="outline-warning"
                          onClick={() => handleRetryPayout(payout.payout_id)}
                        >
                          Retry
                        </Button>
                      ) : (
                        "-"
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </Table>
        </Card>
      ) : null}
    </div>
  );
}
