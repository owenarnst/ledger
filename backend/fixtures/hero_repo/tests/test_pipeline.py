from retrieval.models import Document
from retrieval.pipeline import deduplicate, search
from retrieval.store import DocumentStore


def _doc(id: str, text: str, score: float = 0.9, tenant_id: str = "alpha") -> Document:
    return Document(id=id, tenant_id=tenant_id, score=score, text=text)


def test_store_returns_only_term_matching_candidates():
    store = DocumentStore(
        [
            _doc("a", "the quick brown fox"),
            _doc("b", "lazy dogs sleep"),
        ]
    )

    candidates = store.candidates("fox")

    assert [doc.id for doc in candidates] == ["a"]


def test_deduplicate_keeps_first_occurrence_of_each_id():
    docs = [
        _doc("a", "first", score=0.9),
        _doc("a", "duplicate", score=0.5),
        _doc("b", "other"),
    ]

    unique = deduplicate(docs)

    assert [doc.id for doc in unique] == ["a", "b"]
    assert unique[0].text == "first"


def test_search_returns_reranked_excerpts_above_the_cutoff():
    store = DocumentStore(
        [
            _doc("low", "alpha signal", score=0.1),
            _doc("high", "alpha signal", score=0.95),
            _doc("mid", "alpha signal", score=0.6),
        ]
    )

    response = search(store, "alpha", tenant_id="alpha")

    # "low" (0.1) is below the 0.30 confidence cutoff and is dropped.
    assert [hit.id for hit in response.results] == ["high", "mid"]
    assert response.query == "alpha"
    assert all(hit.excerpt for hit in response.results)


def test_search_never_returns_another_tenants_documents():
    # Both documents match the query and belong to different tenants; the
    # higher-scoring one is beta's, so only tenant scoping keeps it out.
    store = DocumentStore(
        [
            _doc("alpha-1", "shared refund policy", score=0.90, tenant_id="alpha"),
            _doc("beta-1", "shared refund policy", score=0.95, tenant_id="beta"),
        ]
    )

    response = search(store, "refund", tenant_id="alpha")

    assert [hit.id for hit in response.results] == ["alpha-1"]
    assert response.tenant_id == "alpha"
