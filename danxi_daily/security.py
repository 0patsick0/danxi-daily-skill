from __future__ import annotations

from urllib.parse import urlparse


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
