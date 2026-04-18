from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import fetch_hole_floors, fetch_holes_with_fallback, should_prefer_webvpn
from .models import normalize_hole_id
from .poster import post_markdown
from .ranking import rank_holes
from .reporter import build_daily_markdown
from .security import require_https, validate_allowed_host
from .utils import ensure_parent, parse_iso8601, write_json, write_text
from .webvpn import WebVPNClient


@dataclass
class PipelineConfig:
    base_urls: list[str]
    hours: int = 24
    fetch_limit: int = 10
    top_n: int = 10
    fetch_max_pages: int = 300
    fetch_retry_per_page: int = 3
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
    post_schedule_hhmm: str | None = None
    post_schedule_state_file: Path = Path("outputs/last_post_slot.txt")
    verbose: bool = False
    webvpn_client: WebVPNClient | None = None
    force_webvpn: bool = False
    floor_fetch_workers: int = 6
    floor_fetch_timeout: int = 8
    floor_cache_file: Path = Path("outputs/floors_cache.json")
    floor_cache_max_entries: int = 800
    archive_outputs: bool = True
    archive_dir: Path = Path("outputs/history")

def _local_today_start_utc_iso() -> str:
    now_local = datetime.now().astimezone()
    day_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start_utc = day_start_local.astimezone(timezone.utc)
    return day_start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _effective_start_time(hours: int) -> str:
    _ = hours
    # Daily report should always include the entire local day window.
    return _local_today_start_utc_iso()


_POST_SCHEDULE_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _load_floor_cache(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}

    cache: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        time_updated = value.get("time_updated")
        floors = value.get("floors")
        if not isinstance(time_updated, str) or not isinstance(floors, list):
            continue
        normalized_floors = [x for x in floors if isinstance(x, dict)]
        cache[key] = {
            "time_updated": time_updated,
            "floors": normalized_floors,
        }
    return cache


def _write_json_atomic(path: Path, payload: Any) -> None:
    ensure_parent(path)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _try_acquire_lock(lock_path: Path) -> int | None:
    try:
        return os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None


def _release_lock(lock_path: Path, lock_fd: int | None) -> None:
    if lock_fd is None:
        return
    os.close(lock_fd)
    try:
        os.remove(lock_path)
    except FileNotFoundError:
        pass


def _touch_cache_entry(cache: dict[str, dict[str, Any]], key: str) -> None:
    value = cache.pop(key, None)
    if value is not None:
        cache[key] = value


def _prune_floor_cache(cache: dict[str, dict[str, Any]], max_entries: int) -> dict[str, dict[str, Any]]:
    if len(cache) <= max_entries:
        return cache
    keep = list(cache.items())[-max_entries:]
    return dict(keep)


def _is_post_due_today(hhmm: str, now_local: datetime) -> bool:
    match = _POST_SCHEDULE_RE.match(hhmm)
    if match is None:
        raise ValueError("post schedule must be HH:MM (24-hour)")
    hour = int(match.group(1))
    minute = int(match.group(2))
    return (now_local.hour, now_local.minute) >= (hour, minute)


def _current_post_slot(hhmm: str, now_local: datetime) -> str:
    return f"{now_local.strftime('%Y%m%d')}-{hhmm}"


def _should_skip_post_for_schedule(config: PipelineConfig, now_local: datetime) -> tuple[bool, str | None, str | None]:
    if not config.post_schedule_hhmm:
        return False, None, None
    if not _is_post_due_today(config.post_schedule_hhmm, now_local):
        return True, "schedule_not_due", None

    slot = _current_post_slot(config.post_schedule_hhmm, now_local)
    last_slot = ""
    if config.post_schedule_state_file.exists():
        try:
            last_slot = config.post_schedule_state_file.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            last_slot = ""
    if last_slot == slot:
        return True, "same_slot_already_posted", slot
    return False, None, slot


def _archive_outputs(
    config: PipelineConfig,
    report: str,
    holes: list[dict[str, Any]],
    ranked_payload: list[dict[str, Any]],
) -> dict[str, str]:
    if not config.archive_outputs:
        return {}

    now_local = datetime.now().astimezone()
    stamp = f"{now_local.strftime('%Y%m%d_%H%M%S_%f')}_{time.time_ns()}"
    month_dir = config.archive_dir / now_local.strftime("%Y%m")

    md_path = month_dir / f"daily_{stamp}.md"
    holes_path = month_dir / f"holes_{stamp}.json"
    ranked_path = month_dir / f"ranked_{stamp}.json"

    write_text(md_path, report)
    write_json(holes_path, holes)
    write_json(ranked_path, ranked_payload)

    return {
        "archived_markdown": str(md_path),
        "archived_holes": str(holes_path),
        "archived_ranked": str(ranked_path),
    }


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


def _page_time_cursor(holes: list[dict[str, Any]]) -> str | None:
    oldest: datetime | None = None
    for hole in holes:
        dt = parse_iso8601(hole.get("time_updated"))
        if dt is None:
            dt = parse_iso8601(hole.get("time_created"))
        if dt is None:
            continue
        if oldest is None or dt < oldest:
            oldest = dt

    if oldest is None:
        return None
    # WebVPN /holes offset expects local wall-clock timestamp without timezone suffix.
    return oldest.astimezone().strftime("%Y-%m-%dT%H:%M:%S")


def _webvpn_start_cursor() -> str:
    # Start from current local time and page backward to today's cutoff.
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S")


def _fetch_hot_candidates(config: PipelineConfig) -> tuple[list[dict[str, Any]], str]:
    merged: dict[int, dict[str, Any]] = {}
    endpoint = config.base_urls[0].rstrip("/")
    errors: list[str] = []
    start_time = _effective_start_time(config.hours)
    # /api/holes currently accepts up to 10 items per request.
    page_size = max(1, min(config.fetch_limit, 10))
    use_time_offset = bool(config.force_webvpn)
    offset: int | str | None = (_webvpn_start_cursor() if use_time_offset else 0)
    previous_cursor: str | None = None
    max_pages = max(1, config.fetch_max_pages)
    retry_per_page = max(1, config.fetch_retry_per_page)

    for _ in range(max_pages):
        holes: list[dict[str, Any]] | None = None
        for _attempt in range(retry_per_page):
            try:
                fetched, used_endpoint = fetch_holes_with_fallback(
                    base_urls=config.base_urls,
                    start_time=start_time,
                    limit=page_size,
                    offset=offset,
                    division_id=config.division_id,
                    token=config.api_token,
                    timeout=config.timeout,
                    webvpn_client=config.webvpn_client,
                    force_webvpn=config.force_webvpn,
                )
                holes = fetched
                endpoint = used_endpoint
                break
            except RuntimeError as exc:
                errors.append(str(exc))

        if holes is None:
            break

        new_count = 0
        for hole in holes:
            try:
                hole_id = normalize_hole_id(hole)
            except ValueError:
                continue

            current = merged.get(hole_id)
            if current is None:
                merged[hole_id] = hole
                new_count += 1
            else:
                merged[hole_id] = _merge_hole(current, hole)

        if len(holes) < page_size:
            break

        if new_count == 0:
            break

        if use_time_offset:
            next_cursor = _page_time_cursor(holes)
            if not next_cursor or next_cursor == previous_cursor:
                break
            previous_cursor = next_cursor
            offset = next_cursor
        else:
            assert isinstance(offset, int)
            offset += len(holes)

    if not merged:
        raise RuntimeError("; ".join(errors) if errors else "all endpoints failed")

    merged_items = list(merged.values())
    cutoff = parse_iso8601(start_time)
    if cutoff is None:
        return merged_items, endpoint

    filtered: list[dict[str, Any]] = []
    for hole in merged_items:
        created_at = parse_iso8601(hole.get("time_created"))
        if created_at is None:
            created_at = parse_iso8601(hole.get("time_updated"))
        if created_at is not None and created_at >= cutoff:
            filtered.append(hole)

    return filtered, endpoint


def run_pipeline(config: PipelineConfig) -> dict[str, Any]:
    for url in config.base_urls:
        require_https(url)
        if (not config.unsafe_allow_any_host) and config.allowed_read_hosts:
            validate_allowed_host(url, config.allowed_read_hosts)

    if config.post and config.post_endpoint:
        require_https(config.post_endpoint)
        if (not config.unsafe_allow_any_host) and config.allowed_post_hosts:
            validate_allowed_host(config.post_endpoint, config.allowed_post_hosts)

    start_time = _effective_start_time(config.hours)
    holes, used_endpoint = _fetch_hot_candidates(config)
    prefer_webvpn_for_floors = config.webvpn_client is not None and (
        config.force_webvpn or should_prefer_webvpn(used_endpoint)
    )

    write_json(config.output_holes, holes)

    # Enrich floors concurrently and reuse local cache to reduce repeated network waits.
    if config.floor_enrich_size > 0:
        floor_cache = _load_floor_cache(config.floor_cache_file)
        cache_dirty = False
        cache_updates: dict[str, dict[str, Any]] = {}
        to_fetch: list[tuple[dict[str, Any], int, str]] = []
        floor_sample_size = max(config.top_n * 2, 10)

        for hole in holes[:floor_sample_size]:
            hole_id = hole.get("hole_id")
            if not isinstance(hole_id, int):
                continue
            time_updated = str(hole.get("time_updated") or "")
            cache_key = str(hole_id)
            cached = floor_cache.get(cache_key)
            if isinstance(cached, dict) and cached.get("time_updated") == time_updated:
                cached_floors = cached.get("floors")
                if isinstance(cached_floors, list):
                    if not isinstance(hole.get("floors"), dict):
                        hole["floors"] = {}
                    hole["floors"]["prefetch"] = [x for x in cached_floors if isinstance(x, dict)]
                    _touch_cache_entry(floor_cache, cache_key)
                    continue
            to_fetch.append((hole, hole_id, time_updated))

        if to_fetch:
            # Avoid sharing a mutable WebVPN session across worker threads.
            use_webvpn_in_parallel = prefer_webvpn_for_floors
            workers = max(1, min(config.floor_fetch_workers, len(to_fetch)))
            if use_webvpn_in_parallel:
                workers = 1
            floor_timeout = max(1, min(config.timeout, config.floor_fetch_timeout))
            needs_webvpn_retry: list[tuple[dict[str, Any], int, str]] = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                future_map = {
                    pool.submit(
                        fetch_hole_floors,
                        base_url=used_endpoint,
                        hole_id=hole_id,
                        token=config.api_token,
                        size=config.floor_enrich_size,
                        timeout=floor_timeout,
                        webvpn_client=(config.webvpn_client if use_webvpn_in_parallel else None),
                        force_webvpn=prefer_webvpn_for_floors,
                    ): (hole, hole_id, time_updated)
                    for hole, hole_id, time_updated in to_fetch
                }

                for future in concurrent.futures.as_completed(future_map):
                    hole, hole_id, time_updated = future_map[future]
                    floors: list[dict[str, Any]] = []
                    fetch_succeeded = False
                    try:
                        result = future.result()
                        if isinstance(result, list):
                            floors = [x for x in result if isinstance(x, dict)]
                            fetch_succeeded = True
                    except Exception:
                        floors = []

                    if floors:
                        if not isinstance(hole.get("floors"), dict):
                            hole["floors"] = {}
                        hole["floors"]["prefetch"] = floors

                    # Cache only non-empty successful fetches to avoid freezing transient failures.
                    if fetch_succeeded and floors:
                        entry = {
                            "time_updated": time_updated,
                            "floors": floors,
                        }
                        floor_cache[str(hole_id)] = entry
                        cache_updates[str(hole_id)] = entry
                        cache_dirty = True

                    # Optional serial retry through WebVPN when direct fetch returns empty.
                    if (
                        not floors
                        and config.webvpn_client is not None
                        and not use_webvpn_in_parallel
                    ):
                        needs_webvpn_retry.append((hole, hole_id, time_updated))

            if needs_webvpn_retry:
                for hole, hole_id, time_updated in needs_webvpn_retry:
                    retry_floors = fetch_hole_floors(
                        base_url=used_endpoint,
                        hole_id=hole_id,
                        token=config.api_token,
                        size=config.floor_enrich_size,
                        timeout=floor_timeout,
                        webvpn_client=config.webvpn_client,
                        force_webvpn=True,
                    )
                    if not retry_floors:
                        continue

                    floors = [x for x in retry_floors if isinstance(x, dict)]
                    if not floors:
                        continue

                    if not isinstance(hole.get("floors"), dict):
                        hole["floors"] = {}
                    hole["floors"]["prefetch"] = floors

                    entry = {
                        "time_updated": time_updated,
                        "floors": floors,
                    }
                    floor_cache[str(hole_id)] = entry
                    cache_updates[str(hole_id)] = entry
                    cache_dirty = True

        if cache_dirty:
            lock_path = config.floor_cache_file.with_suffix(config.floor_cache_file.suffix + ".lock")
            lock_fd = _try_acquire_lock(lock_path)
            try:
                if lock_fd is not None:
                    latest_cache = _load_floor_cache(config.floor_cache_file)
                    latest_cache.update(cache_updates)
                    pruned_cache = _prune_floor_cache(latest_cache, max(100, config.floor_cache_max_entries))
                    _write_json_atomic(config.floor_cache_file, pruned_cache)
            finally:
                _release_lock(lock_path, lock_fd)

    ranked = rank_holes(holes, source_endpoint=used_endpoint)
    top_posts = ranked[: config.top_n]

    report = build_daily_markdown(top_posts, title_prefix=config.title_prefix)
    write_text(config.output_markdown, report)
    ranked_payload = [p.to_dict() for p in top_posts]
    write_json(config.output_ranked, ranked_payload)
    archive_paths = _archive_outputs(config, report, holes, ranked_payload)

    post_result: dict[str, Any] | None = None
    if config.post:
        if not config.post_endpoint:
            raise ValueError("post mode requires post_endpoint")
        token = config.post_token or os.getenv("DANXI_POST_TOKEN")
        if not token:
            raise ValueError("post mode requires DANXI_POST_TOKEN")

        now_local = datetime.now().astimezone()
        skip_for_schedule, schedule_reason, current_slot = _should_skip_post_for_schedule(config, now_local)
        if skip_for_schedule:
            post_result = {
                "status": "skipped",
                "reason": schedule_reason,
            }
            if current_slot:
                post_result["slot"] = current_slot

        if post_result is None:
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

            lock_path = config.post_dedupe_file.with_suffix(config.post_dedupe_file.suffix + ".lock")
            lock_fd = _try_acquire_lock(lock_path)
            if lock_fd is None:
                post_result = {
                    "status": "skipped",
                    "reason": "lock_exists",
                }
            try:
                if post_result is not None:
                    pass
                else:
                    old_hash = ""
                    if config.post_dedupe_file.exists():
                        try:
                            old_hash = config.post_dedupe_file.read_text(encoding="utf-8").strip()
                        except (OSError, UnicodeDecodeError):
                            old_hash = ""

                    if old_hash and old_hash == new_hash:
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
                            division_id=config.division_id or 1,
                            webvpn_client=config.webvpn_client if prefer_webvpn_for_floors else None,
                        )
                        if status < 300:
                            write_text(config.post_dedupe_file, new_hash)
                            if current_slot:
                                write_text(config.post_schedule_state_file, current_slot)

                        post_result = {"status": status}
                        if config.verbose:
                            post_result["response_preview"] = body[:500]
            finally:
                _release_lock(lock_path, lock_fd)

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
        **archive_paths,
    }
