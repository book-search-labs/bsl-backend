from fastapi.testclient import TestClient

from app.main import app


def test_prepare_parses_author_and_residual_text():
    client = TestClient(app)
    response = client.post("/query/prepare", json={"query": {"raw": "author:김영하 데미안"}})
    assert response.status_code == 200
    data = response.json()

    assert data["meta"]["schemaVersion"] == "qc.v1.1"
    assert data["understanding"]["entities"]["author"] == ["김영하"]
    assert data["understanding"]["constraints"]["residualText"] == "데미안"
    assert data["query"]["final"] == "데미안"
    assert data["query"]["finalSource"] == "explicit_residual"


def test_prepare_parses_isbn_and_adds_filter():
    client = TestClient(app)
    response = client.post("/query/prepare", json={"query": {"raw": "isbn:978-89-349-1234-5"}})
    assert response.status_code == 200
    data = response.json()

    filters = data["retrievalHints"]["filters"]
    assert len(filters) == 1
    isbn_constraint = filters[0]["and"][0]
    assert isbn_constraint["logicalField"] == "isbn13"
    assert isbn_constraint["op"] == "eq"
    assert isinstance(isbn_constraint["value"], str)
    assert isbn_constraint["value"].isdigit()
