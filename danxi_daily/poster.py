from __future__ import annotations

import json
import urllib.error
import urllib.request


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
) -> tuple[int, str]:
    """Post a markdown report to the DanXi forum API.

    Args:
        endpoint: The POST endpoint URL (e.g. https://forum.fduhole.com/api/holes).
        token: Bearer token for authorization.
        content: Markdown content to post.
        timeout: Request timeout in seconds.
        division_id: Forum division ID to post to (default 1 = 树洞).

    Returns:
        Tuple of (HTTP status code, response body string).
    """
    payload = {
        "content": content,
        "division_id": division_id,
    }
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
