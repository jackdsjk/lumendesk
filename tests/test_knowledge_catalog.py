import threading

from tooling.knowledge_base import KnowledgeBase


class CatalogCollection:
    def __init__(self):
        self.rows = {}

    def upsert(self, *, ids, documents, metadatas):
        for row_id, document, metadata in zip(ids, documents, metadatas):
            self.rows[row_id] = (document, metadata)

    def get(self, where=None, include=None):
        where = where or {}
        rows = [
            (row_id, document, metadata)
            for row_id, (document, metadata) in self.rows.items()
            if all(metadata.get(key) == value for key, value in where.items())
        ]
        result = {
            "ids": [row_id for row_id, _, _ in rows],
            "metadatas": [metadata for _, _, metadata in rows],
        }
        if include and "documents" in include:
            result["documents"] = [document for _, document, _ in rows]
        return result

    def delete(self, ids):
        for row_id in ids:
            self.rows.pop(row_id, None)


def make_kb():
    kb = KnowledgeBase.__new__(KnowledgeBase)
    kb._write_lock = threading.RLock()
    kb._collection = CatalogCollection()
    return kb


def test_list_documents_reassembles_chunks_and_filters_unpublished():
    kb = make_kb()
    kb.add_documents([
        {
            "document_id": "published",
            "title": "退款政策",
            "content": "第一段。第二段。",
            "product_id": "halex-support-cloud",
            "approval_status": "approved",
            "publication_status": "published",
        },
        {
            "document_id": "draft",
            "title": "草稿政策",
            "content": "仅供审核。",
            "product_id": "halex-support-cloud",
        },
    ])

    documents = kb.list_documents(product_id="halex-support-cloud")
    assert [document["title"] for document in documents] == ["退款政策"]
    assert documents[0]["content"] == "第一段。第二段。"
    assert documents[0]["chunk_count"] == 1

    all_documents = kb.list_documents(
        product_id="halex-support-cloud", include_unpublished=True
    )
    assert {document["title"] for document in all_documents} == {"退款政策", "草稿政策"}
