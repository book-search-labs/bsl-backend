import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Alert, Button, Card, Col, Form, Row, Spinner } from "react-bootstrap";

import { fetchJson } from "../lib/api";

type ErrorInfo = {
  status: number;
  statusText: string;
  body: unknown;
};

const DEFAULT_QUERY = "해리 포터";
const DEFAULT_TIMEOUT = 200;
const DEFAULT_SIZE = 5;

const DEFAULT_CANDIDATES = [
  {
    doc_id: "b1",
    features: {
      rrf_score: 0.167,
      lex_rank: 1,
      vec_rank: 2,
      issued_year: 1999,
      volume: 1,
      edition_labels: ["recover"],
    },
  },
  {
    doc_id: "b2",
    features: {
      rrf_score: 0.15,
      lex_rank: 2,
      vec_rank: 1,
      issued_year: 2001,
      volume: 2,
      edition_labels: [],
    },
  },
];

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

export default function RerankPlaygroundPage() {
  const [queryText, setQueryText] = useState(DEFAULT_QUERY);
  const [timeoutMs, setTimeoutMs] = useState(DEFAULT_TIMEOUT);
  const [size, setSize] = useState(DEFAULT_SIZE);
  const [debugEnabled, setDebugEnabled] = useState(true);
  const [rerankEnabled, setRerankEnabled] = useState(true);
  const [candidatesJson, setCandidatesJson] = useState(prettyJson(DEFAULT_CANDIDATES));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ErrorInfo | null>(null);
  const [response, setResponse] = useState<unknown>(null);

  const baseUrl = import.meta.env.VITE_RANKING_BASE_URL ?? "http://localhost:8082";
  const endpoint = `${baseUrl.replace(/\/$/, "")}/rerank`;

  const payload = useMemo(() => {
    let candidates: unknown = [];
    try {
      candidates = JSON.parse(candidatesJson);
    } catch {
      candidates = [];
    }
    return {
      query: { text: queryText },
      candidates,
      options: {
        size,
        debug: debugEnabled,
        rerank: rerankEnabled,
        timeout_ms: timeoutMs,
      },
    };
  }, [candidatesJson, debugEnabled, queryText, rerankEnabled, size, timeoutMs]);

  const curlPreview = useMemo(() => buildCurl(endpoint, payload), [endpoint, payload]);

  const onRun = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setResponse(null);

    const result = await fetchJson(endpoint, {
      method: "POST",
      body: JSON.stringify(payload),
    });

    if (result.ok) {
      setResponse(result.data);
    } else {
      setError({ status: result.status, statusText: result.statusText, body: result.body });
    }
    setLoading(false);
  };

  return (
    <div className="px-3 px-xl-4 py-4">
      <h1 className="mb-3">Rerank Playground</h1>
      <p className="text-muted">
        Replay rerank failures with debug features, scores, and guardrail reasons.
      </p>

      <Form onSubmit={onRun}>
        <Row className="g-3">
          <Col lg={4}>
            <Card className="h-100">
              <Card.Body>
                <Card.Title>Request</Card.Title>
                <Form.Group className="mb-3">
                  <Form.Label>Query</Form.Label>
                  <Form.Control
                    value={queryText}
                    onChange={(event) => setQueryText(event.target.value)}
                  />
                </Form.Group>
                <Row className="g-2">
                  <Col>
                    <Form.Label>Top N</Form.Label>
                    <Form.Control
                      type="number"
                      min={1}
                      value={size}
                      onChange={(event) => setSize(Number(event.target.value))}
                    />
                  </Col>
                  <Col>
                    <Form.Label>Timeout (ms)</Form.Label>
                    <Form.Control
                      type="number"
                      min={1}
                      value={timeoutMs}
                      onChange={(event) => setTimeoutMs(Number(event.target.value))}
                    />
                  </Col>
                </Row>
                <Row className="g-2 mt-2">
                  <Col>
                    <Form.Check
                      type="switch"
                      label="Debug mode"
                      checked={debugEnabled}
                      onChange={(event) => setDebugEnabled(event.target.checked)}
                    />
                  </Col>
                  <Col>
                    <Form.Check
                      type="switch"
                      label="Rerank enabled"
                      checked={rerankEnabled}
                      onChange={(event) => setRerankEnabled(event.target.checked)}
                    />
                  </Col>
                </Row>
                <Form.Group className="mt-3">
                  <Form.Label>Candidates (JSON array)</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={10}
                    value={candidatesJson}
                    onChange={(event) => setCandidatesJson(event.target.value)}
                  />
                </Form.Group>
                <Button type="submit" className="mt-3" disabled={loading}>
                  {loading ? <Spinner size="sm" className="me-2" /> : null}
                  Run rerank
                </Button>
              </Card.Body>
            </Card>
          </Col>
          <Col lg={8}>
            <Card className="mb-3">
              <Card.Body>
                <Card.Title>Response</Card.Title>
                {error ? (
                  <Alert variant="danger">
                    <div className="fw-semibold">Request failed</div>
                    <div>Status: {error.status || "N/A"} ({error.statusText})</div>
                    <pre className="mb-0 mt-2">{prettyJson(error.body)}</pre>
                  </Alert>
                ) : null}
                <pre className="mb-0">{prettyJson(response)}</pre>
              </Card.Body>
            </Card>
            <Card>
              <Card.Body>
                <Card.Title>Curl Preview</Card.Title>
                <pre className="mb-0">{curlPreview}</pre>
              </Card.Body>
            </Card>
          </Col>
        </Row>
      </Form>
    </div>
  );
}
