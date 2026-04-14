from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .models import RankedPost
from .utils import clean_publish_text, extract_text_lines


def _load_prompt_template(path: Path) -> str:
    if not path.exists():
        return (
            "You are an editor for a forum daily report. Summarize the post in Simplified Chinese "
            "in at most 2 short sentences. Keep neutral tone and keep key facts."
        )
    return path.read_text(encoding="utf-8")


def _collect_candidate_lines(post: RankedPost, max_lines: int = 8) -> list[str]:
    candidates: list[str] = []
    candidates.extend(extract_text_lines(clean_publish_text(post.excerpt)))

    floors = post.raw.get("floors")
    if not isinstance(floors, dict):
        floors = {}
    prefetch = floors.get("prefetch")
    if not isinstance(prefetch, list):
        prefetch = []

    for floor in prefetch:
        if not isinstance(floor, dict):
            continue
        text = floor.get("content")
        if isinstance(text, str):
            candidates.extend(extract_text_lines(clean_publish_text(text)))
        if len(candidates) >= max_lines:
            break

    deduped: list[str] = []
    seen: set[str] = set()
    for line in candidates:
        text = line.strip()
        if not text or text in seen:
            continue
        deduped.append(text)
        seen.add(text)
        if len(deduped) >= max_lines:
            break
    return deduped


def _extractive_summary(post: RankedPost, max_chars: int = 120) -> str:
    lines = _collect_candidate_lines(post)

    if not lines:
        return "该帖信息较少，当前可提炼的核心观点有限。"

    topic = lines[0][:28]
    detail = ""
    for line in lines[1:]:
        if line and line != topic:
            detail = line[:36]
            break

    if detail:
        summary = (
            f"该帖主要围绕“{topic}”展开，评论中提到“{detail}”等观点。"
        )
    else:
        summary = f"该帖主要围绕“{topic}”展开。"

    if len(summary) > max_chars:
        summary = summary[: max_chars - 1].rstrip() + "…"
    return summary


def _build_user_input(post: RankedPost) -> str:
    lines = _collect_candidate_lines(post, max_lines=6)
    snippet = "；".join(lines[:4]).strip()
    if not snippet:
        snippet = "信息较少"

    return (
        f"Hole ID: {post.hole_id}\n"
        f"Snippet: {snippet}\n"
    )


def _openai_summary(prompt: str, user_input: str, model: str, api_key: str, timeout: int) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_input},
        ],
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "danxi-daily-skill/1.0",
        },
        data=json.dumps(payload).encode("utf-8"),
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        raise ValueError("openai choices is empty")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("openai first choice is invalid")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError("openai message is invalid")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("openai content is empty")
    return content.strip()


def _anthropic_summary(prompt: str, user_input: str, model: str, api_key: str, timeout: int) -> str:
    payload = {
        "model": model,
        "max_tokens": 220,
        "temperature": 0.2,
        "system": prompt,
        "messages": [{"role": "user", "content": user_input}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "User-Agent": "danxi-daily-skill/1.0",
        },
        data=json.dumps(payload).encode("utf-8"),
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    if not isinstance(data, dict):
        raise ValueError("anthropic response is invalid")

    content_blocks = data.get("content")
    if not isinstance(content_blocks, list):
        raise ValueError("anthropic content blocks are invalid")

    text_parts: list[str] = []
    for block in content_blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text_parts.append(str(block.get("text", "")))

    merged = "".join(text_parts).strip()
    if not merged:
        raise ValueError("anthropic content is empty")
    return merged


def summarize_post(
    post: RankedPost,
    prompt_path: Path,
    provider: str = "auto",
    timeout: int = 25,
) -> str:
    prompt = _load_prompt_template(prompt_path)
    user_input = _build_user_input(post)

    normalized = provider.strip().lower()
    if normalized == "auto":
        if os.getenv("ANTHROPIC_API_KEY"):
            normalized = "anthropic"
        elif os.getenv("OPENAI_API_KEY"):
            normalized = "openai"
        else:
            normalized = "none"

    try:
        if normalized == "openai":
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            api_key = os.environ["OPENAI_API_KEY"]
            content = _openai_summary(prompt, user_input, model, api_key, timeout)
            cleaned = clean_publish_text(content)
            return cleaned or _extractive_summary(post)
        if normalized == "anthropic":
            model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
            api_key = os.environ["ANTHROPIC_API_KEY"]
            content = _anthropic_summary(prompt, user_input, model, api_key, timeout)
            cleaned = clean_publish_text(content)
            return cleaned or _extractive_summary(post)
    except (
        KeyError,
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
        IndexError,
        TypeError,
        AttributeError,
        ValueError,
    ):
        return _extractive_summary(post)

    return _extractive_summary(post)
