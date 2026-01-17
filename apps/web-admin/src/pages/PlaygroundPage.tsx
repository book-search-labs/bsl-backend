import { useMemo, useState } from "react";
import {
    Button,
    Card,
    Col,
    Form,
    InputGroup,
    Row,
    Tab,
    Tabs,
    ToggleButton,
    ButtonGroup,
} from "react-bootstrap";

type Flags = {
    useQsPrepare: boolean;
    useQsEnhance: boolean;
    retrievalMode: "LEXICAL" | "HYBRID";
    useRerank: boolean;
    debug: boolean;
};

export default function PlaygroundPage() {
    const [q, setQ] = useState("해리포터 1");
    const [flags, setFlags] = useState<Flags>({
        useQsPrepare: true,
        useQsEnhance: false,
        retrievalMode: "HYBRID",
        useRerank: false,
        debug: true,
    });

    // 임시 더미 (백엔드 붙이면 fetch로 교체)
    const mock = useMemo(() => {
        return {
            items: [
                { id: "1", title: "해리 포터와 마법사의 돌", author: "J.K. 롤링", publisher: "문학수첩" },
                { id: "2", title: "해리 포터와 비밀의 방", author: "J.K. 롤링", publisher: "문학수첩" },
            ],
            debug: {
                queryContext: { normalized: q.trim(), flags },
                esDsl: { query: { match: { title: q } } },
                latencyMs: { qsPrepare: 6, search: 12, opensearch: 40, total: 58 },
                trace: ["normalize: applied", "hybrid: enabled"],
            },
        };
    }, [q, flags]);

    const onSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        // TODO: POST /api/search 로 연결 (지금은 mock)
        console.log("search", { q, flags });
    };

    return (
        <>
            <h3 className="mb-3">Playground</h3>

            <Card className="shadow-sm mb-3">
                <Card.Body>
                    <Form onSubmit={onSubmit}>
                        <Row className="g-2 align-items-center">
                            <Col xs={12} lg={6}>
                                <InputGroup>
                                    <InputGroup.Text>
                                        <i className="bi bi-search" />
                                    </InputGroup.Text>
                                    <Form.Control
                                        value={q}
                                        onChange={(e) => setQ(e.target.value)}
                                        placeholder="검색어를 입력하세요"
                                    />
                                    <Button type="submit" variant="primary">
                                        Search
                                    </Button>
                                </InputGroup>
                            </Col>

                            <Col xs={12} lg={6}>
                                <div className="d-flex flex-wrap gap-2 justify-content-lg-end">
                                    <ToggleButton
                                        id="qs-prepare"
                                        type="checkbox"
                                        variant={flags.useQsPrepare ? "success" : "outline-secondary"}
                                        checked={flags.useQsPrepare}
                                        value="1"
                                        onChange={(e) => setFlags((p) => ({ ...p, useQsPrepare: e.currentTarget.checked }))}
                                    >
                                        QS Prepare
                                    </ToggleButton>

                                    <ToggleButton
                                        id="qs-enhance"
                                        type="checkbox"
                                        variant={flags.useQsEnhance ? "success" : "outline-secondary"}
                                        checked={flags.useQsEnhance}
                                        value="1"
                                        onChange={(e) => setFlags((p) => ({ ...p, useQsEnhance: e.currentTarget.checked }))}
                                    >
                                        QS Enhance
                                    </ToggleButton>

                                    <ButtonGroup>
                                        <ToggleButton
                                            id="lexical"
                                            type="radio"
                                            variant={flags.retrievalMode === "LEXICAL" ? "primary" : "outline-primary"}
                                            name="retrieval"
                                            value="LEXICAL"
                                            checked={flags.retrievalMode === "LEXICAL"}
                                            onChange={() => setFlags((p) => ({ ...p, retrievalMode: "LEXICAL" }))}
                                        >
                                            Lexical
                                        </ToggleButton>
                                        <ToggleButton
                                            id="hybrid"
                                            type="radio"
                                            variant={flags.retrievalMode === "HYBRID" ? "primary" : "outline-primary"}
                                            name="retrieval"
                                            value="HYBRID"
                                            checked={flags.retrievalMode === "HYBRID"}
                                            onChange={() => setFlags((p) => ({ ...p, retrievalMode: "HYBRID" }))}
                                        >
                                            Hybrid
                                        </ToggleButton>
                                    </ButtonGroup>

                                    <ToggleButton
                                        id="rerank"
                                        type="checkbox"
                                        variant={flags.useRerank ? "danger" : "outline-secondary"}
                                        checked={flags.useRerank}
                                        value="1"
                                        onChange={(e) => setFlags((p) => ({ ...p, useRerank: e.currentTarget.checked }))}
                                    >
                                        Rerank
                                    </ToggleButton>
                                </div>
                            </Col>
                        </Row>
                    </Form>
                </Card.Body>
            </Card>

            <Row className="g-3">
                {/* Results */}
                <Col xs={12} xl={7}>
                    <Card className="shadow-sm">
                        <Card.Header className="fw-semibold">Results</Card.Header>
                        <Card.Body>
                            {mock.items.map((it) => (
                                <div key={it.id} className="border rounded p-2 mb-2 bg-white">
                                    <div className="fw-semibold">{it.title}</div>
                                    <div className="text-muted small">
                                        {it.author} · {it.publisher}
                                    </div>
                                </div>
                            ))}
                        </Card.Body>
                    </Card>
                </Col>

                {/* Debug */}
                <Col xs={12} xl={5}>
                    <Card className="shadow-sm">
                        <Card.Header className="fw-semibold">Debug</Card.Header>
                        <Card.Body>
                            <Tabs defaultActiveKey="context" className="mb-3">
                                <Tab eventKey="context" title="QueryContext">
                  <pre className="bg-dark text-light p-2 rounded small overflow-auto" style={{ maxHeight: 260 }}>
                    {JSON.stringify(mock.debug.queryContext, null, 2)}
                  </pre>
                                </Tab>
                                <Tab eventKey="dsl" title="ES DSL">
                  <pre className="bg-dark text-light p-2 rounded small overflow-auto" style={{ maxHeight: 260 }}>
                    {JSON.stringify(mock.debug.esDsl, null, 2)}
                  </pre>
                                </Tab>
                                <Tab eventKey="latency" title="Latency">
                  <pre className="bg-dark text-light p-2 rounded small overflow-auto" style={{ maxHeight: 260 }}>
                    {JSON.stringify(mock.debug.latencyMs, null, 2)}
                  </pre>
                                </Tab>
                                <Tab eventKey="trace" title="Trace">
                  <pre className="bg-dark text-light p-2 rounded small overflow-auto" style={{ maxHeight: 260 }}>
                    {JSON.stringify(mock.debug.trace, null, 2)}
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