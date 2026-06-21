from fastapi.testclient import TestClient

from app import create_app
from retrieval.models import Document
from retrieval.store import DocumentStore


def _client() -> TestClient:
    store = DocumentStore(
        [
            Document(id="alpha-1", tenant_id="alpha", score=0.90, text="alpha refund policy details"),
            Document(id="alpha-2", tenant_id="alpha", score=0.55, text="alpha refund timelines"),
            Document(id="beta-1", tenant_id="beta", score=0.99, text="beta refund policy details"),
        ]
    )
    return TestClient(create_app(store))


def test_health_returns_ok():
    response = _client().get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_search_returns_only_the_requested_tenants_documents():
    response = _client().post(
        "/search", headers={"X-Tenant-ID": "alpha"}, json={"query": "refund"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == "alpha"
    assert body["query"] == "refund"
    # beta-1 has the highest score and matches the query, but is never returned.
    assert [hit["id"] for hit in body["results"]] == ["alpha-1", "alpha-2"]


def test_search_for_a_different_tenant_returns_that_tenants_documents():
    response = _client().post(
        "/search", headers={"X-Tenant-ID": "beta"}, json={"query": "refund"}
    )

    assert [hit["id"] for hit in response.json()["results"]] == ["beta-1"]


def test_search_requires_the_tenant_header():
    response = _client().post("/search", json={"query": "refund"})

    assert response.status_code == 400
