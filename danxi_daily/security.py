from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import quote, quote_plus, urlparse


def parse_host(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.hostname or "").lower()


def require_https(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise ValueError(f"only https is allowed: {url}")


def validate_allowed_host(url: str, allowed_hosts: set[str]) -> None:
    host = parse_host(url)
    if not host:
        raise ValueError(f"invalid URL host: {url}")
    if host not in allowed_hosts:
        raise ValueError(f"host is not allowlisted: {host}")


def normalize_allowed_hosts(text: str) -> set[str]:
    return {x.strip().lower() for x in text.split(",") if x.strip()}


def sanitize_url_for_log(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or "unknown-host"
    path = parsed.path or "/"
    return f"{parsed.scheme}://{host}{path}"


def safe_error_message(exc: BaseException | str, *, secrets: Iterable[str] = ()) -> str:
    """Keep useful failure details without credentials, URL queries or fragments."""
    message = str(exc)

    def clean_url(match: re.Match[str]) -> str:
        try:
            return sanitize_url_for_log(match.group(0))
        except ValueError:
            return "[redacted URL]"

    message = re.sub(r"https?://[^\s<>\"']+", clean_url, message, flags=re.IGNORECASE)
    secret_values: set[str] = set()
    for value in secrets:
        if isinstance(value, str) and value:
            secret_values.update((value, quote(value, safe=""), quote_plus(value)))
    for value in sorted(secret_values, key=len, reverse=True):
        message = message.replace(value, "[redacted]")
    message = re.sub(r"(?i)\bBearer\s+[^\s,;\"'}]+", "Bearer [redacted]", message)
    message = re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "[redacted]", message)
    message = re.sub(
        r"(?i)(\b(?:authorization|access|refresh|(?:access[_-]?|refresh[_-]?|login)?token|"
        r"password|passwd|pwd|username|cookie|ticket|lck)\b[\"']?\s*[:=]\s*)"
        r"(?:\"[^\"]*\"|'[^']*'|[^\s,;}\]]+)",
        r"\1[redacted]",
        message,
    )
    return " ".join(message.split())[:1000]
