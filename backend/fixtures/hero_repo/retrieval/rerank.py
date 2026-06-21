"""Deterministic reranking and the rerank confidence policy.

Reranking takes the candidate documents returned by retrieval and imposes a
stable order, then drops anything below a named confidence threshold so weak
matches never reach context construction.
"""

from __future__ import annotations

from .models import Document

# Documents scoring below this confidence threshold are dropped before context
# construction. Named here so the policy lives in one place rather than as a
# bare literal scattered through the pipeline.
MINIMUM_RERANK_SCORE = 0.30


def visible_documents_for_tenant(
    documents: list[Document], tenant_id: str
) -> list[Document]:
    """Return only the documents that belong to ``tenant_id``."""
    return [doc for doc in documents if doc.tenant_id == tenant_id]


def rerank(documents: list[Document]) -> list[Document]:
    """Order documents by descending score.

    Ties are broken by ``id`` so the ordering is fully deterministic and does
    not depend on the order candidates happened to arrive in.
    """
    return sorted(documents, key=lambda doc: (-doc.score, doc.id))


def apply_confidence_cutoff(
    documents: list[Document], *, minimum_score: float = MINIMUM_RERANK_SCORE
) -> list[Document]:
    """Drop documents whose score is below ``minimum_score``."""
    return [doc for doc in documents if doc.score >= minimum_score]
