from retrieval.context import (
    MAX_EXCERPT_CHARACTERS,
    excerpt_for,
    pack_context,
)
from retrieval.models import Document


def _doc(id: str, text: str, score: float = 0.9, tenant_id: str = "alpha") -> Document:
    return Document(id=id, tenant_id=tenant_id, score=score, text=text)


def test_pack_context_preserves_reranked_order():
    docs = [_doc("a", "aaa"), _doc("b", "bbb"), _doc("c", "ccc")]

    packed = pack_context(docs, char_budget=100)

    assert [doc.id for doc in packed] == ["a", "b", "c"]


def test_pack_context_stops_at_character_budget():
    docs = [_doc("a", "x" * 40), _doc("b", "y" * 40), _doc("c", "z" * 40)]

    # Budget fits the first two excerpts (80 chars) but not the third (120).
    packed = pack_context(docs, char_budget=80)

    assert [doc.id for doc in packed] == ["a", "b"]


def test_excerpt_for_truncates_to_max_excerpt():
    doc = _doc("a", "x" * (MAX_EXCERPT_CHARACTERS + 50))

    assert len(excerpt_for(doc)) == MAX_EXCERPT_CHARACTERS


def test_pack_context_caps_each_documents_contribution():
    # No single document may dominate the window: a document far larger than the
    # per-excerpt cap must still count for at most MAX_EXCERPT_CHARACTERS, leaving
    # room for the next document instead of consuming the whole budget itself.
    big = _doc("big", "x" * 1000)
    small = _doc("small", "y" * 50)

    packed = pack_context([big, small], char_budget=400, max_excerpt=MAX_EXCERPT_CHARACTERS)

    assert [doc.id for doc in packed] == ["big", "small"]
