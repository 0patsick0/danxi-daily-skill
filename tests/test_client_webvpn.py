from __future__ import annotations

from datetime import datetime
import urllib.error
import unittest
from unittest.mock import Mock, patch

from danxi_daily.client import fetch_holes_with_fallback
from danxi_daily.webvpn import translate_to_webvpn


class ClientWebvpnFallbackTests(unittest.TestCase):
    @patch("danxi_daily.client.should_prefer_webvpn", return_value=True)
    @patch("danxi_daily.client._request_json")
    def test_private_host_prefers_webvpn_before_direct(self, mock_request_json, _mock_prefer) -> None:
        webvpn_client = Mock()
        webvpn_client.request_json.return_value = [{"hole_id": 9}]

        holes, _ = fetch_holes_with_fallback(
            base_urls=["https://forum.fduhole.com/api"],
            start_time="2026-01-01T00:00:00Z",
            limit=10,
            offset=None,
            division_id=None,
            token=None,
            webvpn_client=webvpn_client,
        )

        self.assertEqual(holes[0]["hole_id"], 9)
        mock_request_json.assert_not_called()

    @patch("danxi_daily.client.should_prefer_webvpn", return_value=True)
    @patch("danxi_daily.client._request_json")
    def test_private_host_webvpn_failure_falls_back_to_direct(self, mock_request_json, _mock_prefer) -> None:
        mock_request_json.return_value = [{"hole_id": 7}]
        webvpn_client = Mock()
        webvpn_client.request_json.side_effect = urllib.error.URLError("vpn down")

        holes, _ = fetch_holes_with_fallback(
            base_urls=["https://forum.fduhole.com/api"],
            start_time="2026-01-01T00:00:00Z",
            limit=10,
            offset=None,
            division_id=None,
            token=None,
            webvpn_client=webvpn_client,
        )

        self.assertEqual(holes[0]["hole_id"], 7)
        self.assertEqual(webvpn_client.request_json.call_count, 1)
        self.assertEqual(mock_request_json.call_count, 1)

    @patch("danxi_daily.client._request_json")
    def test_fallback_to_webvpn_on_direct_failure(self, mock_request_json) -> None:
        mock_request_json.side_effect = urllib.error.URLError("tls timeout")
        webvpn_client = Mock()
        webvpn_client.request_json.return_value = [{"hole_id": 1}]

        holes, endpoint = fetch_holes_with_fallback(
            base_urls=["https://forum.fduhole.com/api"],
            start_time="2026-01-01T00:00:00Z",
            limit=10,
            offset=None,
            division_id=None,
            token=None,
            webvpn_client=webvpn_client,
        )

        self.assertEqual(endpoint, "https://forum.fduhole.com/api")
        self.assertEqual(len(holes), 1)
        self.assertEqual(holes[0]["hole_id"], 1)
        self.assertEqual(webvpn_client.request_json.call_count, 1)

    @patch("danxi_daily.client.should_prefer_webvpn", return_value=False)
    @patch("danxi_daily.client._request_json")
    def test_direct_success_skips_webvpn(self, mock_request_json, _mock_prefer) -> None:
        mock_request_json.return_value = [{"hole_id": 2}]
        webvpn_client = Mock()

        holes, _ = fetch_holes_with_fallback(
            base_urls=["https://forum.fduhole.com/api"],
            start_time="2026-01-01T00:00:00Z",
            limit=10,
            offset=None,
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
            offset=None,
            division_id=None,
            token=None,
            webvpn_client=webvpn_client,
            force_webvpn=True,
        )

        self.assertEqual(holes[0]["hole_id"], 3)
        mock_request_json.assert_not_called()

    @patch("danxi_daily.client.should_prefer_webvpn", return_value=True)
    @patch("danxi_daily.client._request_json")
    def test_webvpn_normalizes_time_params(self, mock_request_json, _mock_prefer) -> None:
        webvpn_client = Mock()
        webvpn_client.request_json.return_value = [{"hole_id": 10}]

        holes, _ = fetch_holes_with_fallback(
            base_urls=["https://forum.fduhole.com/api"],
            start_time="2026-04-15T16:00:00Z",
            limit=10,
            offset="2026-04-15T17:01:02+08:00",
            division_id=None,
            token=None,
            webvpn_client=webvpn_client,
        )

        self.assertEqual(holes[0]["hole_id"], 10)
        mock_request_json.assert_not_called()
        kwargs = webvpn_client.request_json.call_args.kwargs
        params = kwargs["params"]
        expected_start = datetime.fromisoformat("2026-04-15T16:00:00+00:00").astimezone().strftime("%Y-%m-%dT%H:%M:%S")
        expected_offset = datetime.fromisoformat("2026-04-15T17:01:02+08:00").astimezone().strftime("%Y-%m-%dT%H:%M:%S")
        self.assertEqual(params["start_time"], expected_start)
        self.assertEqual(params["offset"], expected_offset)

    @patch("danxi_daily.client.should_prefer_webvpn", return_value=False)
    @patch("danxi_daily.client._request_json")
    def test_webvpn_fallback_converts_integer_offset_to_timestamp(self, mock_request_json, _mock_prefer) -> None:
        """Regression: integer offset=0 must NOT be sent to WebVPN as the string '0'.
        WebVPN /holes uses time-cursor pagination; sending offset=0 causes HTTP 400."""
        mock_request_json.side_effect = urllib.error.URLError("timed out")
        webvpn_client = Mock()
        webvpn_client.request_json.return_value = [{"hole_id": 42}]

        holes, _ = fetch_holes_with_fallback(
            base_urls=["https://forum.fduhole.com/api"],
            start_time="2026-04-15T16:00:00Z",
            limit=10,
            offset=0,          # integer offset — the bug case
            division_id=None,
            token=None,
            webvpn_client=webvpn_client,
        )

        self.assertEqual(holes[0]["hole_id"], 42)
        kwargs = webvpn_client.request_json.call_args.kwargs
        params = kwargs["params"]
        # offset must be a timestamp string, never "0" or integer 0
        self.assertIsInstance(params["offset"], str)
        self.assertNotEqual(params["offset"], "0")
        self.assertNotEqual(params["offset"], 0)
        # must match YYYY-MM-DDTHH:MM:SS format
        import re
        self.assertRegex(params["offset"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


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
