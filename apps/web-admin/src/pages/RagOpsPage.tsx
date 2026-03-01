import { useCallback, useState } from "react";
import { Alert, Button, Card, Col, Form, Row, Spinner } from "react-bootstrap";
import { fetchJson } from "../lib/api";
import { resolveAdminApiMode, resolveBffBaseUrl, routeRequest } from "../lib/apiRouter";

const joinUrl = (base: string, path: string) => `${base.replace(/\/$/, "")}${path}`;

export default function RagOpsPage() {
  const apiMode = resolveAdminApiMode();
  const bffBaseUrl = resolveBffBaseUrl();

  const [uploading, setUploading] = useState(false);
  const [reindexing, setReindexing] = useState(false);
  const [rollingBack, setRollingBack] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  const [sourceDir, setSourceDir] = useState("data/rag/docs");
  const [docsIndex, setDocsIndex] = useState("docs_doc_v1_YYYYMMDD_001");
  const [vecIndex, setVecIndex] = useState("docs_vec_v1_YYYYMMDD_001");
  const [note, setNote] = useState("");

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

  const handleUpload = async (file?: File | null) => {
    if (!file) return;
    setUploading(true);
    setError(null);
    const formData = new FormData();
    formData.append("file", file);
    const { result } = await callBff("/admin/rag/docs/upload", {
      method: "POST",
      body: formData,
    });
    if (!result.ok) {
      setError(`Upload failed (${result.status || result.statusText}).`);
    }
    setUploading(false);
  };

  const handleReindex = async () => {
    setReindexing(true);
    setError(null);
    const { result } = await callBff("/admin/rag/index/reindex", {
      method: "POST",
      body: JSON.stringify({ source_dir: sourceDir, docs_index: docsIndex, vec_index: vecIndex, note }),
      headers: { "Content-Type": "application/json" },
    });
    if (!result.ok) {
      setError(`Reindex task failed (${result.status || result.statusText}).`);
    }
    setReindexing(false);
  };

  const handleRollback = async () => {
    setRollingBack(true);
    setError(null);
    const { result } = await callBff("/admin/rag/index/rollback", {
      method: "POST",
      body: JSON.stringify({ docs_index: docsIndex, vec_index: vecIndex, note }),
      headers: { "Content-Type": "application/json" },
    });
    if (!result.ok) {
      setError(`Rollback task failed (${result.status || result.statusText}).`);
    }
    setRollingBack(false);
  };

  return (
    <div className="d-flex flex-column gap-3">
      {error ? <Alert variant="danger">{error}</Alert> : null}
      <Row className="g-3">
        <Col xl={12}>
          <Card>
            <Card.Header>
              <strong>Doc Upload</strong>
            </Card.Header>
            <Card.Body className="d-flex flex-column gap-3">
              <Form.Group controlId="rag-upload">
                <Form.Label>Upload a document (md/txt/html)</Form.Label>
                <Form.Control
                  type="file"
                  onChange={(event) => {
                    const input = event.target as HTMLInputElement;
                    setUploadFile(input.files?.[0] ?? null);
                  }}
                />
              </Form.Group>
              <Button
                variant="primary"
                disabled={uploading || !uploadFile}
                onClick={() => handleUpload(uploadFile)}
              >
                {uploading ? <Spinner size="sm" /> : "Upload"}
              </Button>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Row className="g-3">
        <Col xl={6}>
          <Card>
            <Card.Header>
              <strong>Reindex</strong>
            </Card.Header>
            <Card.Body className="d-flex flex-column gap-2">
              <Form.Control
                placeholder="Source dir"
                value={sourceDir}
                onChange={(event) => setSourceDir(event.target.value)}
              />
              <Form.Control
                placeholder="Docs index"
                value={docsIndex}
                onChange={(event) => setDocsIndex(event.target.value)}
              />
              <Form.Control
                placeholder="Vec index"
                value={vecIndex}
                onChange={(event) => setVecIndex(event.target.value)}
              />
              <Form.Control
                placeholder="Note"
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
              <Button onClick={handleReindex} disabled={reindexing}>
                {reindexing ? <Spinner size="sm" /> : "Create Reindex Task"}
              </Button>
            </Card.Body>
          </Card>
        </Col>
        <Col xl={6}>
          <Card>
            <Card.Header>
              <strong>Rollback</strong>
            </Card.Header>
            <Card.Body className="d-flex flex-column gap-2">
              <Form.Control
                placeholder="Docs index"
                value={docsIndex}
                onChange={(event) => setDocsIndex(event.target.value)}
              />
              <Form.Control
                placeholder="Vec index"
                value={vecIndex}
                onChange={(event) => setVecIndex(event.target.value)}
              />
              <Form.Control
                placeholder="Note"
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
              <Button variant="outline-danger" onClick={handleRollback} disabled={rollingBack}>
                {rollingBack ? <Spinner size="sm" /> : "Create Rollback Task"}
              </Button>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
