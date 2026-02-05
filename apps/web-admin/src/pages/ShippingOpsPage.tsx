import { useCallback, useEffect, useState } from "react";
import { Alert, Badge, Button, Card, Col, Form, Row, Table } from "react-bootstrap";
import { fetchJson } from "../lib/api";
import { resolveAdminApiMode, resolveBffBaseUrl, routeRequest } from "../lib/apiRouter";

type Shipment = {
  shipment_id: number;
  order_id: number;
  status: string;
  carrier?: string | null;
  tracking_no?: string | null;
};

type ShipmentEvent = {
  event_type: string;
  event_time: string;
};

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, "")}${path}`;
}

export default function ShippingOpsPage() {
  const apiMode = resolveAdminApiMode();
  const bffBaseUrl = resolveBffBaseUrl();

  const [shipments, setShipments] = useState<Shipment[]>([]);
  const [selected, setSelected] = useState<Shipment | null>(null);
  const [events, setEvents] = useState<ShipmentEvent[]>([]);
  const [carrierCode, setCarrierCode] = useState("CJ");
  const [trackingNumber, setTrackingNumber] = useState("");
  const [statusUpdate, setStatusUpdate] = useState("IN_TRANSIT");
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

  const loadShipments = useCallback(async () => {
    const { result } = await callBff<{ items: Shipment[] }>("/admin/shipments?limit=50");
    if (result.ok) {
      setShipments(result.data.items ?? []);
    }
  }, [callBff]);

  const loadShipmentDetail = useCallback(
    async (shipmentId: number) => {
      const { result } = await callBff<{ shipment: Shipment; events: ShipmentEvent[] }>(
        `/admin/shipments/${shipmentId}`,
        { method: "GET" }
      );
      if (result.ok) {
        setSelected(result.data.shipment);
        setEvents(result.data.events ?? []);
        setCarrierCode(result.data.shipment.carrier ?? "CJ");
        setTrackingNumber(result.data.shipment.tracking_no ?? "");
      }
    },
    [callBff]
  );

  useEffect(() => {
    loadShipments();
  }, [loadShipments]);

  const handleAssignLabel = async () => {
    if (!selected) return;
    const { result } = await callBff(`/admin/shipments/${selected.shipment_id}/label`, {
      method: "POST",
      body: JSON.stringify({ carrierCode, trackingNumber }),
    });
    if (!result.ok) {
      setErrorMessage("Failed to assign label");
      return;
    }
    loadShipmentDetail(selected.shipment_id);
    loadShipments();
  };

  const handleStatusUpdate = async () => {
    if (!selected) return;
    const { result } = await callBff(`/admin/shipments/${selected.shipment_id}/status`, {
      method: "POST",
      body: JSON.stringify({ status: statusUpdate }),
    });
    if (!result.ok) {
      setErrorMessage("Failed to update status");
      return;
    }
    loadShipmentDetail(selected.shipment_id);
    loadShipments();
  };

  return (
    <div className="d-flex flex-column gap-4">
      {errorMessage ? <Alert variant="danger">{errorMessage}</Alert> : null}
      <Card className="p-3">
        <h4>Shipments</h4>
        <Table bordered hover size="sm" className="mt-3">
          <thead>
            <tr>
              <th>ID</th>
              <th>Order</th>
              <th>Status</th>
              <th>Carrier</th>
            </tr>
          </thead>
          <tbody>
            {shipments.map((shipment) => (
              <tr
                key={shipment.shipment_id}
                onClick={() => loadShipmentDetail(shipment.shipment_id)}
                style={{ cursor: "pointer" }}
              >
                <td>{shipment.shipment_id}</td>
                <td>{shipment.order_id}</td>
                <td>
                  <Badge bg={shipment.status === "DELIVERED" ? "success" : "secondary"}>{shipment.status}</Badge>
                </td>
                <td>{shipment.carrier ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>

      {selected ? (
        <Card className="p-3">
          <h4>Shipment #{selected.shipment_id}</h4>
          <Row className="g-2 align-items-end mt-2">
            <Col md={3}>
              <Form.Label>Carrier</Form.Label>
              <Form.Control value={carrierCode} onChange={(event) => setCarrierCode(event.target.value)} />
            </Col>
            <Col md={4}>
              <Form.Label>Tracking No</Form.Label>
              <Form.Control value={trackingNumber} onChange={(event) => setTrackingNumber(event.target.value)} />
            </Col>
            <Col md={2}>
              <Button onClick={handleAssignLabel}>Assign</Button>
            </Col>
          </Row>
          <Row className="g-2 align-items-end mt-3">
            <Col md={3}>
              <Form.Label>Status</Form.Label>
              <Form.Select value={statusUpdate} onChange={(event) => setStatusUpdate(event.target.value)}>
                <option value="IN_TRANSIT">IN_TRANSIT</option>
                <option value="DELIVERED">DELIVERED</option>
                <option value="RETURNED">RETURNED</option>
              </Form.Select>
            </Col>
            <Col md={2}>
              <Button variant="outline-primary" onClick={handleStatusUpdate}>
                Update
              </Button>
            </Col>
          </Row>
          <div className="mt-4">
            <h6>Events</h6>
            <ul className="list-unstyled">
              {events.map((event, idx) => (
                <li key={`${event.event_type}-${idx}`} className="text-muted small">
                  {event.event_time} — {event.event_type}
                </li>
              ))}
            </ul>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
