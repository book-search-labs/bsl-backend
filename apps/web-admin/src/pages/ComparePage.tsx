import { useCallback, useMemo, useState } from "react";
import { Alert, Badge, Button, Card, Col, Form, Row, Spinner, Table } from "react-bootstrap";

import { fetchJson } from "../lib/api";
import { createRequestContext, resolveBffBaseUrl } from "../lib/apiRouter";
import { loadAdminSettings } from "../lib/adminSettings";

type VariantId = "A" | "B" | "C";

type VariantConfig = {
  id: VariantId;
  label: string;
  size: number;
  vectorEnabled: boolean;
  enabled: boolean;
};

type VariantHit = {
  doc_id: string;
  title: string;
  authors: string[];
  publisher?: string;
  issued_year?: number | null;
  score?: number | null;
};

type VariantResult = {
  loading: boolean;
  error?: string | null;
  hits: VariantHit[];
};

type BffSearchResponse = {
  hits?: Array<{
    doc_id?: string;
    score?: number;
    title?: string;
    authors?: string[];
    publisher?: string;
    publication_year?: number;
  }>;
  took_ms?: number;
  total?: number;
  trace_id?: string;
  request_id?: string;
  [key: string]: unknown;
};

const DEFAULT_QUERY = "해리 포터";

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, "")}${path}`;
}

function normalizeHits(response: BffSearchResponse): VariantHit[] {
  const hits = Array.isArray(response.hits) ? response.hits : [];
  return hits
    .map((hit) => {
      if (!hit?.doc_id) return null;
      return {
        doc_id: hit.doc_id,
        title: hit.title ?? "Untitled",
        authors: Array.isArray(hit.authors) ? hit.authors : [],
        publisher: hit.publisher ?? undefined,
        issued_year: hit.publication_year ?? undefined,
        score: hit.score ?? undefined,
      };
    })
    .filter(Boolean) as VariantHit[];
}

function buildOverlap(a: VariantHit[], b: VariantHit[]) {
  const aIds = new Set(a.map((hit) => hit.doc_id));
  const bIds = new Set(b.map((hit) => hit.doc_id));
  const intersection = [...aIds].filter((id) => bIds.has(id));
  const unionSize = new Set([...aIds, ...bIds]).size;
  const jaccard = unionSize === 0 ? 0 : intersection.length / unionSize;
  return {
    intersectionCount: intersection.length,
    unionCount: unionSize,
    jaccard,
  };
}

export default function ComparePage() {
  const settings = loadAdminSettings();
  const bffBaseUrl = resolveBffBaseUrl();

  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [variants, setVariants] = useState<VariantConfig[]>([
    {
      id: "A",
      label: "Variant A",
      size: settings.defaultSize,
      vectorEnabled: settings.defaultVector,
      enabled: true,
    },
    {
      id: "B",
      label: "Variant B",
      size: settings.defaultSize,
      vectorEnabled: !settings.defaultVector,
      enabled: true,
    },
    {
      id: "C",
      label: "Variant C",
      size: settings.defaultSize,
      vectorEnabled: settings.defaultVector,
      enabled: false,
    },
  ]);
  const [results, setResults] = useState<Record<VariantId, VariantResult>>({
    A: { loading: false, hits: [] },
    B: { loading: false, hits: [] },
    C: { loading: false, hits: [] },
  });
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const updateVariant = (id: VariantId, updates: Partial<VariantConfig>) => {
    setVariants((prev) => prev.map((variant) => (variant.id === id ? { ...variant, ...updates } : variant)));
  };

  const runVariant = useCallback(
    async (variant: VariantConfig) => {
      const requestContext = createRequestContext();
      const payload = {
        query: { raw: query.trim() },
        options: { size: variant.size, from: 0, enableVector: variant.vectorEnabled },
      };

      const response = await fetchJson<BffSearchResponse>(joinUrl(bffBaseUrl, "/search"), {
        method: "POST",
        headers: requestContext.headers,
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(response.statusText || "search_failed");
      }

      return normalizeHits(response.data);
    },
    [bffBaseUrl, query]
  );

  const handleRun = async () => {
    const trimmed = query.trim();
    if (!trimmed) {
      setErrorMessage("Query is required.");
      return;
    }

    setErrorMessage(null);
    const nextResults = { ...results };
    variants.forEach((variant) => {
      if (!variant.enabled) return;
      nextResults[variant.id] = { loading: true, hits: [] };
    });
    setResults(nextResults);

    await Promise.all(
      variants.map(async (variant) => {
        if (!variant.enabled) return;
        try {
          const hits = await runVariant(variant);
          setResults((prev) => ({
            ...prev,
            [variant.id]: { loading: false, hits },
          }));
        } catch (err) {
          setResults((prev) => ({
            ...prev,
            [variant.id]: {
              loading: false,
              hits: [],
              error: err instanceof Error ? err.message : "Search failed",
            },
          }));
        }
      })
    );
  };

  const activeVariants = variants.filter((variant) => variant.enabled);

  const overlapAB = useMemo(() => {
    if (!results.A.hits.length || !results.B.hits.length) return null;
    return buildOverlap(results.A.hits, results.B.hits);
  }, [results.A.hits, results.B.hits]);

  const overlapAC = useMemo(() => {
    if (!results.A.hits.length || !results.C.hits.length) return null;
    return buildOverlap(results.A.hits, results.C.hits);
  }, [results.A.hits, results.C.hits]);

  const overlapBC = useMemo(() => {
    if (!results.B.hits.length || !results.C.hits.length) return null;
    return buildOverlap(results.B.hits, results.C.hits);
  }, [results.B.hits, results.C.hits]);

  const rankMaps = useMemo(() => {
    const map: Record<VariantId, Map<string, number>> = {
      A: new Map(),
      B: new Map(),
      C: new Map(),
    };
    (Object.keys(map) as VariantId[]).forEach((key) => {
      results[key].hits.forEach((hit, index) => {
        map[key].set(hit.doc_id, index + 1);
      });
    });
    return map;
  }, [results]);

  const renderResults = (variant: VariantConfig) => {
    const state = results[variant.id];
    const otherIds = (Object.keys(results) as VariantId[]).filter((id) => id !== variant.id);

    return (
      <Card className="shadow-sm h-100">
        <Card.Header className="d-flex align-items-center justify-content-between">
          <div>
            <strong>{variant.label}</strong>
            <div className="text-muted small">Vector: {variant.vectorEnabled ? "On" : "Off"}</div>
          </div>
          <Badge bg={variant.enabled ? "primary" : "secondary"}>{variant.id}</Badge>
        </Card.Header>
        <Card.Body>
          {state.loading ? (
            <div className="d-flex align-items-center gap-2 text-muted">
              <Spinner size="sm" /> Running...
            </div>
          ) : state.error ? (
            <Alert variant="danger">{state.error}</Alert>
          ) : state.hits.length === 0 ? (
            <div className="text-muted">No results.</div>
          ) : (
            <Table size="sm" responsive className="mb-0">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Title</th>
                  <th>Meta</th>
                </tr>
              </thead>
              <tbody>
                {state.hits.map((hit, index) => {
                  const badges = otherIds
                    .map((id) => (rankMaps[id].has(hit.doc_id) ? id : null))
                    .filter(Boolean) as VariantId[];
                  const rankDiff = rankMaps.A.has(hit.doc_id)
                    ? (rankMaps.A.get(hit.doc_id) ?? 0) - (index + 1)
                    : null;

                  return (
                    <tr key={hit.doc_id}>
                      <td>
                        {index + 1}
                        {variant.id !== "A" && rankDiff !== null ? (
                          <div className="small text-muted">Δ {rankDiff}</div>
                        ) : null}
                      </td>
                      <td>
                        <div className="fw-semibold">{hit.title}</div>
                        <div className="text-muted small">{hit.authors.join(", ") || "-"}</div>
                      </td>
                      <td className="text-muted small">
                        {hit.publisher ?? "-"} · {hit.issued_year ?? "-"}
                        <div className="d-flex flex-wrap gap-1 mt-1">
                          {badges.map((badge) => (
                            <Badge key={`${hit.doc_id}-${badge}`} bg="secondary">
                              In {badge}
                            </Badge>
                          ))}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          )}
        </Card.Body>
      </Card>
    );
  };

  return (
    <div className="d-flex flex-column gap-3">
      <div>
        <h3 className="mb-1">Compare</h3>
        <p className="text-muted mb-0">Run the same query across A/B/C variants and compare results.</p>
      </div>

      <Card className="shadow-sm">
        <Card.Body>
          {errorMessage ? <Alert variant="danger">{errorMessage}</Alert> : null}
          <Form onSubmit={(event) => event.preventDefault()}>
            <Row className="g-3 align-items-end">
              <Col md={6}>
                <Form.Label>Query</Form.Label>
                <Form.Control
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search query"
                />
              </Col>
              <Col md={3}>
                <Button variant="primary" onClick={handleRun}>
                  Run Compare
                </Button>
              </Col>
            </Row>

            <Row className="g-3 mt-2">
              {variants.map((variant) => (
                <Col key={variant.id} md={4}>
                  <Card className="h-100">
                    <Card.Body className="d-flex flex-column gap-2">
                      <div className="d-flex justify-content-between align-items-center">
                        <strong>{variant.label}</strong>
                        <Form.Check
                          type="switch"
                          checked={variant.enabled}
                          onChange={(event) => updateVariant(variant.id, { enabled: event.target.checked })}
                          label="Use"
                        />
                      </div>
                      <Form.Group>
                        <Form.Label>Size</Form.Label>
                        <Form.Control
                          type="number"
                          min={1}
                          max={100}
                          value={variant.size}
                          onChange={(event) => updateVariant(variant.id, { size: Number(event.target.value) })}
                          disabled={!variant.enabled}
                        />
                      </Form.Group>
                      <Form.Check
                        type="switch"
                        label="Vector search"
                        checked={variant.vectorEnabled}
                        onChange={(event) =>
                          updateVariant(variant.id, { vectorEnabled: event.target.checked })
                        }
                        disabled={!variant.enabled}
                      />
                    </Card.Body>
                  </Card>
                </Col>
              ))}
            </Row>
          </Form>
        </Card.Body>
      </Card>

      {activeVariants.length >= 2 ? (
        <Row className="g-3">
          <Col md={4}>
            <Card className="shadow-sm">
              <Card.Body>
                <div className="text-muted small">A vs B</div>
                <div className="fw-semibold">
                  {overlapAB ? `${overlapAB.intersectionCount} overlap` : "-"}
                </div>
                <div className="text-muted small">
                  Jaccard: {overlapAB ? overlapAB.jaccard.toFixed(2) : "-"}
                </div>
              </Card.Body>
            </Card>
          </Col>
          <Col md={4}>
            <Card className="shadow-sm">
              <Card.Body>
                <div className="text-muted small">A vs C</div>
                <div className="fw-semibold">
                  {overlapAC ? `${overlapAC.intersectionCount} overlap` : "-"}
                </div>
                <div className="text-muted small">
                  Jaccard: {overlapAC ? overlapAC.jaccard.toFixed(2) : "-"}
                </div>
              </Card.Body>
            </Card>
          </Col>
          <Col md={4}>
            <Card className="shadow-sm">
              <Card.Body>
                <div className="text-muted small">B vs C</div>
                <div className="fw-semibold">
                  {overlapBC ? `${overlapBC.intersectionCount} overlap` : "-"}
                </div>
                <div className="text-muted small">
                  Jaccard: {overlapBC ? overlapBC.jaccard.toFixed(2) : "-"}
                </div>
              </Card.Body>
            </Card>
          </Col>
        </Row>
      ) : null}

      <Row className="g-3">
        {variants.map((variant) => (
          <Col key={`result-${variant.id}`} md={4}>
            {renderResults(variant)}
          </Col>
        ))}
      </Row>
    </div>
  );
}
