import { useCallback, useEffect, useState } from "react";
import { Alert, Badge, Button, Card, Table } from "react-bootstrap";
import { fetchJson } from "../lib/api";
import { resolveAdminApiMode, resolveBffBaseUrl, routeRequest } from "../lib/apiRouter";

type Payment = {
  payment_id: number;
  order_id: number;
  status: string;
  amount: number;
  currency: string;
  method?: string;
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
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

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

  const load = useCallback(async () => {
    const paymentsResult = await callBff<{ items: Payment[] }>("/admin/payments?limit=50");
    if (paymentsResult.result.ok) {
      setPayments(paymentsResult.result.data.items ?? []);
    }
    const refundsResult = await callBff<{ items: Refund[] }>("/admin/refunds?limit=50");
    if (refundsResult.result.ok) {
      setRefunds(refundsResult.result.data.items ?? []);
    }
  }, [callBff]);

  useEffect(() => {
    load();
  }, [load]);

  const handleCancelPayment = async (paymentId: number) => {
    const { result } = await callBff(`/admin/payments/${paymentId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason: "ops_cancel" }),
    });
    if (!result.ok) {
      setErrorMessage("Failed to cancel payment");
      return;
    }
    load();
  };

  const handleApproveRefund = async (refundId: number) => {
    const { result } = await callBff(`/admin/refunds/${refundId}/approve`, { method: "POST" });
    if (!result.ok) {
      setErrorMessage("Failed to approve refund");
      return;
    }
    load();
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
    load();
  };

  return (
    <div className="d-flex flex-column gap-4">
      {errorMessage ? <Alert variant="danger">{errorMessage}</Alert> : null}
      <Card className="p-3">
        <h4>Payments</h4>
        <Table bordered hover size="sm" className="mt-3">
          <thead>
            <tr>
              <th>ID</th>
              <th>Order</th>
              <th>Status</th>
              <th>Amount</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {payments.map((payment) => (
              <tr key={payment.payment_id}>
                <td>{payment.payment_id}</td>
                <td>{payment.order_id}</td>
                <td>
                  <Badge bg={payment.status === "CAPTURED" ? "success" : "secondary"}>{payment.status}</Badge>
                </td>
                <td>
                  {payment.amount} {payment.currency}
                </td>
                <td>
                  <Button size="sm" variant="outline-danger" onClick={() => handleCancelPayment(payment.payment_id)}>
                    Cancel
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>

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
                <td>
                  <Badge bg={refund.status === "REFUNDED" ? "success" : "warning"}>{refund.status}</Badge>
                </td>
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
