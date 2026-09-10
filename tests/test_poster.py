from __future__ import annotations

import unittest
import io
import urllib.error
from unittest.mock import Mock
from unittest.mock import patch

from danxi_daily.poster import PostError, post_markdown
from danxi_daily.webvpn import WEBVPN_HOST, WebVPNAuthError, translate_to_webvpn


class PosterWebvpnSessionExpiryTests(unittest.TestCase):
    def _make_client(self, allowed_hosts=None):
        client = Mock()
        client.allowed_hosts = allowed_hosts or {"forum.fduhole.com"}
        return client

    def test_success_without_expiry(self) -> None:
        client = self._make_client()
        client._open.return_value = ('{"ok": true}', "https://webvpn.fudan.edu.cn/https/xxx/api/holes")

        status, body = post_markdown(
            "https://forum.fduhole.com/api/holes",
            token="t",
            content="hello",
            webvpn_client=client,
        )

        self.assertEqual(status, 200)
        self.assertEqual(body, '{"ok": true}')
        self.assertEqual(client._open.call_count, 1)

    def test_expired_session_detected_via_redirect_url_and_recovers(self) -> None:
        client = self._make_client()
        login_url = f"https://{WEBVPN_HOST}/login?cas_login=true"
        client._open.side_effect = [
            ("<html>whatever, no chinese marker</html>", login_url),
            ('{"ok": true}', "https://webvpn.fudan.edu.cn/https/xxx/api/holes"),
        ]

        status, body = post_markdown(
            "https://forum.fduhole.com/api/holes",
            token="t",
            content="hello",
            webvpn_client=client,
        )

        self.assertEqual(status, 200)
        self.assertEqual(body, '{"ok": true}')
        self.assertEqual(client._open.call_count, 2)
        self.assertEqual(client.reset_session.call_count, 1)
        self.assertEqual(client._ensure_authenticated.call_count, 2)

    def test_expired_session_still_expired_after_reauth_raises_auth_error(self) -> None:
        client = self._make_client()
        login_url = f"https://{WEBVPN_HOST}/login?cas_login=true"
        client._open.side_effect = [
            ("<html></html>", login_url),
            ("<html></html>", login_url),
        ]

        with self.assertRaisesRegex(WebVPNAuthError, "session expired"):
            post_markdown(
                "https://forum.fduhole.com/api/holes",
                token="t",
                content="hello",
                webvpn_client=client,
            )
        self.assertEqual(client._open.call_count, 2)

    def test_fallback_content_sniff_still_detects_expiry_when_url_unchanged(self) -> None:
        # Regression: if a proxy ever returns the login page body without
        # redirecting the final_url (edge case), the content-based check
        # must still catch it.
        client = self._make_client()
        client._open.side_effect = [
            ('<html>资源访问控制系统<form action="/do-login"><input name="password"></form></html>', "https://webvpn.fudan.edu.cn/https/xxx/api/holes"),
            ('{"ok": true}', "https://webvpn.fudan.edu.cn/https/xxx/api/holes"),
        ]

        status, body = post_markdown(
            "https://forum.fduhole.com/api/holes",
            token="t",
            content="hello",
            webvpn_client=client,
        )

        self.assertEqual(status, 200)
        self.assertEqual(body, '{"ok": true}')
        self.assertEqual(client._open.call_count, 2)

    def test_proxy_error_html_is_not_success_and_is_not_replayed(self) -> None:
        client = self._make_client()
        client._open.return_value = ("<html>upstream unavailable</html>", "https://webvpn.fudan.edu.cn/https/xxx/api/holes")
        with self.assertRaisesRegex(PostError, "non-JSON"):
            post_markdown("https://forum.fduhole.com/api/holes", "t", "hello", webvpn_client=client)
        self.assertEqual(client._open.call_count, 1)
        client.reset_session.assert_not_called()

    def test_post_bounced_to_gateway_portal_recovers_once(self) -> None:
        client = self._make_client()
        client._open.side_effect = [
            ('<html><title>资源访问控制系统 - 资源站点</title></html>', f"https://{WEBVPN_HOST}/"),
            ('{"hole_id":123}', "https://webvpn.fudan.edu.cn/https/xxx/api/holes"),
        ]
        status, _ = post_markdown("https://forum.fduhole.com/api/holes", "t", "hello", webvpn_client=client)
        self.assertEqual(status, 200)
        self.assertEqual(client._open.call_count, 2)
        client.reset_session.assert_called_once()

    def test_forum_401_remains_distinct_from_webvpn_session_failure(self) -> None:
        client = self._make_client()
        client._open.side_effect = urllib.error.HTTPError(
            translate_to_webvpn("https://forum.fduhole.com/api/holes"), 401, "Unauthorized", {}, io.BytesIO(b'{"exp":"token expired"}')
        )
        status, _ = post_markdown("https://forum.fduhole.com/api/holes", "t", "hello", webvpn_client=client)
        self.assertEqual(status, 401)
        client.reset_session.assert_not_called()

    def test_cas_401_is_not_treated_as_forum_token_expiry(self) -> None:
        for stage in ("_ensure_authenticated", "_open"):
            with self.subTest(stage=stage):
                client = self._make_client()
                getattr(client, stage).side_effect = urllib.error.HTTPError(
                    "https://id.fudan.edu.cn/idp/authn/authExecute", 401, "Unauthorized", {}, io.BytesIO(b"CAS rejected")
                )
                with self.assertRaises(WebVPNAuthError):
                    post_markdown("https://forum.fduhole.com/api/holes", "t", "hello", webvpn_client=client)
                client.obtain_forum_api_token.assert_not_called()

    @patch("danxi_daily.poster._SAFE_OPENER")
    def test_direct_http_error_is_reported_to_pipeline(self, opener) -> None:
        opener.open.side_effect = urllib.error.HTTPError(
            "https://forum.fduhole.com/api/holes", 401, "Unauthorized", {}, io.BytesIO(b'{"exp":"token expired"}')
        )
        status, _ = post_markdown("https://forum.fduhole.com/api/holes", "t", "hello")
        self.assertEqual(status, 401)
        opener.open.assert_called_once()


if __name__ == "__main__":
    unittest.main()
