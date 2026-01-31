import { useCallback, useState } from "react";
import { Alert, Button, Card, Col, Form, Row, Spinner } from "react-bootstrap";
import { fetchJson } from "../lib/api";
import { resolveAdminApiMode, resolveBffBaseUrl, routeRequest } from "../lib/apiRouter";

const joinUrl = (base: string, path: string) => `${base.replace(/\/$/, "")}${path}`;

export default function RagEvalPage() {
  const apiMode = resolveAdminApiMode();
  const bffBaseUrl = resolveBffBaseUrl();

  const [questionId, setQuestionId] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [evidence, setEvidence] = useState("");
  const [rating, setRating] = useState("ok");
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

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

  const handleSubmit = useCallback(async () => {
    if (!question.trim()) return;
    setSaving(true);
    setError(null);
    setSuccess(false);

    const { result } = await callBff("/admin/rag/eval/label", {
      method: "POST",
      body: JSON.stringify({
        question_id: questionId,
        question,
        answer,
        evidence,
        rating,
        comment,
      }),
      headers: { "Content-Type": "application/json" },
    });

    if (!result.ok) {
      setError(`Save failed (${result.status || result.statusText}).`);
    } else {
      setSuccess(true);
      setQuestion("");
      setAnswer("");
      setEvidence("");
      setComment("");
    }
    setSaving(false);
  }, [answer, callBff, comment, evidence, question, questionId, rating]);

  return (
    <div className="d-flex flex-column gap-3">
      <Row className="g-3">
        <Col xl={12}>
          <Card>
            <Card.Header>
              <strong>RAG Eval Labeling</strong>
            </Card.Header>
            <Card.Body className="d-flex flex-column gap-3">
              {error ? <Alert variant="danger">{error}</Alert> : null}
              {success ? <Alert variant="success">Saved</Alert> : null}
              <Form.Control
                placeholder="Question ID"
                value={questionId}
                onChange={(event) => setQuestionId(event.target.value)}
              />
              <Form.Control
                placeholder="Question"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
              />
              <Form.Control
                as="textarea"
                rows={3}
                placeholder="Answer"
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
              />
              <Form.Control
                as="textarea"
                rows={3}
                placeholder="Evidence / citations"
                value={evidence}
                onChange={(event) => setEvidence(event.target.value)}
              />
              <Form.Select value={rating} onChange={(event) => setRating(event.target.value)}>
                <option value="ok">OK</option>
                <option value="insufficient">Insufficient evidence</option>
                <option value="hallucination">Hallucination</option>
              </Form.Select>
              <Form.Control
                placeholder="Comment"
                value={comment}
                onChange={(event) => setComment(event.target.value)}
              />
              <Button onClick={handleSubmit} disabled={saving}>
                {saving ? <Spinner size="sm" /> : "Save Label"}
              </Button>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
