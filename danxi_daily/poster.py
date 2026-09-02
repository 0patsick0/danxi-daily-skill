from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


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


def post_markdown(
    endpoint: str,
    token: str,
    content: str,
    timeout: int = 20,
    division_id: int = 1,
    tags: list[str] | None = None,
    webvpn_client: Any = None,
) -> tuple[int, str]:
    """Post a markdown report to the DanXi forum API.

    Args:
        endpoint: The POST endpoint URL (e.g. https://forum.fduhole.com/api/holes).
        token: Bearer token for authorization.
        content: Markdown content to post.
        timeout: Request timeout in seconds.
        tags: Forum tags to attach (default: ['旦夕日报']).
        webvpn_client: Optional WebVPNClient to proxy the post request.

    Returns:
        Tuple of (HTTP status code, response body string).
    """
    if tags is None:
        tags = ["旦夕日报"]
    
    payload = {
        "content": content,
        "division_id": division_id,
        "tags": [{"name": t} for t in tags],
    }
    
    if webvpn_client:
        # Proxy through WebVPN
        from danxi_daily.webvpn import WEBVPN_HOST, translate_to_webvpn
        proxied_url = translate_to_webvpn(endpoint, allowed_hosts=webvpn_client.allowed_hosts)
        if not proxied_url:
            raise ValueError(f"post endpoint {endpoint} is not supported by webvpn")

        req = urllib.request.Request(
            proxied_url,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "danxi-daily-skill/1.0",
            },
            data=json.dumps(payload).encode("utf-8"),
        )

        def _session_expired(body: str, final_url: str) -> bool:
            # If WebVPN session died during the long generation process, it silently
            # redirects to the CAS login page instead of raising an HTTP error.
            # Prefer the redirect target — the same signal webvpn.py's request_json()
            # uses — and fall back to a content sniff in case the login page URL
            # ever changes shape.
            if final_url.startswith(f"https://{WEBVPN_HOST}/login"):
                return True
            return "资源访问控制系统" in body and "<html" in body

        try:
            webvpn_client._ensure_authenticated()
            body, final_url = webvpn_client._open(req, timeout=timeout)

            if _session_expired(body, final_url):
                reset_session = getattr(webvpn_client, "reset_session", None)
                if callable(reset_session):
                    reset_session()
                else:
                    webvpn_client._authenticated = False
                webvpn_client._ensure_authenticated()
                body, final_url = webvpn_client._open(req, timeout=timeout)
                if _session_expired(body, final_url):
                    return 401, "WebVPN session expired and re-authentication failed"

            return 200, body  # WebVPN _open doesn't return status directly but raises HTTPError on >=400
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", errors="replace")
            
    # Direct post
    req = urllib.request.Request(
        endpoint,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "danxi-daily-skill/1.0",
        },
        data=json.dumps(payload).encode("utf-8"),
    )
    with _SAFE_OPENER.open(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return resp.status, body
