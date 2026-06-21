"""Bounded context-window packing.

After reranking and the confidence cutoff, the surviving documents are packed
into a context window of bounded size. Packing walks the documents in reranked
order and keeps adding them until the next one would exceed the character
budget, so the result is always a rank-ordered prefix of the input that fits
the window.
"""

from __future__ import annotations

from .models import Document

# Total size of the packed context window, in characters.
CONTEXT_CHARACTER_BUDGET = 600
# No single excerpt may contribute more than this many characters, so one large
# document cannot dominate the window or overflow it on its own.
MAX_EXCERPT_CHARACTERS = 200


def excerpt_for(document: Document) -> str:
    """Return the bounded excerpt used to represent a document in results."""
    return document.text[:MAX_EXCERPT_CHARACTERS]


def pack_context(
    documents: list[Document],
    *,
    char_budget: int = CONTEXT_CHARACTER_BUDGET,
    max_excerpt: int = MAX_EXCERPT_CHARACTERS,
) -> list[Document]:
    """Select the rank-ordered prefix of ``documents`` that fits the budget.

    ``documents`` is expected to already be in reranked order. Each document
    contributes at most ``max_excerpt`` characters to the running total, and
    packing stops at the first document that would push the total past
    ``char_budget``.
    """
    packed: list[Document] = []
    used = 0
    for document in documents:
        cost = min(len(document.text), max_excerpt)
        if used + cost > char_budget:
            break
        packed.append(document)
        used += cost
    return packed
