import { useCallback, useEffect, useState } from "react";
import { Alert, Badge, Button, Card, Col, Form, Row, Table } from "react-bootstrap";
import { fetchJson } from "../lib/api";
import { resolveAdminApiMode, resolveBffBaseUrl, routeRequest } from "../lib/apiRouter";

type Seller = {
  seller_id: number;
  name: string;
  status: string;
  policy_json?: string | null;
  created_at?: string;
};

type Sku = {
  sku_id: number;
  material_id: string;
  seller_id?: number | null;
  sku_code?: string | null;
  format?: string | null;
  status?: string | null;
  created_at?: string | null;
};

type Offer = {
  offer_id: number;
  sku_id: number;
  seller_id: number;
  currency: string;
  list_price: number;
  sale_price: number;
  status: string;
  priority?: number | null;
  start_at?: string | null;
  end_at?: string | null;
};

type InventoryBalance = {
  sku_id: number;
  seller_id: number;
  on_hand: number;
  reserved: number;
  available: number;
};

type LedgerEvent = {
  ledger_id: number;
  type: string;
  delta: number;
  ref_type?: string | null;
  ref_id?: string | null;
  created_at?: string | null;
};

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, "")}${path}`;
}

export default function ProductOpsPage() {
  const apiMode = resolveAdminApiMode();
  const bffBaseUrl = resolveBffBaseUrl();

  const [sellers, setSellers] = useState<Seller[]>([]);
  const [skus, setSkus] = useState<Sku[]>([]);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [ledger, setLedger] = useState<LedgerEvent[]>([]);
  const [balance, setBalance] = useState<InventoryBalance | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [newSeller, setNewSeller] = useState({ name: "", status: "ACTIVE" });
  const [newSku, setNewSku] = useState({ materialId: "", sellerId: "", format: "PAPERBACK", status: "ACTIVE" });
  const [offerSkuId, setOfferSkuId] = useState("");
  const [newOffer, setNewOffer] = useState({
    skuId: "",
    sellerId: "",
    currency: "KRW",
    listPrice: "",
    salePrice: "",
    status: "ACTIVE",
    priority: "0",
  });
  const [inventorySkuId, setInventorySkuId] = useState("");
  const [inventorySellerId, setInventorySellerId] = useState("");
  const [adjustDelta, setAdjustDelta] = useState("");

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

  const loadSellers = useCallback(async () => {
    const { result } = await callBff<{ items: Seller[] }>("/admin/sellers?limit=50");
    if (result.ok) {
      setSellers(result.data.items ?? []);
    }
  }, [callBff]);

  const loadSkus = useCallback(async () => {
    const { result } = await callBff<{ items: Sku[] }>("/admin/skus?limit=50");
    if (result.ok) {
      setSkus(result.data.items ?? []);
    }
  }, [callBff]);

  const loadOffers = useCallback(async () => {
    if (!offerSkuId) return;
    const { result } = await callBff<{ items: Offer[] }>(`/admin/offers?sku_id=${offerSkuId}`);
    if (result.ok) {
      setOffers(result.data.items ?? []);
    }
  }, [callBff, offerSkuId]);

  const loadInventory = useCallback(async () => {
    if (!inventorySkuId) return;
    const params = new URLSearchParams({
      sku_id: inventorySkuId,
      seller_id: inventorySellerId || "1",
    });
    const balanceResult = await callBff<{ balance: InventoryBalance }>(`/admin/inventory/balance?${params}`);
    if (balanceResult.result.ok) {
      setBalance(balanceResult.result.data.balance);
    }
    const ledgerResult = await callBff<{ items: LedgerEvent[] }>(`/admin/inventory/ledger?${params}`);
    if (ledgerResult.result.ok) {
      setLedger(ledgerResult.result.data.items ?? []);
    }
  }, [callBff, inventorySkuId, inventorySellerId]);

  useEffect(() => {
    loadSellers();
    loadSkus();
  }, [loadSellers, loadSkus]);

  const handleCreateSeller = async () => {
    if (!newSeller.name.trim()) return;
    const { result } = await callBff<{ seller: Seller }>("/admin/sellers", {
      method: "POST",
      body: JSON.stringify(newSeller),
    });
    if (result.ok) {
      setSellers((prev) => [result.data.seller, ...prev]);
      setNewSeller({ name: "", status: "ACTIVE" });
    }
  };

  const handleCreateSku = async () => {
    if (!newSku.materialId.trim()) return;
    const payload = {
      ...newSku,
      sellerId: newSku.sellerId ? Number(newSku.sellerId) : null,
    };
    const { result } = await callBff<{ sku: Sku }>("/admin/skus", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (result.ok) {
      setSkus((prev) => [result.data.sku, ...prev]);
      setNewSku({ materialId: "", sellerId: "", format: "PAPERBACK", status: "ACTIVE" });
    }
  };

  const handleCreateOffer = async () => {
    if (!newOffer.skuId || !newOffer.sellerId) return;
    const payload = {
      ...newOffer,
      skuId: Number(newOffer.skuId),
      sellerId: Number(newOffer.sellerId),
      listPrice: Number(newOffer.listPrice),
      salePrice: Number(newOffer.salePrice),
      priority: Number(newOffer.priority || "0"),
    };
    const { result } = await callBff<{ offer_id: number; offer: Offer }>("/admin/offers", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (result.ok) {
      setOffers((prev) => [result.data.offer, ...prev]);
      setNewOffer({
        skuId: newOffer.skuId,
        sellerId: newOffer.sellerId,
        currency: "KRW",
        listPrice: "",
        salePrice: "",
        status: "ACTIVE",
        priority: "0",
      });
    }
  };

  const handleAdjustInventory = async () => {
    if (!inventorySkuId || !adjustDelta) return;
    const payload = {
      skuId: Number(inventorySkuId),
      sellerId: inventorySellerId ? Number(inventorySellerId) : null,
      delta: Number(adjustDelta),
      idempotencyKey: `adjust_${Date.now()}`,
    };
    const { result } = await callBff<{ balance: InventoryBalance }>("/admin/inventory/adjust", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (result.ok) {
      setBalance(result.data.balance);
      setAdjustDelta("");
      loadInventory();
    }
  };

  return (
    <div className="d-flex flex-column gap-4">
      {errorMessage ? <Alert variant="danger">{errorMessage}</Alert> : null}

      <Card className="p-3">
        <h4 className="mb-3">Sellers</h4>
        <Row className="g-2 align-items-end mb-3">
          <Col md={5}>
            <Form.Label>Name</Form.Label>
            <Form.Control
              value={newSeller.name}
              onChange={(event) => setNewSeller({ ...newSeller, name: event.target.value })}
            />
          </Col>
          <Col md={3}>
            <Form.Label>Status</Form.Label>
            <Form.Select
              value={newSeller.status}
              onChange={(event) => setNewSeller({ ...newSeller, status: event.target.value })}
            >
              <option value="ACTIVE">ACTIVE</option>
              <option value="SUSPENDED">SUSPENDED</option>
            </Form.Select>
          </Col>
          <Col md={2}>
            <Button onClick={handleCreateSeller}>Add seller</Button>
          </Col>
        </Row>
        <Table bordered hover size="sm" className="mb-0">
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {sellers.map((seller) => (
              <tr key={seller.seller_id}>
                <td>{seller.seller_id}</td>
                <td>{seller.name}</td>
                <td>
                  <Badge bg={seller.status === "ACTIVE" ? "success" : "secondary"}>{seller.status}</Badge>
                </td>
                <td>{seller.created_at ? new Date(seller.created_at).toLocaleDateString() : "-"}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>

      <Card className="p-3">
        <h4 className="mb-3">SKUs</h4>
        <Row className="g-2 align-items-end mb-3">
          <Col md={4}>
            <Form.Label>Material ID</Form.Label>
            <Form.Control
              value={newSku.materialId}
              onChange={(event) => setNewSku({ ...newSku, materialId: event.target.value })}
            />
          </Col>
          <Col md={2}>
            <Form.Label>Seller ID</Form.Label>
            <Form.Control
              value={newSku.sellerId}
              onChange={(event) => setNewSku({ ...newSku, sellerId: event.target.value })}
            />
          </Col>
          <Col md={3}>
            <Form.Label>Format</Form.Label>
            <Form.Control
              value={newSku.format}
              onChange={(event) => setNewSku({ ...newSku, format: event.target.value })}
            />
          </Col>
          <Col md={2}>
            <Button onClick={handleCreateSku}>Add SKU</Button>
          </Col>
        </Row>
        <Table bordered hover size="sm" className="mb-0">
          <thead>
            <tr>
              <th>ID</th>
              <th>Material</th>
              <th>Seller</th>
              <th>Format</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {skus.map((sku) => (
              <tr key={sku.sku_id}>
                <td>{sku.sku_id}</td>
                <td>{sku.material_id}</td>
                <td>{sku.seller_id ?? "-"}</td>
                <td>{sku.format ?? "-"}</td>
                <td>{sku.status ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>

      <Card className="p-3">
        <h4 className="mb-3">Offers</h4>
        <Row className="g-2 align-items-end mb-3">
          <Col md={2}>
            <Form.Label>SKU ID</Form.Label>
            <Form.Control value={offerSkuId} onChange={(event) => setOfferSkuId(event.target.value)} />
          </Col>
          <Col md={2}>
            <Button variant="outline-primary" onClick={loadOffers}>
              Load offers
            </Button>
          </Col>
        </Row>
        <Row className="g-2 align-items-end mb-3">
          <Col md={2}>
            <Form.Label>SKU ID</Form.Label>
            <Form.Control
              value={newOffer.skuId}
              onChange={(event) => setNewOffer({ ...newOffer, skuId: event.target.value })}
            />
          </Col>
          <Col md={2}>
            <Form.Label>Seller ID</Form.Label>
            <Form.Control
              value={newOffer.sellerId}
              onChange={(event) => setNewOffer({ ...newOffer, sellerId: event.target.value })}
            />
          </Col>
          <Col md={2}>
            <Form.Label>List Price</Form.Label>
            <Form.Control
              value={newOffer.listPrice}
              onChange={(event) => setNewOffer({ ...newOffer, listPrice: event.target.value })}
            />
          </Col>
          <Col md={2}>
            <Form.Label>Sale Price</Form.Label>
            <Form.Control
              value={newOffer.salePrice}
              onChange={(event) => setNewOffer({ ...newOffer, salePrice: event.target.value })}
            />
          </Col>
          <Col md={2}>
            <Button onClick={handleCreateOffer}>Add offer</Button>
          </Col>
        </Row>
        <Table bordered hover size="sm" className="mb-0">
          <thead>
            <tr>
              <th>ID</th>
              <th>SKU</th>
              <th>Seller</th>
              <th>Price</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {offers.map((offer) => (
              <tr key={offer.offer_id}>
                <td>{offer.offer_id}</td>
                <td>{offer.sku_id}</td>
                <td>{offer.seller_id}</td>
                <td>
                  {offer.sale_price} {offer.currency}
                </td>
                <td>{offer.status}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>

      <Card className="p-3">
        <h4 className="mb-3">Inventory</h4>
        <Row className="g-2 align-items-end mb-3">
          <Col md={2}>
            <Form.Label>SKU ID</Form.Label>
            <Form.Control value={inventorySkuId} onChange={(event) => setInventorySkuId(event.target.value)} />
          </Col>
          <Col md={2}>
            <Form.Label>Seller ID</Form.Label>
            <Form.Control value={inventorySellerId} onChange={(event) => setInventorySellerId(event.target.value)} />
          </Col>
          <Col md={2}>
            <Button variant="outline-primary" onClick={loadInventory}>
              Load balance
            </Button>
          </Col>
        </Row>
        {balance ? (
          <div className="mb-3">
            <Badge bg="info" className="me-2">
              On hand: {balance.on_hand}
            </Badge>
            <Badge bg="warning" className="me-2">
              Reserved: {balance.reserved}
            </Badge>
            <Badge bg="success">Available: {balance.available}</Badge>
          </div>
        ) : null}
        <Row className="g-2 align-items-end mb-3">
          <Col md={3}>
            <Form.Label>Adjust delta</Form.Label>
            <Form.Control value={adjustDelta} onChange={(event) => setAdjustDelta(event.target.value)} />
          </Col>
          <Col md={2}>
            <Button variant="outline-secondary" onClick={handleAdjustInventory}>
              Apply
            </Button>
          </Col>
        </Row>
        <Table bordered hover size="sm" className="mb-0">
          <thead>
            <tr>
              <th>ID</th>
              <th>Type</th>
              <th>Delta</th>
              <th>Ref</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {ledger.map((event) => (
              <tr key={event.ledger_id}>
                <td>{event.ledger_id}</td>
                <td>{event.type}</td>
                <td>{event.delta}</td>
                <td>{event.ref_type ?? "-"}</td>
                <td>{event.created_at ? new Date(event.created_at).toLocaleString() : "-"}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </div>
  );
}
