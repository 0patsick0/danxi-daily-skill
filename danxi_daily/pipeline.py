from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import fetch_hole_floors, fetch_holes_with_fallback
from .poster import post_markdown
from .ranking import rank_holes
from .reporter import build_daily_markdown
from .security import require_https, validate_allowed_host
from .summarizer import summarize_post
from .utils import iso_utc_hours_ago, write_json, write_text


@dataclass
class PipelineConfig:
    base_urls: list[str]
    hours: int = 24
    fetch_limit: int = 120
    top_n: int = 12
    division_id: int | None = None
    prompt_path: Path = Path("prompts/summarize.md")
    output_markdown: Path = Path("outputs/daily.md")
    output_holes: Path = Path("outputs/holes.raw.json")
    output_ranked: Path = Path("outputs/ranked.json")
    api_token: str | None = None
    llm_provider: str = "auto"
    timeout: int = 15
    floor_enrich_size: int = 40
    title_prefix: str = "DanXi Daily"
    post: bool = False
    post_endpoint: str | None = None
    post_token: str | None = None
    allowed_read_hosts: set[str] | None = None
    allowed_post_hosts: set[str] | None = None
    unsafe_allow_any_host: bool = False
    post_dedupe_file: Path = Path("outputs/last_post.sha256")
    verbose: bool = False


def run_pipeline(config: PipelineConfig) -> dict[str, Any]:
    for url in config.base_urls:
        require_https(url)
        if (not config.unsafe_allow_any_host) and config.allowed_read_hosts:
            validate_allowed_host(url, config.allowed_read_hosts)

    if config.post and config.post_endpoint:
        require_https(config.post_endpoint)
        if (not config.unsafe_allow_any_host) and config.allowed_post_hosts:
            validate_allowed_host(config.post_endpoint, config.allowed_post_hosts)

    start_time = iso_utc_hours_ago(config.hours)
    holes, used_endpoint = fetch_holes_with_fallback(
        base_urls=config.base_urls,
        start_time=start_time,
        limit=config.fetch_limit,
        division_id=config.division_id,
        token=config.api_token,
        timeout=config.timeout,
    )

    write_json(config.output_holes, holes)

    # Enrich prefetch floors for better ranking/summaries when endpoint allows it.
    for hole in holes[: max(config.top_n * 2, 10)]:
        hole_id = hole.get("hole_id")
        if not isinstance(hole_id, int):
            continue
        floors = fetch_hole_floors(
            base_url=used_endpoint,
            hole_id=hole_id,
            token=config.api_token,
            size=config.floor_enrich_size,
            timeout=config.timeout,
        )
        if floors:
            if not isinstance(hole.get("floors"), dict):
                hole["floors"] = {}
            hole["floors"]["prefetch"] = floors

    ranked = rank_holes(holes, source_endpoint=used_endpoint)
    top_posts = ranked[: config.top_n]

    for post in top_posts:
        post.summary = summarize_post(
            post,
            prompt_path=config.prompt_path,
            provider=config.llm_provider,
            timeout=config.timeout,
        )

    report = build_daily_markdown(top_posts, title_prefix=config.title_prefix)
    write_text(config.output_markdown, report)
    write_json(config.output_ranked, [p.to_dict() for p in top_posts])

    post_result: dict[str, Any] | None = None
    if config.post:
        if not config.post_endpoint:
            raise ValueError("post mode requires post_endpoint")
        token = config.post_token or os.getenv("DANXI_POST_TOKEN")
        if not token:
            raise ValueError("post mode requires DANXI_POST_TOKEN")

        dedupe_payload = {
            "top": [
                {
                    "hole_id": p.hole_id,
                    "time_updated": p.time_updated,
                    "reply": p.reply,
                    "view": p.view,
                    "like_sum": p.like_sum,
                    "hot_score": round(p.hot_score, 4),
                }
                for p in top_posts
            ]
        }
        dedupe_bytes = json.dumps(dedupe_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        new_hash = hashlib.sha256(dedupe_bytes).hexdigest()
        old_hash = ""
        if config.post_dedupe_file.exists():
            try:
                old_hash = config.post_dedupe_file.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeDecodeError):
                old_hash = ""

        lock_path = config.post_dedupe_file.with_suffix(config.post_dedupe_file.suffix + ".lock")
        lock_fd = None
        try:
            lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            post_result = {
                "status": "skipped",
                "reason": "lock_exists",
            }
        try:
            if post_result is not None:
                pass
            elif old_hash and old_hash == new_hash:
                post_result = {
                    "status": "skipped",
                    "reason": "duplicate_content",
                }
            else:
                status, body = post_markdown(
                    endpoint=config.post_endpoint,
                    token=token,
                    content=report,
                    timeout=config.timeout,
                )
                if status < 300:
                    write_text(config.post_dedupe_file, new_hash)

                post_result = {"status": status}
                if config.verbose:
                    post_result["response_preview"] = body[:500]
        finally:
            if lock_fd is not None:
                os.close(lock_fd)
                try:
                    os.remove(lock_path)
                except FileNotFoundError:
                    pass

    return {
        "used_endpoint": used_endpoint,
        "start_time": start_time,
        "fetched": len(holes),
        "ranked": len(ranked),
        "top": len(top_posts),
        "output_markdown": str(config.output_markdown),
        "output_holes": str(config.output_holes),
        "output_ranked": str(config.output_ranked),
        "post_result": post_result,
    }
