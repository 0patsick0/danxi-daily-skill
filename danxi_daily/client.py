from __future__ import annotations

import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .security import sanitize_url_for_log
from .webvpn import WebVPNAuthError, WebVPNClient, WebVPNError


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            f"redirect blocked: {newurl}",
            headers,
            fp,
        )


_SAFE_OPENER = urllib.request.build_opener(_NoRedirect())


def _headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "danxi-daily-skill/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request_json(url: str, params: dict[str, Any], token: str | None, timeout: int) -> Any:
    encoded = urllib.parse.urlencode(
        {k: v for k, v in params.items() if v is not None},
        safe=":-TZ+.,",
    )
    full_url = f"{url}?{encoded}" if encoded else url
    req = urllib.request.Request(full_url, method="GET", headers=_headers(token))
    with _SAFE_OPENER.open(req, timeout=timeout) as resp:
        payload = resp.read().decode("utf-8")
    return json.loads(payload)


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    raise ValueError("API payload is not a hole list")


def _normalize_webvpn_time(value: Any) -> Any:
    # WebVPN /holes uses time-cursor pagination, NOT integer page offsets.
    # Integer 0 ("first page" in direct API) must become a local timestamp
    # so WebVPN can start paging backward from the current moment.
    if isinstance(value, int):
        return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S")
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return value
    # WebVPN /holes endpoint expects local wall-clock timestamp without timezone suffix.
    return dt.astimezone().strftime("%Y-%m-%dT%H:%M:%S")


def _normalize_webvpn_params(params: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(params)
    normalized["start_time"] = _normalize_webvpn_time(normalized.get("start_time"))
    normalized["offset"] = _normalize_webvpn_time(normalized.get("offset"))
    return normalized


def should_prefer_webvpn(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False

    # Known DanXi upstream domains commonly resolve to campus private addresses.
    if host in {"forum.fduhole.com", "api.fduhole.com", "auth.fduhole.com"}:
        return True

    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        return False


def fetch_holes_with_fallback(
    base_urls: list[str],
    start_time: str,
    limit: int,
    offset: int | str | None = None,
    division_id: int | None = None,
    token: str | None = None,
    timeout: int = 15,
    webvpn_client: WebVPNClient | None = None,
    force_webvpn: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    errors: list[str] = []
    for base in base_urls:
        clean_base = base.rstrip("/")
        url = f"{clean_base}/holes"
        params = {
            "start_time": start_time,
            "length": limit,
            "offset": offset,
            "division_id": division_id,
        }
        prefer_webvpn = webvpn_client is not None and (force_webvpn or should_prefer_webvpn(clean_base))

        if prefer_webvpn:
            try:
                webvpn_params = _normalize_webvpn_params(params)
                payload = webvpn_client.request_json(url, params=webvpn_params, token=token, timeout=timeout)
                items = _extract_items(payload)
                return items, clean_base
            except (
                WebVPNError,
                WebVPNAuthError,
                urllib.error.URLError,
                TimeoutError,
                OSError,
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                errors.append(f"{sanitize_url_for_log(clean_base)} via webvpn: {exc}")
                if force_webvpn:
                    continue

        if force_webvpn:
            continue

        try:
            payload = _request_json(url, params=params, token=token, timeout=timeout)
            items = _extract_items(payload)
            return items, clean_base
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{sanitize_url_for_log(clean_base)}: {exc}")
            if webvpn_client is not None:
                try:
                    webvpn_params = _normalize_webvpn_params(params)
                    payload = webvpn_client.request_json(url, params=webvpn_params, token=token, timeout=timeout)
                    items = _extract_items(payload)
                    return items, clean_base
                except (
                    WebVPNError,
                    WebVPNAuthError,
                    urllib.error.URLError,
                    TimeoutError,
                    OSError,
                    ValueError,
                    json.JSONDecodeError,
                ) as vpn_exc:
                    errors.append(f"{sanitize_url_for_log(clean_base)} via webvpn: {vpn_exc}")
    raise RuntimeError("; ".join(errors) if errors else "all endpoints failed")


def fetch_hole_floors(
    base_url: str,
    hole_id: int,
    token: str | None,
    size: int = 40,
    timeout: int = 15,
    webvpn_client: WebVPNClient | None = None,
    force_webvpn: bool = False,
) -> list[dict[str, Any]]:
    clean_base = base_url.rstrip("/")
    params = {"offset": 0, "size": size}
    url = f"{clean_base}/holes/{hole_id}/floors"
    if webvpn_client is not None and force_webvpn:
        try:
            payload = webvpn_client.request_json(url, params=params, token=token, timeout=timeout)
            return _extract_items(payload)
        except (
            WebVPNError,
            WebVPNAuthError,
            urllib.error.URLError,
            TimeoutError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ):
            return []

    try:
        payload = _request_json(url, params=params, token=token, timeout=timeout)
        return _extract_items(payload)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
        if webvpn_client is not None:
            try:
                payload = webvpn_client.request_json(url, params=params, token=token, timeout=timeout)
                return _extract_items(payload)
            except (WebVPNError, WebVPNAuthError, urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
                return []
        return []
