from __future__ import annotations

from datetime import datetime
import urllib.error
import unittest
from unittest.mock import Mock, patch

from danxi_daily.client import fetch_hole_floors, fetch_holes_with_fallback
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


class FetchHoleFloorsPaginationTests(unittest.TestCase):
    """The forum API caps a single /floors response at 10 items regardless of
    the requested "size". fetch_hole_floors must page through offset to
    collect the full requested amount."""

    @patch("danxi_daily.client._request_json")
    def test_pages_until_requested_size_is_collected(self, mock_request_json) -> None:
        # Server always caps each page at 10 items, no matter what size is requested.
        page1 = [{"id": i} for i in range(10)]
        page2 = [{"id": i} for i in range(10, 20)]
        page3 = [{"id": i} for i in range(20, 25)]  # short page: signals end of data
        mock_request_json.side_effect = [page1, page2, page3]

        floors = fetch_hole_floors(
            base_url="https://forum.fduhole.com/api",
            hole_id=123,
            token=None,
            size=40,
        )

        self.assertEqual(len(floors), 25)
        self.assertEqual([f["id"] for f in floors], list(range(25)))
        self.assertEqual(mock_request_json.call_count, 3)

        offsets = [call.kwargs["params"]["offset"] for call in mock_request_json.call_args_list]
        self.assertEqual(offsets, [0, 10, 20])
        sizes = [call.kwargs["params"]["size"] for call in mock_request_json.call_args_list]
        self.assertEqual(sizes, [10, 10, 10])

    @patch("danxi_daily.client._request_json")
    def test_stops_early_when_full_page_returned_but_size_reached(self, mock_request_json) -> None:
        mock_request_json.return_value = [{"id": i} for i in range(10)]

        floors = fetch_hole_floors(
            base_url="https://forum.fduhole.com/api",
            hole_id=123,
            token=None,
            size=10,
        )

        self.assertEqual(len(floors), 10)
        self.assertEqual(mock_request_json.call_count, 1)

    @patch("danxi_daily.client._request_json")
    def test_stops_when_page_returns_empty(self, mock_request_json) -> None:
        page1 = [{"id": i} for i in range(10)]
        mock_request_json.side_effect = [page1, []]

        floors = fetch_hole_floors(
            base_url="https://forum.fduhole.com/api",
            hole_id=123,
            token=None,
            size=40,
        )

        self.assertEqual(len(floors), 10)
        self.assertEqual(mock_request_json.call_count, 2)

    @patch("danxi_daily.client._request_json")
    def test_never_requests_page_size_above_ten(self, mock_request_json) -> None:
        mock_request_json.return_value = [{"id": i} for i in range(3)]

        fetch_hole_floors(
            base_url="https://forum.fduhole.com/api",
            hole_id=123,
            token=None,
            size=100,
        )

        sizes = [call.kwargs["params"]["size"] for call in mock_request_json.call_args_list]
        self.assertTrue(all(s <= 10 for s in sizes))

    def test_webvpn_force_mode_paginates_through_webvpn_client(self) -> None:
        webvpn_client = Mock()
        page1 = [{"id": i} for i in range(10)]
        page2 = [{"id": i} for i in range(10, 15)]
        webvpn_client.request_json.side_effect = [page1, page2]

        floors = fetch_hole_floors(
            base_url="https://forum.fduhole.com/api",
            hole_id=123,
            token=None,
            size=40,
            webvpn_client=webvpn_client,
            force_webvpn=True,
        )

        self.assertEqual(len(floors), 15)
        self.assertEqual(webvpn_client.request_json.call_count, 2)

    @patch("danxi_daily.client._request_json")
    def test_direct_failure_falls_back_to_webvpn_pagination(self, mock_request_json) -> None:
        mock_request_json.side_effect = urllib.error.URLError("timed out")
        webvpn_client = Mock()
        page1 = [{"id": i} for i in range(10)]
        page2 = [{"id": i} for i in range(10, 12)]
        webvpn_client.request_json.side_effect = [page1, page2]

        floors = fetch_hole_floors(
            base_url="https://forum.fduhole.com/api",
            hole_id=123,
            token=None,
            size=40,
            webvpn_client=webvpn_client,
        )

        self.assertEqual(len(floors), 12)
        self.assertEqual(webvpn_client.request_json.call_count, 2)

    @patch("danxi_daily.client._request_json")
    def test_returns_empty_list_when_all_paths_fail(self, mock_request_json) -> None:
        mock_request_json.side_effect = urllib.error.URLError("timed out")

        floors = fetch_hole_floors(
            base_url="https://forum.fduhole.com/api",
            hole_id=123,
            token=None,
            size=40,
            webvpn_client=None,
        )

        self.assertEqual(floors, [])


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
