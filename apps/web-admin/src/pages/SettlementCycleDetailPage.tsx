import { useEffect, useState } from "react";
import { Alert, Badge, Button, Card, Col, Row, Table } from "react-bootstrap";
import { useNavigate, useParams } from "react-router-dom";
import { resolveAdminApiMode, resolveBffBaseUrl } from "../lib/apiRouter";
import {
  createSettlementApi,
  formatDateTime,
  type Payout,
  type SettlementCycle,
  type SettlementLine,
} from "../lib/settlementApi";

function renderStatusBadge(status: string) {
  if (status === "PAID" || status === "GENERATED" || status === "UNPAID") {
    return <Badge bg={status === "PAID" ? "success" : "primary"}>{status}</Badge>;
  }
  if (status === "FAILED") {
    return <Badge bg="danger">{status}</Badge>;
  }
  if (status === "DRAFT") {
    return <Badge bg="secondary">{status}</Badge>;
  }
  return <Badge bg="dark">{status}</Badge>;
}

function summarizePayouts(items: Payout[]) {
  return items.reduce<Record<string, number>>((summary, item) => {
    summary[item.status] = (summary[item.status] ?? 0) + 1;
    return summary;
  }, {});
}

export default function SettlementCycleDetailPage() {
  const navigate = useNavigate();
  const { cycleId } = useParams();
  const apiMode = resolveAdminApiMode();
  const bffBaseUrl = resolveBffBaseUrl();

  const [cycle, setCycle] = useState<SettlementCycle | null>(null);
  const [lines, setLines] = useState<SettlementLine[]>([]);
  const [payouts, setPayouts] = useState<Payout[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  const numericCycleId = Number(cycleId);
  const payoutSummary = summarizePayouts(payouts);

  async function loadCycleDetail() {
    if (!Number.isFinite(numericCycleId) || numericCycleId <= 0) {
      setErrorMessage("Invalid settlement cycle id");
      return;
    }

    setErrorMessage(null);
    const api = createSettlementApi(apiMode, bffBaseUrl);
    const detail = await api.getCycle(numericCycleId);
    if (!detail.ok) {
      setErrorMessage("Failed to load settlement cycle");
      return;
    }

    setCycle(detail.data.cycle ?? null);
    setLines(detail.data.lines ?? []);
    setPayouts(detail.data.payouts ?? []);

    const lineResult = await api.listCycleLines(numericCycleId);
    if (lineResult.ok) {
      setLines(lineResult.data.items ?? []);
    }
  }

  useEffect(() => {
    void loadCycleDetail();
  }, [cycleId]);

  async function handleGenerateCycle() {
    if (!Number.isFinite(numericCycleId) || numericCycleId <= 0) {
      setErrorMessage("Invalid settlement cycle id");
      return;
    }

    setErrorMessage(null);
    setInfoMessage(null);
    const api = createSettlementApi(apiMode, bffBaseUrl);
    const result = await api.generateCycle(numericCycleId);
    if (!result.ok) {
      setErrorMessage("Failed to generate settlement cycle");
      return;
    }

    setCycle(result.data.cycle ?? null);
    setLines(result.data.lines ?? []);
    setPayouts(result.data.payouts ?? []);
    setInfoMessage(`Generated cycle #${numericCycleId}`);
  }

  async function handlePayPayout(payoutId: number) {
    setErrorMessage(null);
    setInfoMessage(null);
    const api = createSettlementApi(apiMode, bffBaseUrl);
    const result = await api.payPayout(payoutId);
    if (!result.ok) {
      setErrorMessage(`Failed to pay payout #${payoutId}`);
      return;
    }

    setCycle(result.data.cycle ?? cycle);
    setPayouts(result.data.payouts ?? []);
    await loadCycleDetail();
    setInfoMessage(`Processed payout #${payoutId}`);
  }

  return (
    <div className="d-flex flex-column gap-4">
      {errorMessage ? <Alert variant="danger">{errorMessage}</Alert> : null}
      {infoMessage ? <Alert variant="success">{infoMessage}</Alert> : null}

      <Card className="p-3">
        <div className="d-flex justify-content-between align-items-center flex-wrap gap-2">
          <div>
            <h4 className="mb-1">Settlement Cycle Detail</h4>
            <div className="text-muted small">Cycle #{Number.isFinite(numericCycleId) ? numericCycleId : "-"}</div>
          </div>
          <div className="d-flex gap-2">
            <Button variant="outline-secondary" onClick={() => navigate("/ops/commerce/settlements")}>
              Back to List
            </Button>
            <Button variant="outline-primary" onClick={() => void loadCycleDetail()}>
              Refresh
            </Button>
            {cycle?.status === "DRAFT" ? (
              <Button variant="success" onClick={() => void handleGenerateCycle()}>
                Generate
              </Button>
            ) : null}
          </div>
        </div>
      </Card>

      {cycle ? (
        <>
          <Card className="p-3">
            <Row className="g-3">
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
                <div className="text-muted small">Generated At</div>
                <div>{formatDateTime(cycle.generated_at)}</div>
              </Col>
              <Col md={2}>
                <div className="text-muted small">Created At</div>
                <div>{formatDateTime(cycle.created_at)}</div>
              </Col>
              <Col md={2}>
                <div className="text-muted small">Updated At</div>
                <div>{formatDateTime(cycle.updated_at)}</div>
              </Col>
            </Row>
          </Card>

          <Card className="p-3">
            <div className="d-flex justify-content-between align-items-center mb-3">
              <h5 className="mb-0">Payout Summary</h5>
              <div className="d-flex flex-wrap gap-2">
                {Object.keys(payoutSummary).length === 0 ? (
                  <Badge bg="secondary">No payouts</Badge>
                ) : (
                  Object.entries(payoutSummary).map(([status, count]) => (
                    <Badge key={status} bg={status === "PAID" ? "success" : status === "FAILED" ? "danger" : "primary"}>
                      {status}: {count}
                    </Badge>
                  ))
                )}
              </div>
            </div>

            <h6 className="mt-2">Settlement Lines</h6>
            <Table bordered hover size="sm" className="mb-0">
              <thead>
                <tr>
                  <th>Line ID</th>
                  <th>Seller</th>
                  <th>Gross</th>
                  <th>Fees</th>
                  <th>Refunds</th>
                  <th>Net</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {lines.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center text-muted">
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
                      <td>{line.refund_amount ?? 0}</td>
                      <td>{line.net_amount}</td>
                      <td>{renderStatusBadge(line.status)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </Table>
          </Card>

          <Card className="p-3">
            <div className="d-flex justify-content-between align-items-center mb-3">
              <h5 className="mb-0">Payouts</h5>
              <Button variant="outline-primary" onClick={() => void loadCycleDetail()}>
                Refresh Payouts
              </Button>
            </div>
            <Table bordered hover size="sm" className="mb-0">
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
                      {cycle.status === "DRAFT" ? "Generate cycle to populate payouts" : "No payouts"}
                    </td>
                  </tr>
                ) : (
                  payouts.map((payout) => (
                    <tr key={payout.payout_id}>
                      <td>{payout.payout_id}</td>
                      <td>{payout.settlement_line_id}</td>
                      <td>{renderStatusBadge(payout.status)}</td>
                      <td>{formatDateTime(payout.paid_at)}</td>
                      <td>{payout.failure_reason ?? "-"}</td>
                      <td>
                        {payout.status === "FAILED" || payout.status === "SCHEDULED" ? (
                          <Button
                            size="sm"
                            variant={payout.status === "FAILED" ? "outline-warning" : "outline-success"}
                            onClick={() => void handlePayPayout(payout.payout_id)}
                          >
                            {payout.status === "FAILED" ? "Retry Pay" : "Pay"}
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
        </>
      ) : null}
    </div>
  );
}
