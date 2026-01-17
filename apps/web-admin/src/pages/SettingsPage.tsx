import { Card, Form } from "react-bootstrap";

export default function SettingsPage() {
    return (
        <>
            <h3 className="mb-3">Settings</h3>
            <Card className="shadow-sm">
                <Card.Body>
                    <Form>
                        <Form.Group className="mb-3">
                            <Form.Label>Default size</Form.Label>
                            <Form.Control type="number" defaultValue={10} />
                        </Form.Group>
                        <Form.Group className="mb-3">
                            <Form.Label>Timeout (ms)</Form.Label>
                            <Form.Control type="number" defaultValue={1200} />
                        </Form.Group>
                    </Form>
                </Card.Body>
            </Card>
        </>
    );
}