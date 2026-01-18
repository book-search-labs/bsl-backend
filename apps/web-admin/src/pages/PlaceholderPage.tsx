import { Card } from "react-bootstrap";

export default function PlaceholderPage({ title }: { title: string }) {
  return (
    <>
      <h3 className="mb-3">{title}</h3>
      <Card className="shadow-sm">
        <Card.Body className="text-muted">TODO: implement</Card.Body>
      </Card>
    </>
  );
}
