from __future__ import annotations

import urllib.error
import unittest
from unittest.mock import Mock, patch

from danxi_daily.client import fetch_holes_with_fallback
from danxi_daily.webvpn import translate_to_webvpn


class ClientWebvpnFallbackTests(unittest.TestCase):
    @patch("danxi_daily.client._request_json")
    def test_fallback_to_webvpn_on_direct_failure(self, mock_request_json) -> None:
        mock_request_json.side_effect = urllib.error.URLError("tls timeout")
        webvpn_client = Mock()
        webvpn_client.request_json.return_value = [{"hole_id": 1}]

        holes, endpoint = fetch_holes_with_fallback(
            base_urls=["https://forum.fduhole.com/api"],
            start_time="2026-01-01T00:00:00Z",
            limit=10,
            division_id=None,
            token=None,
            webvpn_client=webvpn_client,
        )

        self.assertEqual(endpoint, "https://forum.fduhole.com/api")
        self.assertEqual(len(holes), 1)
        self.assertEqual(holes[0]["hole_id"], 1)
        self.assertEqual(webvpn_client.request_json.call_count, 1)

    @patch("danxi_daily.client._request_json")
    def test_direct_success_skips_webvpn(self, mock_request_json) -> None:
        mock_request_json.return_value = [{"hole_id": 2}]
        webvpn_client = Mock()

        holes, _ = fetch_holes_with_fallback(
            base_urls=["https://forum.fduhole.com/api"],
            start_time="2026-01-01T00:00:00Z",
            limit=10,
            division_id=None,
            token=None,
            webvpn_client=webvpn_client,
        )

        self.assertEqual(holes[0]["hole_id"], 2)
        webvpn_client.request_json.assert_not_called()

    @patch("danxi_daily.client._request_json")
    def test_force_webvpn_skips_direct(self, mock_request_json) -> None:
        webvpn_client = Mock()
        webvpn_client.request_json.return_value = [{"hole_id": 3}]

        holes, _ = fetch_holes_with_fallback(
            base_urls=["https://forum.fduhole.com/api"],
            start_time="2026-01-01T00:00:00Z",
            limit=10,
            division_id=None,
            token=None,
            webvpn_client=webvpn_client,
            force_webvpn=True,
        )

        self.assertEqual(holes[0]["hole_id"], 3)
        mock_request_json.assert_not_called()


class WebvpnUrlTranslationTests(unittest.TestCase):
    def test_translate_to_webvpn_for_forum_host(self) -> None:
        translated = translate_to_webvpn(
            "https://forum.fduhole.com/api/holes?length=1",
            allowed_hosts={"forum.fduhole.com"},
        )

        self.assertIsNotNone(translated)
        assert translated is not None
        self.assertTrue(translated.startswith("https://webvpn.fudan.edu.cn/https/"))
        self.assertTrue(translated.endswith("/api/holes?length=1"))


if __name__ == "__main__":
    unittest.main()
