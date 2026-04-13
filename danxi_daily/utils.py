from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc_hours_ago(hours: int) -> str:
    point = utc_now() - timedelta(hours=hours)
    return point.isoformat().replace("+00:00", "Z")


def parse_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_iso8601(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def recency_factor(updated_at: str | None, half_life_hours: float) -> float:
    dt = parse_iso8601(updated_at)
    if dt is None:
        return 0.0
    age_seconds = max((utc_now() - dt).total_seconds(), 0.0)
    half_life_seconds = max(half_life_hours * 3600.0, 1.0)
    return math.exp(-math.log(2.0) * (age_seconds / half_life_seconds))


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def extract_text_lines(content: str | None) -> list[str]:
    if not content:
        return []
    lines: list[str] = []
    for raw in content.replace("\r", "\n").split("\n"):
        text = raw.strip()
        if not text:
            continue
        lines.append(text)
    return lines
