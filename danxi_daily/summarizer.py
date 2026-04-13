from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .models import RankedPost
from .utils import extract_text_lines


def _load_prompt_template(path: Path) -> str:
    if not path.exists():
        return (
            "You are an editor for a forum daily report. Summarize the post in Simplified Chinese "
            "in at most 2 short sentences. Keep neutral tone and keep key facts."
        )
    return path.read_text(encoding="utf-8")


def _extractive_summary(post: RankedPost, max_chars: int = 120) -> str:
    candidates: list[str] = []

    lines = extract_text_lines(post.excerpt)
    candidates.extend(lines)

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
            candidates.extend(extract_text_lines(text))
        if len(candidates) >= 2:
            break

    merged = " ".join(candidates).strip()
    if not merged:
        merged = "No content snippet is available for this hole."

    if len(merged) > max_chars:
        merged = merged[: max_chars - 3].rstrip() + "..."
    return f"[fallback] {merged}"


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
    content = post.excerpt or "No excerpt"
    user_input = (
        f"Hole ID: {post.hole_id}\n"
        f"Stats: views={post.view}, replies={post.reply}, likes={post.like_sum}\n"
        f"Snippet: {content}\n"
    )

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
            return _openai_summary(prompt, user_input, model, api_key, timeout)
        if normalized == "anthropic":
            model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
            api_key = os.environ["ANTHROPIC_API_KEY"]
            return _anthropic_summary(prompt, user_input, model, api_key, timeout)
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
