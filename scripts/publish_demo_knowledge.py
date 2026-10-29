#!/usr/bin/env python3
"""Explicitly publish the reviewed LumenDesk Support Cloud demo knowledge.

This is intentionally separate from draft preparation. It requires
``--approve-demo`` so a dry-run or draft validation can never publish by
accident. It writes only through the authenticated knowledge API.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_REGISTRY = Path("wiki/knowledge-governance/source_registry.json")
DEFAULT_DRAFT = Path("wiki/knowledge-governance/lumendesk_support_cloud_draft.jsonl")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_documents(registry_path: Path, draft_path: Path, reviewer: str) -> list[dict[str, Any]]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    sources = {
        item.get("source_id"): item
        for item in registry.get("sources", [])
        if isinstance(item, dict)
    }
    now = utc_now()
    documents: list[dict[str, Any]] = []
    for line in draft_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        draft = json.loads(line)
        refs = draft.get("source_refs") or []
        source = sources.get(refs[0], {}) if refs else {}
        documents.append({
            "document_id": draft["document_id"],
            "title": draft["title"],
            "content": draft["content"],
            "product_id": "halex-support-cloud",
            "region": "AU",
            "channel": "web",
            "tenant_scope": "global",
            "source_url": source.get("source_url", ""),
            "source_title": source.get("source_title", "LumenDesk internal demo policy"),
            "source_hash": source.get("source_hash", ""),
            "approval_status": "approved",
            "publication_status": "published",
            "effective_from": draft.get("effective_from", ""),
            "effective_to": draft.get("effective_to") or "",
            "reviewer": reviewer,
            "reviewed_at": now,
            "published_at": now,
            "policy_type": draft.get("policy_type", ""),
            "locale": "zh-CN",
        })
    return documents


def admin_token(explicit: str | None) -> str:
    if explicit:
        return explicit
    entries = json.loads(os.getenv("LUMENDESK_API_TOKENS", "{}") or "{}")
    return next(
        (
            token
            for token, account in entries.items()
            if isinstance(account, dict) and account.get("role") == "admin"
        ),
        "",
    )


def publish(base_url: str, documents: list[dict[str, Any]], token: str) -> str:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/knowledge/add",
        data=json.dumps({"documents": documents}, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"知识发布失败 HTTP {exc.code}: {detail}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--reviewer", default="demo-owner")
    parser.add_argument("--token", help="管理员 Bearer Token；缺省从 LUMENDESK_API_TOKENS 读取")
    parser.add_argument("--approve-demo", action="store_true", help="明确批准仅用于演示的草案并发布")
    args = parser.parse_args()
    if not args.approve_demo:
        parser.error("发布前必须显式传入 --approve-demo")
    documents = load_documents(args.registry, args.draft, args.reviewer)
    print(publish(args.base_url, documents, admin_token(args.token)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
