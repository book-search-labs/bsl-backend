import { useCallback, useState } from "react";
import { Alert, Button, Card, Col, Form, Row, Spinner } from "react-bootstrap";
import { fetchJson } from "../lib/api";
import { createRequestContext, resolveAdminApiMode, resolveBffBaseUrl, routeRequest } from "../lib/apiRouter";

type BookDetailResponse = {
  version?: string;
  doc_id?: string;
  source?: {
    title_ko?: string;
    authors?: string[];
    publisher_name?: string;
    issued_year?: number;
    volume?: number;
    edition_labels?: string[];
    [key: string]: unknown;
  };
  trace_id?: string;
  request_id?: string;
  took_ms?: number;
  [key: string]: unknown;
};

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, "")}${path}`;
}

function prettyJson(value: unknown) {
  return JSON.stringify(value ?? null, null, 2);
}

export default function DocLookupPage() {
  const apiMode = resolveAdminApiMode();
  const bffBaseUrl = resolveBffBaseUrl();
  const searchBaseUrl = import.meta.env.VITE_SEARCH_BASE_URL ?? "http://localhost:8080";

  const [docId, setDocId] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<BookDetailResponse | null>(null);
  const [copySuccess, setCopySuccess] = useState(false);

  const handleLookup = useCallback(
    async (event?: React.FormEvent) => {
      event?.preventDefault();
      const trimmed = docId.trim();
      if (!trimmed) return;

      setLoading(true);
      setErrorMessage(null);
      setResult(null);
      setCopySuccess(false);

      const requestContext = createRequestContext();
      const encoded = encodeURIComponent(trimmed);

      const { result: lookupResult } = await routeRequest<BookDetailResponse>({
        route: "book_detail",
        mode: apiMode,
        allowFallback: true,
        requestContext,
        bff: (context) =>
          fetchJson<BookDetailResponse>(joinUrl(bffBaseUrl, `/books/${encoded}`), {
            method: "GET",
            headers: context.headers,
          }),
        direct: (context) =>
          fetchJson<BookDetailResponse>(joinUrl(searchBaseUrl, `/books/${encoded}`), {
            method: "GET",
            headers: context.headers,
          }),
      });

      if (lookupResult.ok) {
        setResult(lookupResult.data);
      } else if (lookupResult.status === 404) {
        setErrorMessage("Document not found.");
      } else {
        setErrorMessage(`Lookup failed (${lookupResult.status || lookupResult.statusText}).`);
      }

      setLoading(false);
    },
    [apiMode, bffBaseUrl, docId, searchBaseUrl]
  );

  const handleCopy = async () => {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(prettyJson(result));
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 1500);
    } catch {
      setCopySuccess(false);
    }
  };

  const source = result?.source ?? {};

  return (
    <div className="d-flex flex-column gap-3">
      <div>
        <h3 className="mb-1">Doc Lookup</h3>
        <p className="text-muted mb-0">Fetch a document by doc_id and inspect the raw source.</p>
      </div>

      <Card className="shadow-sm">
        <Card.Body>
          <Form onSubmit={handleLookup}>
            <Row className="g-3 align-items-end">
              <Col md={8}>
                <Form.Label>Doc ID</Form.Label>
                <Form.Control
                  value={docId}
                  onChange={(event) => setDocId(event.target.value)}
                  placeholder="doc_id"
                />
              </Col>
              <Col md={4} className="d-flex gap-2">
                <Button type="submit" variant="primary" disabled={loading || !docId.trim()}>
                  {loading ? <Spinner size="sm" /> : "Lookup"}
                </Button>
                <Button variant="outline-secondary" onClick={() => setDocId("")} disabled={loading}>
                  Clear
                </Button>
              </Col>
            </Row>
          </Form>
        </Card.Body>
      </Card>

      {errorMessage ? <Alert variant="danger">{errorMessage}</Alert> : null}

      {result ? (
        <Row className="g-3">
          <Col lg={5}>
            <Card className="shadow-sm h-100">
              <Card.Body>
                <div className="text-muted small">Title</div>
                <div className="fw-semibold">{source.title_ko ?? "-"}</div>
                <div className="text-muted small mt-3">Authors</div>
                <div>{Array.isArray(source.authors) ? source.authors.join(", ") : "-"}</div>
                <div className="text-muted small mt-3">Publisher</div>
                <div>{source.publisher_name ?? "-"}</div>
                <div className="text-muted small mt-3">Issued Year</div>
                <div>{source.issued_year ?? "-"}</div>
                <div className="text-muted small mt-3">Volume</div>
                <div>{source.volume ?? "-"}</div>
                <div className="text-muted small mt-3">Edition Labels</div>
                <div>
                  {Array.isArray(source.edition_labels) && source.edition_labels.length > 0
                    ? source.edition_labels.join(", ")
                    : "-"}
                </div>
              </Card.Body>
            </Card>
          </Col>
          <Col lg={7}>
            <Card className="shadow-sm h-100">
              <Card.Header className="d-flex align-items-center justify-content-between">
                <strong>Raw JSON</strong>
                <div className="d-flex align-items-center gap-2">
                  {copySuccess ? <span className="text-success small">Copied</span> : null}
                  <Button size="sm" variant="outline-primary" onClick={handleCopy}>
                    Copy
                  </Button>
                </div>
              </Card.Header>
              <Card.Body>
                <pre className="small mb-0">{prettyJson(result)}</pre>
              </Card.Body>
            </Card>
          </Col>
        </Row>
      ) : null}
    </div>
  );
}
