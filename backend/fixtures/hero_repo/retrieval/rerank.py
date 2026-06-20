from dataclasses import dataclass


@dataclass(frozen=True)
class Document:
    id: str
    tenant_id: str
    score: float
    text: str


def visible_documents_for_tenant(documents: list[Document], tenant_id: str) -> list[Document]:
    return [doc for doc in documents if doc.tenant_id == tenant_id]

