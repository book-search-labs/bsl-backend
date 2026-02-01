import { useState } from "react";
import { Alert, Button, Card, Form } from "react-bootstrap";
import { DEFAULT_SETTINGS, loadAdminSettings, resetAdminSettings, saveAdminSettings } from "../lib/adminSettings";

export default function SettingsPage() {
  const [settings, setSettings] = useState(loadAdminSettings());
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    const next = saveAdminSettings(settings);
    setSettings(next);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  const handleReset = () => {
    const next = resetAdminSettings();
    setSettings(next);
  };

  return (
    <div className="d-flex flex-column gap-3">
      <div>
        <h3 className="mb-1">Settings</h3>
        <p className="text-muted mb-0">Configure default admin search behavior.</p>
      </div>

      {saved ? <Alert variant="success">Settings saved.</Alert> : null}

      <Card className="shadow-sm">
        <Card.Body>
          <Form className="d-flex flex-column gap-3">
            <Form.Group>
              <Form.Label>Default size</Form.Label>
              <Form.Control
                type="number"
                min={1}
                max={100}
                value={settings.defaultSize}
                onChange={(event) =>
                  setSettings((prev) => ({ ...prev, defaultSize: Number(event.target.value) }))
                }
              />
              <Form.Text className="text-muted">Used as the default result size in compare tools.</Form.Text>
            </Form.Group>
            <Form.Group>
              <Form.Label>Timeout (ms)</Form.Label>
              <Form.Control
                type="number"
                min={100}
                max={60000}
                value={settings.timeoutMs}
                onChange={(event) =>
                  setSettings((prev) => ({ ...prev, timeoutMs: Number(event.target.value) }))
                }
              />
            </Form.Group>
            <Form.Check
              type="switch"
              label="Enable vector search by default"
              checked={settings.defaultVector}
              onChange={(event) =>
                setSettings((prev) => ({ ...prev, defaultVector: event.target.checked }))
              }
            />
            <Form.Check
              type="switch"
              label="Enable debug mode by default"
              checked={settings.defaultDebug}
              onChange={(event) =>
                setSettings((prev) => ({ ...prev, defaultDebug: event.target.checked }))
              }
            />
            <div className="d-flex gap-2">
              <Button variant="primary" onClick={handleSave}>
                Save settings
              </Button>
              <Button variant="outline-secondary" onClick={handleReset}>
                Reset to default ({DEFAULT_SETTINGS.defaultSize})
              </Button>
            </div>
          </Form>
        </Card.Body>
      </Card>
    </div>
  );
}
