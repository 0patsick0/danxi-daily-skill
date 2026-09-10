#!/usr/bin/env python3
"""Diagnose one WebVPN login without fetching a forum token or posting."""
from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from danxi_daily.security import safe_error_message
from danxi_daily.webvpn import WebVPNClient, WebVPNCredentials


class _PageShape(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict[str, Any]] = []
        self.inputs: list[dict[str, str]] = []
        self.hidden_values: list[str] = []
        self.title_parts: list[str] = []
        self.scripts: list[str] = []
        self._in_title = False
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "script":
            self._in_script = True
        elif tag == "form":
            self.forms.append({
                "id": attributes.get("id") or "",
                "method": (attributes.get("method") or "GET").upper(),
                "action": attributes.get("action") or "",
            })
        elif tag == "input":
            self.inputs.append({
                "name": attributes.get("name") or "",
                "type": attributes.get("type") or "text",
            })
            # Values are used only for redaction and never returned in output.
            value = attributes.get("value")
            if value:
                self.hidden_values.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._in_script:
            self.scripts.append(data)


class DiagnosticWebVPNClient(WebVPNClient):
    def __init__(self, credentials: WebVPNCredentials) -> None:
        super().__init__(credentials, timeout=60)
        self.max_retries = 1
        self._diagnostic_secrets = {credentials.username, credentials.password}
        self._step = 0

    def _safe(self, value: str) -> str:
        return safe_error_message(value, secrets=self._diagnostic_secrets)

    def _remember(self, values: list[str]) -> None:
        self._diagnostic_secrets.update(value for value in values if len(value) >= 4)

    def _url_shape(self, url: str, base: str = "") -> dict[str, Any]:
        try:
            parsed = urllib.parse.urlsplit(urllib.parse.urljoin(base, html.unescape(url)))
            pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            self._remember([value for _, value in pairs])
            self._remember([parsed.fragment, parsed.username or "", parsed.password or ""])
            return {
                "host": self._safe(parsed.hostname or ""),
                "path": self._safe(parsed.path or "/"),
                "query_keys": sorted({self._safe(key) for key, _ in pairs}),
                "has_fragment": bool(parsed.fragment),
            }
        except ValueError:
            return {"invalid_url": True}

    def _cookies(self) -> list[dict[str, str]]:
        cookies = list(self._cookie_jar)
        self._remember([cookie.value for cookie in cookies])
        return [{
            "name": self._safe(cookie.name),
            "domain": self._safe(cookie.domain),
            "path": self._safe(cookie.path),
        } for cookie in cookies]

    def _page_shape(self, body: str, final_url: str) -> dict[str, Any]:
        page = _PageShape()
        page.feed(body)
        self._remember(page.hidden_values)
        script = html.unescape("\n".join(page.scripts))
        redirects: list[dict[str, Any]] = []
        # Match only literal URL assignments/calls, never execute page JavaScript.
        pattern = (
            r"(?P<source>(?:(?:window|top|self|document)\.)?location(?:\.href)?|locationValue)"
            r"\s*=\s*(?P<quote>[\"'])(?P<url>.*?)(?P=quote)"
            r"|(?P<call>(?:(?:window|top|self|document)\.)?location\.(?:assign|replace))"
            r"\s*\(\s*(?P<callquote>[\"'])(?P<callurl>.*?)(?P=callquote)\s*\)"
        )
        for match in re.finditer(pattern, script, flags=re.IGNORECASE):
            url = (match.group("url") or match.group("callurl") or "").replace(r"\/", "/")
            url = re.sub(r"\\u([0-9a-fA-F]{4})", lambda item: chr(int(item.group(1), 16)), url)
            redirects.append({
                "source": match.group("source") or match.group("call"),
                "target": self._url_shape(url, final_url),
            })
        forms = [{
            "id": self._safe(form["id"]),
            "method": self._safe(form["method"]),
            "action": self._url_shape(form["action"], final_url),
        } for form in page.forms]
        return {
            "title": self._safe(" ".join(page.title_parts))[:200],
            "forms": forms,
            "inputs": [{key: self._safe(value) for key, value in item.items()} for item in page.inputs],
            "static_redirects": redirects,
        }

    def _emit(self, **record: Any) -> None:
        print(json.dumps(record, ensure_ascii=False), flush=True)

    def _attempt_open_with_retries(
        self, opener: Any, request: str | urllib.request.Request, timeout: int
    ) -> tuple[str, str]:
        self._step += 1
        step = self._step
        url = request.full_url if isinstance(request, urllib.request.Request) else request
        method = request.get_method() if isinstance(request, urllib.request.Request) else "GET"
        self._emit(step=step, event="request", method=method, url=self._url_shape(url))
        try:
            body, final_url = super()._attempt_open_with_retries(opener, request, min(timeout, 60))
        except Exception as exc:
            cookies = self._cookies()
            self._emit(step=step, event="request_failed", error=self._safe(str(exc)), cookies=cookies)
            raise
        # Collect cookie/input/query secrets before rendering any page metadata.
        cookies = self._cookies()
        final_shape = self._url_shape(final_url)
        page_shape = self._page_shape(body, final_url)
        self._emit(step=step, event="response", final_url=final_shape, page=page_shape, cookies=cookies)
        return body, final_url


def main() -> int:
    username = (os.getenv("DANXI_WEBVPN_USERNAME") or "").strip()
    password = (os.getenv("DANXI_WEBVPN_PASSWORD") or "").strip()
    if not username or not password:
        print(json.dumps({"authenticated": False, "error": "WebVPN credentials are missing"}), flush=True)
        return 1
    client = DiagnosticWebVPNClient(WebVPNCredentials(username=username, password=password))
    try:
        client._ensure_authenticated()
    except Exception as exc:
        client._emit(authenticated=False, error=client._safe(str(exc)))
        return 1
    client._emit(authenticated=client._authenticated)
    return 0 if client._authenticated else 1


if __name__ == "__main__":
    raise SystemExit(main())
