#!/usr/bin/env python3
"""Opt-in collector for small, public, official documentation sources.

This script performs GET requests only. It never calls the LumenDesk API,
ChromaDB, or any write endpoint. By default it is a dry-run; pass --execute
to save local snapshots and a manifest under the requested output directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REGISTRY = Path("wiki/knowledge-governance/source_registry.json")
DEFAULT_OUTPUT = Path(".workbench/runtime/knowledge-source-captures")
USER_AGENT = "LumenDeskKnowledgeCollector/0.1 (+public-reference-only)"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_registry(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise ValueError("registry.sources 必须是数组")
    return [source for source in sources if isinstance(source, dict)]


def can_fetch(url: str) -> tuple[bool, str]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False, "invalid_http_url"
    robots_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except (OSError, urllib.error.URLError):
        # Fail closed: an unreachable robots file is not permission to crawl.
        return False, f"robots_unreachable:{robots_url}"
    return parser.can_fetch(USER_AGENT, url), robots_url


def fetch(url: str, max_bytes: int) -> tuple[bytes, str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(min(64 * 1024, max_bytes - total + 1))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"response exceeds --max-bytes={max_bytes}")
        content_type = response.headers.get_content_type()
        charset = response.headers.get_content_charset() or "utf-8"
    return b"".join(chunks), content_type, charset


def extract_title(body: str) -> str | None:
    markdown_title = re.search(r"^Title:\s*(.+)$", body, flags=re.MULTILINE)
    if markdown_title:
        return markdown_title.group(1).strip()
    html_title = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.IGNORECASE | re.DOTALL)
    if html_title:
        return re.sub(r"\s+", " ", html_title.group(1)).strip()
    return None


def collect(source: dict[str, Any], output_dir: Path, max_bytes: int) -> dict[str, Any]:
    source_id = str(source.get("source_id", "unknown"))
    url = str(source.get("source_url", ""))
    result: dict[str, Any] = {"source_id": source_id, "source_url": url, "collected_at": utc_now()}
    allowed, robots_result = can_fetch(url)
    result["robots_result"] = robots_result
    if not allowed:
        result["status"] = "skipped_robots_or_invalid_url"
        return result
    try:
        raw, content_type, charset = fetch(url, max_bytes)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        result["status"] = "fetch_failed"
        result["error"] = str(exc)
        return result
    digest = hashlib.sha256(raw).hexdigest()
    filename = f"{source_id}-{digest[:12]}.source"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename
    output_path.write_bytes(raw)
    decoded = raw.decode(charset, errors="replace")
    result.update({
        "status": "fetched",
        "content_type": content_type,
        "charset": charset,
        "source_hash": f"sha256:{digest}",
        "source_title_observed": extract_title(decoded),
        "snapshot_path": str(output_path),
    })
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, help="写入采集结果清单；默认写到 output-dir/manifest.json")
    parser.add_argument("--max-bytes", type=int, default=2_000_000)
    parser.add_argument("--delay", type=float, default=1.0, help="请求之间的最小间隔（秒）")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--execute", action="store_true", help="确认执行公开 GET；缺省仅做 dry-run")
    args = parser.parse_args()

    sources = read_registry(args.registry)
    candidates = [s for s in sources if s.get("collection_status") != "not_usable_http_404"]
    candidates = candidates[: max(0, args.limit)]
    if not args.execute:
        print(json.dumps({"mode": "dry_run", "sources": [{"source_id": s.get("source_id"), "url": s.get("source_url")} for s in candidates]}, ensure_ascii=False, indent=2))
        return 0

    results: list[dict[str, Any]] = []
    for index, source in enumerate(candidates):
        if index:
            time.sleep(max(0.0, args.delay))
        results.append(collect(source, args.output_dir, args.max_bytes))
    manifest = args.manifest or args.output_dir / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"collected_at": utc_now(), "results": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"mode": "execute", "manifest": str(manifest), "results": results}, ensure_ascii=False, indent=2))
    return 0 if all(item.get("status") == "fetched" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
