import threading
from datetime import datetime, timedelta, timezone

import pytest

from tooling.knowledge_base import KnowledgeBase


class GovernanceCollection:
    def __init__(self):
        self.rows = {}

    def count(self):
        return len(self.rows)

    def upsert(self, *, ids, documents, metadatas):
        for row_id, document, metadata in zip(ids, documents, metadatas):
            self.rows[row_id] = (document, metadata)

    def get(self, where, include):
        selected = [(row_id, document, metadata) for row_id, (document, metadata) in self.rows.items()
                    if all(metadata.get(key) == value for key, value in where.items())]
        return {
            "ids": [row_id for row_id, _, _ in selected],
            "metadatas": [metadata for _, _, metadata in selected],
        }

    def delete(self, ids):
        for row_id in ids:
            self.rows.pop(row_id, None)

    def query(self, *, query_texts, n_results, where):
        def matches(metadata, condition):
            if "$and" in condition:
                return all(matches(metadata, item) for item in condition["$and"])
            if "$or" in condition:
                return any(matches(metadata, item) for item in condition["$or"])
            return all(metadata.get(key) == value for key, value in condition.items())

        selected = [(document, metadata) for document, metadata in self.rows.values() if matches(metadata, where)]
        selected = selected[:n_results]
        return {
            "documents": [[document for document, _ in selected]],
            "metadatas": [[metadata for _, metadata in selected]],
            "distances": [[0.1 for _ in selected]],
        }


def make_kb():
    kb = KnowledgeBase.__new__(KnowledgeBase)
    kb._write_lock = threading.RLock()
    kb._collection = GovernanceCollection()
    return kb


def approved_doc(**overrides):
    now = datetime.now(timezone.utc)
    doc = {
        "document_id": "policy-1",
        "title": "LumenDesk 退款政策",
        "content": "当前有效的退款规则。",
        "product_id": "lumendesk",
        "region": "AU",
        "channel": "web",
        "tenant_scope": "global",
        "approval_status": "approved",
        "publication_status": "published",
        "effective_from": (now - timedelta(days=1)).isoformat(),
        "effective_to": (now + timedelta(days=1)).isoformat(),
        "source_url": "https://example.com/refund",
        "source_title": "Refund policy",
    }
    doc.update(overrides)
    return doc


def test_metadata_is_allowlisted_and_defaults_to_unpublished_draft():
    kb = make_kb()
    kb.add_documents([{"title": "草稿", "content": "尚未审核"}])
    metadata = next(iter(kb._collection.rows.values()))[1]
    assert metadata["approval_status"] == "draft"
    assert metadata["publication_status"] == "unpublished"
    assert metadata["tenant_scope"] == "global"
    assert len(metadata["source_hash"]) == 64


def test_only_approved_published_current_documents_are_searchable():
    kb = make_kb()
    kb.add_documents([
        approved_doc(document_id="valid"),
        approved_doc(document_id="draft", approval_status="draft"),
        approved_doc(document_id="unpublished", publication_status="unpublished"),
        approved_doc(document_id="expired", effective_to=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()),
        approved_doc(document_id="future", effective_from=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat()),
    ])
    result = kb.search("退款", top_k=10)
    assert len(result) == 1
    assert result[0]["title"] == "LumenDesk 退款政策"
    assert result[0]["source_url"] == "https://example.com/refund"


def test_legacy_rows_without_governance_metadata_are_not_searchable():
    kb = make_kb()
    kb._collection.rows["legacy"] = ("旧内容", {"title": "旧政策", "document_id": "legacy"})
    assert kb.search("旧政策") == []


def test_filter_context_is_passed_to_search_handler():
    kb = make_kb()
    kb.add_documents([approved_doc(document_id="global"), approved_doc(document_id="tenant", tenant_scope="tenant-a")])
    import asyncio
    result = asyncio.run(kb.search_handler(
        {"query": "退款", "top_k": 5},
        {"knowledge_filters": {"tenant_scope": "tenant-a"}},
    ))
    assert {item["tenant_scope"] for item in result} == {"global", "tenant-a"}


@pytest.mark.parametrize("field,value", [
    ("approval_status", "approved-now"),
    ("publication_status", "live"),
    ("effective_from", "not-a-date"),
])
def test_invalid_governance_metadata_is_rejected(field, value):
    kb = make_kb()
    with pytest.raises(ValueError):
        kb.add_documents([approved_doc(**{field: value})])
