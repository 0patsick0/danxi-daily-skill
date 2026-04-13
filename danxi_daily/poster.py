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
) -> tuple[int, str]:
    payload = {"content": content}
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
