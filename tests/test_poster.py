from __future__ import annotations

import unittest
from unittest.mock import Mock

from danxi_daily.poster import post_markdown
from danxi_daily.webvpn import WEBVPN_HOST


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
        self.assertFalse(client._authenticated)
        self.assertEqual(client._ensure_authenticated.call_count, 2)

    def test_expired_session_still_expired_after_reauth_returns_401(self) -> None:
        client = self._make_client()
        login_url = f"https://{WEBVPN_HOST}/login?cas_login=true"
        client._open.side_effect = [
            ("<html></html>", login_url),
            ("<html></html>", login_url),
        ]

        status, body = post_markdown(
            "https://forum.fduhole.com/api/holes",
            token="t",
            content="hello",
            webvpn_client=client,
        )

        self.assertEqual(status, 401)
        self.assertIn("session expired", body)
        self.assertEqual(client._open.call_count, 2)

    def test_fallback_content_sniff_still_detects_expiry_when_url_unchanged(self) -> None:
        # Regression: if a proxy ever returns the login page body without
        # redirecting the final_url (edge case), the content-based check
        # must still catch it.
        client = self._make_client()
        client._open.side_effect = [
            ("<html>资源访问控制系统</html>", "https://webvpn.fudan.edu.cn/https/xxx/api/holes"),
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


if __name__ == "__main__":
    unittest.main()
