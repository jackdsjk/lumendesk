#!/usr/bin/env python3
"""Prepare a review manifest for LumenDesk knowledge drafts.

The command validates and hashes draft records. It does not approve content,
call an external model, or write to ChromaDB or any HTTP endpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REGISTRY = Path("wiki/knowledge-governance/source_registry.json")
DEFAULT_DRAFT = Path("wiki/knowledge-governance/lumendesk_support_cloud_draft.jsonl")
REQUIRED_FIELDS = {
    "document_id",
    "product_id",
    "title",
    "content",
    "policy_type",
    "source_refs",
    "adapted",
    "adaptation_notes",
    "approval_status",
    "effective_from",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number} 不是有效 JSON：{exc}") from exc
        if not isinstance(record, dict):
            raise ValueError(f"{path}:{line_number} 必须是 JSON 对象")
        records.append(record)
    return records


def prepare(registry_path: Path, draft_path: Path) -> dict[str, Any]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    sources = {item.get("source_id"): item for item in registry.get("sources", []) if isinstance(item, dict)}
    records = load_jsonl(draft_path)
    prepared: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_ids: set[str] = set()
    for index, record in enumerate(records, 1):
        missing = sorted(REQUIRED_FIELDS - set(record))
        document_id = str(record.get("document_id", f"line-{index}"))
        if missing:
            errors.append(f"{document_id}: 缺少字段 {', '.join(missing)}")
        if document_id in seen_ids:
            errors.append(f"{document_id}: document_id 重复")
        seen_ids.add(document_id)
        if record.get("approval_status") not in {"draft", "needs_review"}:
            errors.append(f"{document_id}: 只能准备 draft/needs_review，禁止脚本生成 approved")
        if record.get("adapted") is not True:
            errors.append(f"{document_id}: adapted 必须为 true")
        for source_id in record.get("source_refs", []):
            source = sources.get(source_id)
            if source is None:
                errors.append(f"{document_id}: 未登记来源 {source_id}")
            elif source.get("collection_status") == "not_usable_http_404":
                errors.append(f"{document_id}: 来源 {source_id} 不可用（404）")
        content = str(record.get("content", ""))
        prepared_record = dict(record)
        prepared_record["content_hash"] = f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"
        prepared_record["production_import_allowed"] = False
        prepared.append(prepared_record)
    return {"prepared_at": utc_now(), "production_import_allowed": False, "errors": errors, "records": prepared}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.registry, args.draft)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "records": len(result["records"]), "errors": result["errors"]}, ensure_ascii=False, indent=2))
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
