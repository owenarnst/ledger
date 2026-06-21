"""HTTP layer for the document search service.

Exposes a health check and a single tenant-scoped search endpoint. The tenant
is taken from the ``X-Tenant-ID`` request header; the request body carries only
the query. The corpus is a fixed in-memory store, so the service is fully
deterministic and needs no network access, database, or secrets to run.

This demonstrates tenant-scoped retrieval. It is not a complete authorization
boundary: the tenant header is trusted as supplied.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from retrieval.models import Document
from retrieval.pipeline import search
from retrieval.store import DocumentStore


class SearchRequest(BaseModel):
    """Body of a search request. The tenant comes from a header, not here."""

    query: str = Field(min_length=1)


def default_store() -> DocumentStore:
    """Construct the fixed in-memory corpus the service searches."""
    return DocumentStore(
        [
            Document(
                id="alpha-billing",
                tenant_id="alpha",
                score=0.92,
                text="Alpha billing: a refund is issued to the original payment method within five business days.",
            ),
            Document(
                id="alpha-onboarding",
                tenant_id="alpha",
                score=0.74,
                text="Alpha onboarding guide: invite teammates and configure your first project workspace.",
            ),
            Document(
                id="alpha-security",
                tenant_id="alpha",
                score=0.41,
                text="Alpha security overview: documents are encrypted in transit and at rest.",
            ),
            Document(
                id="beta-billing",
                tenant_id="beta",
                score=0.95,
                text="Beta billing: a refund requires manager approval before the payment is reversed.",
            ),
            Document(
                id="beta-onboarding",
                tenant_id="beta",
                score=0.68,
                text="Beta onboarding guide: import existing documents and set retention policies.",
            ),
            Document(
                id="beta-support",
                tenant_id="beta",
                score=0.20,
                text="Beta support: weekday support hours and contact details.",
            ),
        ]
    )


def create_app(store: DocumentStore) -> FastAPI:
    """Build a FastAPI app that searches ``store``."""
    app = FastAPI(title="Docs Search API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/search")
    def search_documents(
        request: SearchRequest,
        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
    ) -> dict[str, Any]:
        if not x_tenant_id:
            raise HTTPException(status_code=400, detail="X-Tenant-ID header is required")
        response = search(store, request.query, tenant_id=x_tenant_id)
        return asdict(response)

    return app


app = create_app(default_store())
