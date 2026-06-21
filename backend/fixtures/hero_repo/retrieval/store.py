"""In-memory document store and candidate retrieval.

The store holds the entire shared corpus across all tenants. Candidate
retrieval is deliberately tenant-blind: it matches on query terms only, and it
is the pipeline's job to scope the candidates down to the requesting tenant.
"""

from __future__ import annotations

import re

from .models import Document

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Split text into lowercase alphanumeric tokens."""
    return _TOKEN_PATTERN.findall(text.lower())


class DocumentStore:
    """A shared, in-memory corpus queried by lexical term overlap."""

    def __init__(self, documents: list[Document]) -> None:
        self._documents = list(documents)

    def candidates(self, query: str) -> list[Document]:
        """Return documents sharing at least one token with ``query``.

        Candidates span every tenant in the corpus; narrowing them to a single
        tenant happens downstream in the pipeline.
        """
        query_tokens = set(tokenize(query))
        if not query_tokens:
            return []
        return [
            document
            for document in self._documents
            if query_tokens & set(tokenize(document.text))
        ]
