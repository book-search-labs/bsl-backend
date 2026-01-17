import { Card, Col, Row } from "react-bootstrap";

export default function DashboardPage() {
    return (
        <>
            <h3 className="mb-3">Dashboard</h3>

            <Row className="g-3">
                <Col xs={12} md={6} xl={3}>
                    <Card className="shadow-sm">
                        <Card.Body>
                            <div className="d-flex justify-content-between">
                                <div>
                                    <div className="text-muted small">New Queries</div>
                                    <div className="fs-3 fw-bold">150</div>
                                </div>
                                <i className="bi bi-search fs-2 text-primary" />
                            </div>
                        </Card.Body>
                    </Card>
                </Col>

                <Col xs={12} md={6} xl={3}>
                    <Card className="shadow-sm">
                        <Card.Body>
                            <div className="d-flex justify-content-between">
                                <div>
                                    <div className="text-muted small">Avg Latency</div>
                                    <div className="fs-3 fw-bold">44ms</div>
                                </div>
                                <i className="bi bi-speedometer2 fs-2 text-success" />
                            </div>
                        </Card.Body>
                    </Card>
                </Col>

                <Col xs={12} md={6} xl={3}>
                    <Card className="shadow-sm">
                        <Card.Body>
                            <div className="d-flex justify-content-between">
                                <div>
                                    <div className="text-muted small">Zero Results</div>
                                    <div className="fs-3 fw-bold">12</div>
                                </div>
                                <i className="bi bi-exclamation-triangle fs-2 text-warning" />
                            </div>
                        </Card.Body>
                    </Card>
                </Col>

                <Col xs={12} md={6} xl={3}>
                    <Card className="shadow-sm">
                        <Card.Body>
                            <div className="d-flex justify-content-between">
                                <div>
                                    <div className="text-muted small">Rerank On</div>
                                    <div className="fs-3 fw-bold">65%</div>
                                </div>
                                <i className="bi bi-lightning-charge fs-2 text-danger" />
                            </div>
                        </Card.Body>
                    </Card>
                </Col>
            </Row>
        </>
    );
}