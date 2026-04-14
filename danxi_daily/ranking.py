from __future__ import annotations

import re
from typing import Any

from .models import RankedPost, extract_prefetch_floors, normalize_hole_id
from .utils import extract_text_lines, parse_int, recency_factor


_INVALID_DISCUSSION_PATTERNS = [
    re.compile(r"(?:收|出|求|蹲|互换|交换)\s*(?:资料|课件|讲义|笔记)", re.IGNORECASE),
    re.compile(r"(?:代课|替课|带课|求代课|找代课|代上课)", re.IGNORECASE),
    re.compile(r"(?:代刷|代锻|代跑|刷锻)", re.IGNORECASE),
    re.compile(r"(?:资料\s*dd|dd\s*资料)", re.IGNORECASE),
]


def _sum_floor_likes(floors: list[dict[str, Any]]) -> int:
    total = 0
    for floor in floors:
        total += parse_int(floor.get("like"), default=0)
    return total


def _build_excerpt(hole: dict[str, Any], floors: list[dict[str, Any]], max_chars: int = 90) -> str:
    contents: list[str] = []
    for floor in floors:
        text = floor.get("content")
        if isinstance(text, str) and text.strip():
            contents.extend(extract_text_lines(text))
        if contents:
            break

    if not contents:
        text = hole.get("content")
        if isinstance(text, str):
            contents.extend(extract_text_lines(text))

    joined = " ".join(contents).strip()
    if len(joined) <= max_chars:
        return joined
    return joined[: max_chars - 3].rstrip() + "..."


def _collect_discussion_text(hole: dict[str, Any], floors: list[dict[str, Any]]) -> str:
    segments: list[str] = []
    content = hole.get("content")
    if isinstance(content, str) and content.strip():
        segments.append(content)
    for floor in floors[:8]:
        text = floor.get("content")
        if isinstance(text, str) and text.strip():
            segments.append(text)
    return "\n".join(segments)


def _is_invalid_discussion(text: str) -> bool:
    if not text.strip():
        return False
    return any(pattern.search(text) is not None for pattern in _INVALID_DISCUSSION_PATTERNS)


def _passes_engagement_gate(view_count: int, reply_count: int) -> bool:
    # Keep meaningful discussions and avoid low-signal noise.
    if view_count >= 120 or reply_count >= 8:
        return True
    if view_count >= 80 and reply_count >= 4:
        return True
    return False


def rank_holes(
    holes: list[dict[str, Any]],
    source_endpoint: str,
    half_life_hours: float = 16.0,
    weight_view: float = 0.08,
    weight_reply: float = 5.0,
    weight_like: float = 1.0,
    weight_recency: float = 1.5,
) -> list[RankedPost]:
    ranked: list[RankedPost] = []

    for raw_hole in holes:
        try:
            hole_id = normalize_hole_id(raw_hole)
        except ValueError:
            continue

        floors = extract_prefetch_floors(raw_hole)
        like_sum = _sum_floor_likes(floors)
        reply_count = parse_int(raw_hole.get("reply"), default=len(floors))
        view_count = parse_int(raw_hole.get("view"), default=0)

        discussion_text = _collect_discussion_text(raw_hole, floors)
        if _is_invalid_discussion(discussion_text):
            continue
        if not _passes_engagement_gate(view_count, reply_count):
            continue

        score = (
            (view_count * weight_view)
            + (reply_count * weight_reply)
            + (like_sum * weight_like)
            + (recency_factor(raw_hole.get("time_updated"), half_life_hours) * weight_recency)
        )

        ranked.append(
            RankedPost(
                hole_id=hole_id,
                division_id=parse_int(raw_hole.get("division_id"), default=0) or None,
                time_created=raw_hole.get("time_created"),
                time_updated=raw_hole.get("time_updated"),
                reply=reply_count,
                view=view_count,
                like_sum=like_sum,
                hot_score=score,
                excerpt=_build_excerpt(raw_hole, floors),
                source_endpoint=source_endpoint,
                floors_count=len(floors),
                raw=raw_hole,
            )
        )

    ranked.sort(
        key=lambda item: (
            -item.hot_score,
            -(item.reply),
            -(item.view),
            -(item.like_sum),
            -(item.hole_id),
        )
    )
    return ranked
