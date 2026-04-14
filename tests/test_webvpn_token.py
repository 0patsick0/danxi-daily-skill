from __future__ import annotations

import io
import json
import unittest
import urllib.error
import urllib.request

from danxi_daily.webvpn import WebVPNClient, WebVPNCredentials, WebVPNAuthError, _PreserveMethodRedirectHandler


def _http_error(code: int, body: dict[str, str]) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://webvpn.fudan.edu.cn/mock",
        code=code,
        msg="error",
        hdrs=None,
        fp=io.BytesIO(json.dumps(body).encode("utf-8")),
    )


class WebvpnTokenTests(unittest.TestCase):
    def test_preserve_redirect_blocks_untrusted_host(self) -> None:
        handler = _PreserveMethodRedirectHandler()
        req = urllib.request.Request(
            "https://webvpn.fudan.edu.cn/mock",
            data=b"email=a&password=b",
            method="POST",
        )

        with self.assertRaises(WebVPNAuthError):
            handler.redirect_request(req, fp=None, code=307, msg="", headers={}, newurl="https://evil.example/steal")

    def test_preserve_redirect_allows_trusted_host(self) -> None:
        handler = _PreserveMethodRedirectHandler()
        req = urllib.request.Request(
            "https://webvpn.fudan.edu.cn/mock",
            data=b"email=a&password=b",
            method="POST",
        )

        redirected = handler.redirect_request(
            req,
            fp=None,
            code=307,
            msg="",
            headers={},
            newurl="https://webvpn.fudan.edu.cn/next",
        )

        self.assertIsNotNone(redirected)
        assert redirected is not None
        self.assertEqual(redirected.get_full_url(), "https://webvpn.fudan.edu.cn/next")

    def test_candidate_email_variants(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="24307100036", password="x"), allowed_hosts={"forum.fduhole.com"})
        self.assertEqual(
            client._candidate_forum_emails(),
            ["24307100036@m.fudan.edu.cn", "24307100036@fudan.edu.cn"],
        )

    def test_obtain_forum_api_token_success(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"), allowed_hosts={"forum.fduhole.com"})
        client._ensure_authenticated = lambda: None  # type: ignore[method-assign]

        calls: list[str] = []

        def fake_open(req, timeout=None):
            calls.append(req.full_url)
            return json.dumps({"access": "token-123"}), req.full_url

        client._open_following_post_redirects = fake_open  # type: ignore[method-assign]

        from unittest.mock import patch

        with patch("danxi_daily.webvpn.translate_to_webvpn", return_value="https://webvpn.fudan.edu.cn/mock"):
            token = client.obtain_forum_api_token()

        self.assertEqual(token, "token-123")
        self.assertEqual(len(calls), 1)

    def test_obtain_forum_api_token_retries_next_email(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="24307100036", password="pwd"), allowed_hosts={"forum.fduhole.com"})
        client._ensure_authenticated = lambda: None  # type: ignore[method-assign]

        first = _http_error(403, {"message": "account not registered"})
        second = (json.dumps({"access": "token-ok"}), "https://webvpn.fudan.edu.cn/mock")
        responses = [first, second]

        def fake_open(req, timeout=None):
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        client._open_following_post_redirects = fake_open  # type: ignore[method-assign]

        from unittest.mock import patch

        with patch("danxi_daily.webvpn.translate_to_webvpn", return_value="https://webvpn.fudan.edu.cn/mock"):
            token = client.obtain_forum_api_token()

        self.assertEqual(token, "token-ok")

    def test_obtain_forum_api_token_raises_when_all_fail(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"), allowed_hosts={"forum.fduhole.com"})
        client._ensure_authenticated = lambda: None  # type: ignore[method-assign]

        def fake_open(req, timeout=None):
            raise _http_error(403, {"message": "no such account"})

        client._open_following_post_redirects = fake_open  # type: ignore[method-assign]

        from unittest.mock import patch

        with patch("danxi_daily.webvpn.translate_to_webvpn", return_value="https://webvpn.fudan.edu.cn/mock"):
            with self.assertRaises(WebVPNAuthError):
                client.obtain_forum_api_token()


if __name__ == "__main__":
    unittest.main()
