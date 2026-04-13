from __future__ import annotations

from typing import Any

from .models import RankedPost, extract_prefetch_floors, normalize_hole_id
from .utils import extract_text_lines, parse_int, recency_factor


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


def rank_holes(
    holes: list[dict[str, Any]],
    source_endpoint: str,
    half_life_hours: float = 12.0,
    weight_view: float = 0.03,
    weight_reply: float = 1.6,
    weight_like: float = 2.4,
    weight_recency: float = 3.2,
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
            -(item.like_sum),
            -(item.hole_id),
        )
    )
    return ranked
