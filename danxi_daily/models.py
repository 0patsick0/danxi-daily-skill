from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .utils import parse_int


@dataclass
class RankedPost:
    hole_id: int
    division_id: int | None
    time_created: str | None
    time_updated: str | None
    reply: int
    view: int
    like_sum: int
    hot_score: float
    excerpt: str
    summary: str = ""
    source_endpoint: str = ""
    floors_count: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["hot_score"] = round(self.hot_score, 6)
        return data


def normalize_hole_id(raw_hole: dict[str, Any]) -> int:
    hole_id = parse_int(raw_hole.get("hole_id"), default=-1)
    if hole_id < 0:
        raise ValueError("missing hole_id")
    return hole_id


def extract_prefetch_floors(raw_hole: dict[str, Any]) -> list[dict[str, Any]]:
    floors = raw_hole.get("floors")
    if not isinstance(floors, dict):
        return []
    prefetch = floors.get("prefetch")
    if isinstance(prefetch, list):
        return [x for x in prefetch if isinstance(x, dict)]

    first_floor = floors.get("first_floor")
    if isinstance(first_floor, dict):
        return [first_floor]
    return []
