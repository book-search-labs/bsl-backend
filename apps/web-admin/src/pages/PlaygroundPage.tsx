import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import {
  Alert,
  Button,
  ButtonGroup,
  Card,
  Col,
  Form,
  InputGroup,
  Row,
  Spinner,
  Tab,
  Tabs,
  ToggleButton,
} from "react-bootstrap";

import { fetchJson } from "../lib/api";
import { createRequestContext, resolveAdminApiMode, resolveBffBaseUrl, routeRequest } from "../lib/apiRouter";

type Mode = "qc_v1_1" | "legacy";

type ErrorInfo = {
  stage: "input" | "query" | "search";
  status: number;
  statusText: string;
  body: unknown;
};

type QueryContext = {
  meta?: { schemaVersion?: string; traceId?: string; requestId?: string };
  retrievalHints?: { vector?: { enabled?: boolean } };
  [key: string]: unknown;
};

type SearchResponse = {
  trace_id?: string;
  request_id?: string;
  took_ms?: number;
  ranking_applied?: boolean;
  strategy?: string;
  hits?: Array<{
    doc_id?: string;
    rank?: number;
    score?: number;
    debug?: {
      lex_rank?: number;
      vec_rank?: number;
      rrf_score?: number;
      ranking_score?: number;
    };
    source?: {
      title_ko?: string;
      authors?: string[];
      publisher_name?: string;
      issued_year?: number;
      volume?: number;
      edition_labels?: string[];
    };
  }>;
  debug?: {
    applied_fallback_id?: string;
    query_text_source_used?: string;
    stages?: { lexical?: boolean; vector?: boolean; rerank?: boolean };
    query_dsl?: Record<string, unknown>;
    cache?: { hit?: boolean; age_ms?: number; ttl_ms?: number; key?: string };
    retrieval?: {
      lexical?: { took_ms?: number; doc_count?: number; top_k?: number; error?: boolean; timed_out?: boolean };
      vector?: { took_ms?: number; doc_count?: number; top_k?: number; error?: boolean; timed_out?: boolean; mode?: string };
      fusion?: { took_ms?: number; doc_count?: number };
      rerank?: { took_ms?: number; top_k?: number; error?: boolean; timed_out?: boolean };
    };
    warnings?: string[];
  };
  [key: string]: unknown;
};

type BffSearchResponse = {
  version?: string;
  trace_id?: string;
  request_id?: string;
  took_ms?: number;
  timed_out?: boolean;
  total?: number;
  hits?: Array<{
    doc_id?: string;
    score?: number;
    title?: string;
    authors?: string[];
    publisher?: string;
    publication_year?: number;
  }>;
  debug?: { query_dsl?: Record<string, unknown> };
  [key: string]: unknown;
};

type LastRequest = {
  mode: Mode;
  target: "bff" | "direct";
  bffPayload?: unknown;
  queryPayload?: unknown;
  searchPayload?: unknown;
};

const DEFAULT_QUERY = "해리";
const DEFAULT_SIZE = 5;

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, "")}${path}`;
}

function prettyJson(value: unknown) {
  return JSON.stringify(value ?? null, null, 2);
}

function buildCurl(url: string, payload: unknown) {
  const body = prettyJson(payload).replace(/'/g, "'\\''");
  return [
    `curl -s -X POST ${url} \\`,
    "  -H 'Content-Type: application/json' \\",
    `  -d '${body}'`,
  ].join("\n");
}

function mapBffSearchResponse(response: BffSearchResponse): SearchResponse {
  const hits = Array.isArray(response.hits)
    ? response.hits
        .map((hit) => {
          if (!hit) return null;
          return {
            doc_id: hit.doc_id,
            score: hit.score,
            source: {
              title_ko: hit.title ?? "Untitled",
              authors: Array.isArray(hit.authors) ? hit.authors : [],
              publisher_name: hit.publisher ?? undefined,
              issued_year: hit.publication_year ?? undefined,
            },
          };
        })
        .filter(Boolean)
    : [];

  return {
    trace_id: response.trace_id,
    request_id: response.request_id,
    took_ms: response.took_ms,
    hits: hits as SearchResponse["hits"],
    debug: response.debug as SearchResponse["debug"],
  };
}

export default function PlaygroundPage() {
  const [mode, setMode] = useState<Mode>("qc_v1_1");
  const [rawQuery, setRawQuery] = useState(DEFAULT_QUERY);
  const [size, setSize] = useState(DEFAULT_SIZE);
  const [vectorEnabled, setVectorEnabled] = useState(true);
  const [debugEnabled, setDebugEnabled] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ErrorInfo | null>(null);
  const [qcResponse, setQcResponse] = useState<QueryContext | null>(null);
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null);
  const [lastRequest, setLastRequest] = useState<LastRequest | null>(null);

  const queryBaseUrl = import.meta.env.VITE_QUERY_BASE_URL ?? "http://localhost:8001";
  const searchBaseUrl = import.meta.env.VITE_SEARCH_BASE_URL ?? "http://localhost:8080";
  const bffBaseUrl = resolveBffBaseUrl();
  const apiMode = resolveAdminApiMode();

  const hits = useMemo(() => {
    return Array.isArray(searchResponse?.hits) ? searchResponse?.hits : [];
  }, [searchResponse]);

  const curlPreview = useMemo(() => {
    if (!lastRequest) return null;
    const blocks: string[] = [];
    if (lastRequest.target === "bff" && lastRequest.bffPayload) {
      blocks.push("# BFF");
      blocks.push(buildCurl(joinUrl(bffBaseUrl, "/search"), lastRequest.bffPayload));
    } else {
      if (lastRequest.queryPayload) {
        blocks.push("# Query Service");
        blocks.push(buildCurl(joinUrl(queryBaseUrl, "/query-context"), lastRequest.queryPayload));
      }
      if (lastRequest.searchPayload) {
        blocks.push("# Search Service");
        blocks.push(buildCurl(joinUrl(searchBaseUrl, "/search"), lastRequest.searchPayload));
      }
    }
    return blocks.join("\n\n");
  }, [lastRequest, queryBaseUrl, searchBaseUrl, bffBaseUrl]);

  const onRun = async (event: FormEvent) => {
    event.preventDefault();

    const trimmedQuery = rawQuery.trim();
    if (!trimmedQuery) {
      setError({
        stage: "input",
        status: 0,
        statusText: "invalid_input",
        body: "Query is required.",
      });
      return;
    }

    const safeSize = Math.max(1, Math.min(100, Number.isFinite(size) ? size : DEFAULT_SIZE));

    setLoading(true);
    setError(null);
    setQcResponse(null);
    setSearchResponse(null);

    const requestContext = createRequestContext();
    const bffPayload = {
      query: { raw: trimmedQuery },
      options: { size: safeSize, from: 0, enableVector: vectorEnabled },
    };

    let directMeta: {
      qcData?: QueryContext | null;
      queryPayload?: unknown;
      searchPayload?: unknown;
      stage?: "query" | "search";
    } | null = null;

    try {
      const { result, target } = await routeRequest<SearchResponse>({
        route: "search",
        mode: apiMode,
        allowFallback: true,
        requestContext,
        bff: async (context) => {
          const bffResult = await fetchJson<BffSearchResponse>(joinUrl(bffBaseUrl, "/search"), {
            method: "POST",
            headers: context.headers,
            body: JSON.stringify(bffPayload),
          });

          if (!bffResult.ok) {
            return { ok: false, status: bffResult.status, statusText: bffResult.statusText, body: bffResult.body };
          }

          return {
            ok: true,
            status: bffResult.status,
            data: mapBffSearchResponse(bffResult.data),
          };
        },
        direct: async (context) => {
          if (mode === "qc_v1_1") {
            const qcPayload = {
              query: { raw: trimmedQuery },
              client: { device: "web_admin" },
              user: null,
            };

            const qcResult = await fetchJson<QueryContext>(joinUrl(queryBaseUrl, "/query-context"), {
              method: "POST",
              headers: context.headers,
              body: JSON.stringify(qcPayload),
            });

            if (!qcResult.ok) {
              directMeta = { queryPayload: qcPayload, stage: "query" };
              return { ok: false, status: qcResult.status, statusText: qcResult.statusText, body: qcResult.body };
            }

            const qcData = qcResult.data;
            if (qcData?.meta?.schemaVersion !== "qc.v1.1") {
              directMeta = { queryPayload: qcPayload, qcData, stage: "query" };
              return { ok: false, status: 0, statusText: "invalid_schema", body: qcData };
            }

            const qcForSearch = !vectorEnabled
              ? {
                  ...qcData,
                  retrievalHints: {
                    ...qcData.retrievalHints,
                    vector: {
                      ...qcData.retrievalHints?.vector,
                      enabled: false,
                    },
                  },
                }
              : qcData;

            const searchPayload = {
              query_context_v1_1: qcForSearch,
              options: { size: safeSize, from: 0, debug: debugEnabled },
            };

            const searchResult = await fetchJson<SearchResponse>(joinUrl(searchBaseUrl, "/search"), {
              method: "POST",
              headers: context.headers,
              body: JSON.stringify(searchPayload),
            });

            directMeta = { qcData, queryPayload: qcPayload, searchPayload, stage: searchResult.ok ? "search" : "search" };
            return searchResult;
          }

          const legacyPayload = {
            query: { raw: trimmedQuery },
            options: { size: safeSize, from: 0, enableVector: vectorEnabled },
          };

          const legacyResult = await fetchJson<SearchResponse>(joinUrl(searchBaseUrl, "/search"), {
            method: "POST",
            headers: context.headers,
            body: JSON.stringify(legacyPayload),
          });

          directMeta = { searchPayload: legacyPayload, stage: "search" };
          return legacyResult;
        },
      });

      if (target === "bff") {
        setQcResponse(null);
        setLastRequest({ mode, target, bffPayload });
      } else {
        setQcResponse(directMeta?.qcData ?? null);
        setLastRequest({
          mode,
          target,
          queryPayload: directMeta?.queryPayload,
          searchPayload: directMeta?.searchPayload,
        });
      }

      if (!result.ok) {
        setError({
          stage: target === "bff" ? "search" : directMeta?.stage ?? "search",
          status: result.status,
          statusText: result.statusText,
          body: result.body,
        });
        return;
      }

      setSearchResponse(result.data);
    } finally {
      setLoading(false);
    }
  };

  const onReset = () => {
    setMode("qc_v1_1");
    setRawQuery(DEFAULT_QUERY);
    setSize(DEFAULT_SIZE);
    setVectorEnabled(true);
    setDebugEnabled(true);
    setQcResponse(null);
    setSearchResponse(null);
    setLastRequest(null);
    setError(null);
  };

  const traceId = qcResponse?.meta?.traceId ?? searchResponse?.trace_id ?? "-";
  const requestId = qcResponse?.meta?.requestId ?? searchResponse?.request_id ?? "-";

  return (
    <>
      <h3 className="mb-3">Search Playground</h3>

      <Card className="shadow-sm mb-3">
        <Card.Body>
          <Form onSubmit={onRun}>
            <Row className="g-3 align-items-end">
              <Col xs={12} lg={6}>
                <Form.Label>Raw Query</Form.Label>
                <InputGroup>
                  <InputGroup.Text>
                    <i className="bi bi-search" />
                  </InputGroup.Text>
                  <Form.Control
                    value={rawQuery}
                    onChange={(e) => setRawQuery(e.target.value)}
                    placeholder="검색어를 입력하세요"
                    disabled={loading}
                  />
                  <Button type="submit" variant="primary" disabled={loading}>
                    {loading ? (
                      <>
                        <Spinner size="sm" className="me-2" />
                        Running
                      </>
                    ) : (
                      "Run"
                    )}
                  </Button>
                </InputGroup>
              </Col>

              <Col xs={6} md={3} lg={2}>
                <Form.Label>Result size</Form.Label>
                <Form.Control
                  type="number"
                  min={1}
                  max={100}
                  value={size}
                  onChange={(e) => {
                    const next = Number(e.target.value);
                    setSize(Number.isFinite(next) ? next : DEFAULT_SIZE);
                  }}
                  disabled={loading}
                />
              </Col>

              <Col xs={6} md={3} lg={2}>
                <Form.Check
                  type="switch"
                  id="vector-enabled"
                  label="Vector enabled"
                  checked={vectorEnabled}
                  onChange={(e) => setVectorEnabled(e.currentTarget.checked)}
                  disabled={loading}
                />
                <Form.Check
                  type="switch"
                  id="debug-enabled"
                  label="Debug"
                  className="mt-2"
                  checked={debugEnabled}
                  onChange={(e) => setDebugEnabled(e.currentTarget.checked)}
                  disabled={loading}
                />
              </Col>

              <Col xs={12} md={6} lg={2}>
                <Form.Label>Request mode</Form.Label>
                <ButtonGroup className="w-100">
                  <ToggleButton
                    id="mode-qc"
                    type="radio"
                    variant={mode === "qc_v1_1" ? "primary" : "outline-primary"}
                    name="mode"
                    value="qc_v1_1"
                    checked={mode === "qc_v1_1"}
                    onChange={() => setMode("qc_v1_1")}
                    disabled={loading}
                  >
                    qc.v1.1
                  </ToggleButton>
                  <ToggleButton
                    id="mode-legacy"
                    type="radio"
                    variant={mode === "legacy" ? "primary" : "outline-primary"}
                    name="mode"
                    value="legacy"
                    checked={mode === "legacy"}
                    onChange={() => setMode("legacy")}
                    disabled={loading}
                  >
                    Legacy
                  </ToggleButton>
                </ButtonGroup>
              </Col>

              <Col xs={12} md={6} lg={12} className="d-flex flex-wrap gap-2">
                <Button variant="outline-secondary" onClick={onReset} disabled={loading}>
                  Reset
                </Button>
                <div className="text-muted small d-flex align-items-center gap-3">
                  <span>
                    BFF: <span className="fw-semibold">{bffBaseUrl}</span>
                  </span>
                  <span>
                    QS: <span className="fw-semibold">{queryBaseUrl}</span>
                  </span>
                  <span>
                    Search: <span className="fw-semibold">{searchBaseUrl}</span>
                  </span>
                  <span>
                    Mode: <span className="fw-semibold">{apiMode}</span>
                  </span>
                </div>
              </Col>
            </Row>
          </Form>
        </Card.Body>
      </Card>

      {error ? (
        <Alert variant="danger" className="mb-3">
          <div className="fw-semibold">Request failed ({error.stage})</div>
          <div className="text-muted small">
            {error.status ? `HTTP ${error.status} ${error.statusText}` : error.statusText}
          </div>
          <pre className="bg-dark text-light p-2 rounded small mb-0 mt-2 overflow-auto" style={{ maxHeight: 200 }}>
            {prettyJson(error.body)}
          </pre>
        </Alert>
      ) : null}

      <Row className="g-3">
        <Col xs={12} xl={7}>
          <Card className="shadow-sm mb-3">
            <Card.Header className="fw-semibold">Hits</Card.Header>
            <Card.Body>
              {loading ? (
                <div className="text-muted">Loading results…</div>
              ) : hits.length === 0 ? (
                <div className="text-muted">{searchResponse ? "No hits found." : "Run a query to see hits."}</div>
              ) : (
                hits.map((hit, index) => {
                  const source = hit.source ?? {};
                  const title = source.title_ko ?? "Untitled";
                  const authors = Array.isArray(source.authors) ? source.authors.join(", ") : "-";
                  const publisher = source.publisher_name ?? "-";
                  const issuedYear = source.issued_year ?? "-";
                  const volume = source.volume ?? "-";
                  const editions = Array.isArray(source.edition_labels) ? source.edition_labels.join(", ") : "-";
                  const debug = hit.debug ?? {};
                  const formatScore = (value?: number) => (value === undefined ? "-" : value.toFixed(4));

                  return (
                    <div key={hit.doc_id ?? index} className="border rounded p-2 mb-2 bg-white">
                      <div className="fw-semibold">{title}</div>
                      <div className="text-muted small">
                        {authors} · {publisher}
                      </div>
                      <div className="text-muted small">
                        Year: {issuedYear} · Volume: {volume}
                      </div>
                      <div className="text-muted small">
                        Scores: lex={debug.lex_rank ?? "-"} vec={debug.vec_rank ?? "-"} rrf={formatScore(debug.rrf_score)}{" "}
                        rank={formatScore(debug.ranking_score)}
                      </div>
                      <div className="text-muted small">Editions: {editions}</div>
                    </div>
                  );
                })
              )}
            </Card.Body>
          </Card>

          <Card className="shadow-sm">
            <Card.Header className="fw-semibold">Key Meta</Card.Header>
            <Card.Body>
              <Row className="g-3">
                <Col xs={12} md={6}>
                  <div className="text-muted small">traceId</div>
                  <div className="fw-semibold">{traceId}</div>
                </Col>
                <Col xs={12} md={6}>
                  <div className="text-muted small">requestId</div>
                  <div className="fw-semibold">{requestId}</div>
                </Col>
                <Col xs={12} md={6}>
                  <div className="text-muted small">strategy</div>
                  <div className="fw-semibold">{searchResponse?.strategy ?? "-"}</div>
                </Col>
                <Col xs={12} md={6}>
                  <div className="text-muted small">took_ms</div>
                  <div className="fw-semibold">
                    {searchResponse?.took_ms !== undefined ? `${searchResponse?.took_ms} ms` : "-"}
                  </div>
                </Col>
                <Col xs={12} md={6}>
                  <div className="text-muted small">ranking_applied</div>
                  <div className="fw-semibold">
                    {searchResponse?.ranking_applied !== undefined
                      ? String(searchResponse?.ranking_applied)
                      : "-"}
                  </div>
                </Col>
                <Col xs={12} md={6}>
                  <div className="text-muted small">debug.stages</div>
                  <div className="fw-semibold">
                    {searchResponse?.debug?.stages
                      ? `lexical=${String(searchResponse.debug.stages.lexical)} vector=${String(
                          searchResponse.debug.stages.vector
                        )} rerank=${String(searchResponse.debug.stages.rerank)}`
                      : "-"}
                  </div>
                </Col>
                <Col xs={12} md={6}>
                  <div className="text-muted small">debug.applied_fallback_id</div>
                  <div className="fw-semibold">{searchResponse?.debug?.applied_fallback_id ?? "-"}</div>
                </Col>
                <Col xs={12} md={6}>
                  <div className="text-muted small">debug.query_text_source_used</div>
                  <div className="fw-semibold">{searchResponse?.debug?.query_text_source_used ?? "-"}</div>
                </Col>
              </Row>
            </Card.Body>
          </Card>
        </Col>

        <Col xs={12} xl={5}>
          <Card className="shadow-sm">
            <Card.Header className="fw-semibold">JSON + cURL</Card.Header>
            <Card.Body>
              <Tabs id="search-playground-tabs" defaultActiveKey="search" className="mb-3">
                <Tab eventKey="search" title="Search Response">
                  <pre className="bg-dark text-light p-2 rounded small overflow-auto" style={{ maxHeight: 280 }}>
                    {searchResponse ? prettyJson(searchResponse) : "// Run a search to see response JSON"}
                  </pre>
                </Tab>
                <Tab eventKey="debug" title="Debug JSON">
                  <pre className="bg-dark text-light p-2 rounded small overflow-auto" style={{ maxHeight: 280 }}>
                    {searchResponse ? prettyJson(searchResponse.debug ?? null) : "// Run a search to see debug JSON"}
                  </pre>
                </Tab>
                <Tab eventKey="qc" title="QueryContext (qc.v1.1)">
                  <pre className="bg-dark text-light p-2 rounded small overflow-auto" style={{ maxHeight: 280 }}>
                    {lastRequest?.target === "bff"
                      ? "// BFF responses do not expose QueryContext"
                      : mode === "qc_v1_1"
                        ? qcResponse
                          ? prettyJson(qcResponse)
                          : "// Run a search to see qc.v1.1"
                        : "// Legacy mode does not call Query Service"}
                  </pre>
                </Tab>
                <Tab eventKey="curl" title="cURL">
                  <pre className="bg-dark text-light p-2 rounded small overflow-auto" style={{ maxHeight: 280 }}>
                    {curlPreview ?? "// Run a search to see request cURL"}
                  </pre>
                </Tab>
              </Tabs>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </>
  );
}
