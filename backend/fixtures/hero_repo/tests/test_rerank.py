from retrieval.models import Document
from retrieval.rerank import (
    MINIMUM_RERANK_SCORE,
    apply_confidence_cutoff,
    rerank,
    visible_documents_for_tenant,
)


def _doc(id: str, score: float, text: str = "text", tenant_id: str = "alpha") -> Document:
    return Document(id=id, tenant_id=tenant_id, score=score, text=text)


def test_rerank_orders_by_score_descending():
    ranked = rerank([_doc("a", 0.2), _doc("b", 0.9), _doc("c", 0.5)])

    assert [doc.id for doc in ranked] == ["b", "c", "a"]


def test_rerank_breaks_ties_by_id_for_determinism():
    # Equal scores must produce a stable, input-order-independent ranking.
    ranked = rerank([_doc("c", 0.7), _doc("a", 0.7), _doc("b", 0.7)])

    assert [doc.id for doc in ranked] == ["a", "b", "c"]


def test_confidence_cutoff_keeps_documents_at_or_above_threshold():
    docs = [
        _doc("keep", MINIMUM_RERANK_SCORE),
        _doc("drop", MINIMUM_RERANK_SCORE - 0.01),
    ]

    survivors = apply_confidence_cutoff(docs)

    assert [doc.id for doc in survivors] == ["keep"]


def test_filters_documents_by_tenant():
    documents = [
        Document(id="a1", tenant_id="alpha", score=0.9, text="alpha quarterly report"),
        Document(id="b1", tenant_id="beta", score=0.8, text="beta quarterly report"),
        Document(id="a2", tenant_id="alpha", score=0.7, text="alpha onboarding guide"),
    ]

    visible = visible_documents_for_tenant(documents, "alpha")

    assert [doc.id for doc in visible] == ["a1", "a2"]
    assert all(doc.tenant_id == "alpha" for doc in visible)
