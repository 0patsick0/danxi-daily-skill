from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import fetch_hole_floors, fetch_holes_with_fallback, should_prefer_webvpn
from .models import normalize_hole_id
from .poster import post_markdown
from .ranking import rank_holes
from .reporter import build_daily_markdown
from .security import require_https, validate_allowed_host
from .utils import iso_utc_hours_ago, parse_iso8601, write_json, write_text
from .webvpn import WebVPNClient


@dataclass
class PipelineConfig:
    base_urls: list[str]
    hours: int = 24
    fetch_limit: int = 10
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
    title_prefix: str = "旦夕热榜日报"
    post: bool = False
    post_endpoint: str | None = None
    post_token: str | None = None
    allowed_read_hosts: set[str] | None = None
    allowed_post_hosts: set[str] | None = None
    unsafe_allow_any_host: bool = False
    post_dedupe_file: Path = Path("outputs/last_post.sha256")
    verbose: bool = False
    webvpn_client: WebVPNClient | None = None
    force_webvpn: bool = False


def _window_hours(total_hours: int) -> list[int]:
    base = [1, 2, 4, 8, 12, 24]
    usable = [h for h in base if h <= total_hours]
    if total_hours not in usable:
        usable.append(total_hours)
    return sorted({max(1, h) for h in usable})


def _merge_hole(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    existing_reply = int(existing.get("reply") or 0)
    candidate_reply = int(candidate.get("reply") or 0)
    existing_view = int(existing.get("view") or 0)
    candidate_view = int(candidate.get("view") or 0)

    existing_score = (existing_view, existing_reply)
    candidate_score = (candidate_view, candidate_reply)
    chosen = candidate if candidate_score > existing_score else existing

    t_existing = parse_iso8601(existing.get("time_updated"))
    t_candidate = parse_iso8601(candidate.get("time_updated"))
    if t_existing is None:
        return chosen
    if t_candidate is None:
        return chosen
    return candidate if t_candidate > t_existing else chosen


def _fetch_hot_candidates(config: PipelineConfig) -> tuple[list[dict[str, Any]], str]:
    merged: dict[int, dict[str, Any]] = {}
    endpoint = config.base_urls[0].rstrip("/")
    errors: list[str] = []
    effective_fetch_limit = min(10, max(1, config.fetch_limit))

    for hours in _window_hours(config.hours):
        start_time = iso_utc_hours_ago(hours)
        try:
            holes, used_endpoint = fetch_holes_with_fallback(
                base_urls=config.base_urls,
                start_time=start_time,
                limit=effective_fetch_limit,
                division_id=config.division_id,
                token=config.api_token,
                timeout=config.timeout,
                webvpn_client=config.webvpn_client,
                force_webvpn=config.force_webvpn,
            )
            endpoint = used_endpoint
        except RuntimeError as exc:
            errors.append(str(exc))
            continue

        for hole in holes:
            try:
                hole_id = normalize_hole_id(hole)
            except ValueError:
                continue

            current = merged.get(hole_id)
            if current is None:
                merged[hole_id] = hole
            else:
                merged[hole_id] = _merge_hole(current, hole)

    if not merged:
        raise RuntimeError("; ".join(errors) if errors else "all endpoints failed")

    cutoff = parse_iso8601(iso_utc_hours_ago(config.hours))
    merged_items = list(merged.values())
    if cutoff is None:
        return merged_items, endpoint

    recent_items: list[dict[str, Any]] = []
    for hole in merged_items:
        created_at = parse_iso8601(hole.get("time_created"))
        if created_at is not None and created_at >= cutoff:
            recent_items.append(hole)

    if recent_items:
        return recent_items, endpoint
    return merged_items, endpoint


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
    holes, used_endpoint = _fetch_hot_candidates(config)
    prefer_webvpn_for_floors = config.webvpn_client is not None and (
        config.force_webvpn or should_prefer_webvpn(used_endpoint)
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
            webvpn_client=config.webvpn_client,
            force_webvpn=prefer_webvpn_for_floors,
        )
        if floors:
            if not isinstance(hole.get("floors"), dict):
                hole["floors"] = {}
            hole["floors"]["prefetch"] = floors

    ranked = rank_holes(holes, source_endpoint=used_endpoint)
    top_posts = ranked[: config.top_n]

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
