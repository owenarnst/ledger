from retrieval.rerank import Document, visible_documents_for_tenant


def test_filters_documents_by_tenant():
    docs = [
        Document(id="a", tenant_id="alpha", score=0.9, text="Alpha docs"),
        Document(id="b", tenant_id="beta", score=0.8, text="Beta docs"),
    ]

    visible = visible_documents_for_tenant(docs, "alpha")

    assert [doc.id for doc in visible] == ["a"]

