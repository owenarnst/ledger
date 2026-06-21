"""Core data models for the retrieval pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Document:
    """A single retrievable chunk in the shared corpus.

    Documents from every tenant live together in one store; ``tenant_id``
    is what lets the pipeline scope results back down to a single caller.
    ``score`` is a precomputed relevance signal used by reranking.
    """

    id: str
    tenant_id: str
    score: float
    text: str
