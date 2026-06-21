"""The end-to-end retrieval pipeline.

A search request flows through retrieval, reranking, duplicate resolution, the
confidence cutoff, and finally context packing before results are returned.
"""

from __future__ import annotations

from dataclasses import dataclass

from .context import excerpt_for, pack_context
from .models import Document
from .rerank import apply_confidence_cutoff, rerank, visible_documents_for_tenant
from .store import DocumentStore


@dataclass(frozen=True)
class SearchHit:
    """A single document returned to the caller."""

    id: str
    score: float
    excerpt: str


@dataclass(frozen=True)
class SearchResponse:
    """The full result of a search."""

    tenant_id: str
    query: str
    results: list[SearchHit]


def deduplicate(documents: list[Document]) -> list[Document]:
    """Collapse duplicate chunks, keeping the first occurrence of each id.

    The shared corpus can surface the same chunk more than once. Duplicates are
    resolved here, before the context window's size limit is applied, so the
    limit is spent on distinct documents. Because this runs after reranking, the
    first occurrence of an id is also its highest-scoring one.
    """
    seen: set[str] = set()
    unique: list[Document] = []
    for document in documents:
        if document.id in seen:
            continue
        seen.add(document.id)
        unique.append(document)
    return unique


def search(store: DocumentStore, query: str, tenant_id: str) -> SearchResponse:
    """Run the retrieval pipeline for ``query`` on behalf of ``tenant_id``."""
    candidates = store.candidates(query)
    scoped = visible_documents_for_tenant(candidates, tenant_id)
    ranked = rerank(scoped)
    deduped = deduplicate(ranked)
    confident = apply_confidence_cutoff(deduped)
    packed = pack_context(confident)
    hits = [
        SearchHit(id=document.id, score=document.score, excerpt=excerpt_for(document))
        for document in packed
    ]
    return SearchResponse(tenant_id=tenant_id, query=query, results=hits)
