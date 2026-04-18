from __future__ import annotations

import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from danxi_daily.pipeline import PipelineConfig, run_pipeline
from danxi_daily.utils import parse_iso8601


def _fake_hole(hole_id: int) -> dict:
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "hole_id": hole_id,
        "division_id": 1,
        "view": 120,
        "reply": 12,
        "time_created": now_utc,
        "time_updated": now_utc,
        "floors": {
            "prefetch": [
                {"floor_id": 1, "like": 3, "content": "sample floor"},
            ]
        },
    }


class PipelineDryRunTests(unittest.TestCase):
    @patch("danxi_daily.pipeline.fetch_hole_floors", return_value=[])
    @patch("danxi_daily.pipeline.fetch_holes_with_fallback")
    def test_pipeline_generates_files_without_post(
        self,
        mock_fetch_holes,
        _mock_fetch_floors,
    ) -> None:
        mock_fetch_holes.return_value = ([_fake_hole(1), _fake_hole(2)], "https://forum.fduhole.com/api")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = PipelineConfig(
                base_urls=["https://forum.fduhole.com/api"],
                output_markdown=root / "daily.md",
                output_holes=root / "holes.json",
                output_ranked=root / "ranked.json",
                prompt_path=root / "prompt.md",
                llm_provider="none",
                post=False,
            )
            result = run_pipeline(config)

            self.assertEqual(result["top"], 2)
            self.assertIsNone(result["post_result"])
            self.assertTrue((root / "daily.md").exists())
            self.assertTrue((root / "holes.json").exists())
            self.assertTrue((root / "ranked.json").exists())

    @patch("danxi_daily.pipeline.fetch_holes_with_fallback")
    def test_floor_enrichment_uses_parallel_workers(self, mock_fetch_holes) -> None:
        holes = [_fake_hole(100 + idx) for idx in range(8)]
        for hole in holes:
            hole.pop("floors", None)
        mock_fetch_holes.return_value = (holes, "https://forum.fduhole.com/api")

        lock = threading.Lock()
        active = {"count": 0, "max": 0}

        def _slow_fetch(*_args, **_kwargs):
            with lock:
                active["count"] += 1
                active["max"] = max(active["max"], active["count"])
            try:
                time.sleep(0.05)
                return [{"floor_id": 1, "like": 1, "content": "ok"}]
            finally:
                with lock:
                    active["count"] -= 1

        with patch("danxi_daily.pipeline.fetch_hole_floors", side_effect=_slow_fetch):
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                config = PipelineConfig(
                    base_urls=["https://forum.fduhole.com/api"],
                    output_markdown=root / "daily.md",
                    output_holes=root / "holes.json",
                    output_ranked=root / "ranked.json",
                    floor_cache_file=root / "floor_cache.json",
                    floor_fetch_workers=4,
                    floor_fetch_timeout=4,
                    prompt_path=root / "prompt.md",
                    llm_provider="none",
                    post=False,
                )
                run_pipeline(config)

        self.assertGreaterEqual(active["max"], 2)

    @patch("danxi_daily.pipeline.fetch_hole_floors", return_value=[])
    @patch("danxi_daily.pipeline.fetch_holes_with_fallback")
    def test_pipeline_archives_markdown_with_unique_datetime_path(
        self,
        mock_fetch_holes,
        _mock_fetch_floors,
    ) -> None:
        mock_fetch_holes.return_value = ([_fake_hole(7)], "https://forum.fduhole.com/api")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = PipelineConfig(
                base_urls=["https://forum.fduhole.com/api"],
                output_markdown=root / "daily.md",
                output_holes=root / "holes.json",
                output_ranked=root / "ranked.json",
                archive_outputs=True,
                archive_dir=root / "history",
                prompt_path=root / "prompt.md",
                llm_provider="none",
                post=False,
            )

            first = run_pipeline(config)
            second = run_pipeline(config)

            self.assertNotEqual(first["archived_markdown"], second["archived_markdown"])
            self.assertTrue(Path(first["archived_markdown"]).exists())
            self.assertTrue(Path(second["archived_markdown"]).exists())
            self.assertTrue((root / "daily.md").exists())

    @patch("danxi_daily.pipeline.fetch_hole_floors", return_value=[])
    @patch("danxi_daily.pipeline.fetch_holes_with_fallback")
    def test_pipeline_fetches_all_today_pages(
        self,
        mock_fetch_holes,
        _mock_fetch_floors,
    ) -> None:
        page1 = [_fake_hole(1000 + idx) for idx in range(10)]
        page2 = [_fake_hole(2000 + idx) for idx in range(10)]
        page3 = [_fake_hole(3000 + idx) for idx in range(3)]
        call_offsets: list[int | None] = []
        call_limits: list[int] = []

        def _side_effect(*_args, **kwargs):
            offset = kwargs.get("offset")
            limit = kwargs.get("limit")
            call_offsets.append(offset)
            call_limits.append(limit)
            if offset == 0:
                return page1, "https://forum.fduhole.com/api"
            if offset == 10:
                return page2, "https://forum.fduhole.com/api"
            if offset == 20:
                return page3, "https://forum.fduhole.com/api"
            return [], "https://forum.fduhole.com/api"

        mock_fetch_holes.side_effect = _side_effect

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = PipelineConfig(
                base_urls=["https://forum.fduhole.com/api"],
                fetch_limit=10,
                output_markdown=root / "daily.md",
                output_holes=root / "holes.json",
                output_ranked=root / "ranked.json",
                prompt_path=root / "prompt.md",
                llm_provider="none",
                post=False,
            )
            result = run_pipeline(config)

        self.assertIn(0, call_offsets)
        self.assertIn(10, call_offsets)
        self.assertIn(20, call_offsets)
        self.assertTrue(all(limit <= 10 for limit in call_limits))
        self.assertGreaterEqual(result["fetched"], 23)

    @patch("danxi_daily.pipeline.fetch_hole_floors", return_value=[])
    @patch("danxi_daily.pipeline.fetch_holes_with_fallback")
    def test_pipeline_does_not_expand_length_when_offset_is_ignored(
        self,
        mock_fetch_holes,
        _mock_fetch_floors,
    ) -> None:
        page = [_fake_hole(5000 + idx) for idx in range(10)]
        call_limits: list[int] = []
        call_offsets: list[int | None] = []

        def _side_effect(*_args, **kwargs):
            call_limits.append(kwargs.get("limit"))
            call_offsets.append(kwargs.get("offset"))
            return page, "https://forum.fduhole.com/api"

        mock_fetch_holes.side_effect = _side_effect

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = PipelineConfig(
                base_urls=["https://forum.fduhole.com/api"],
                fetch_limit=10,
                output_markdown=root / "daily.md",
                output_holes=root / "holes.json",
                output_ranked=root / "ranked.json",
                prompt_path=root / "prompt.md",
                llm_provider="none",
                post=False,
            )
            result = run_pipeline(config)

        self.assertEqual(result["fetched"], 10)
        self.assertTrue(all(limit <= 10 for limit in call_limits))
        self.assertEqual(call_offsets[:2], [0, 10])

    @patch("danxi_daily.pipeline.fetch_hole_floors", return_value=[])
    @patch("danxi_daily.pipeline.fetch_holes_with_fallback", side_effect=RuntimeError("network down"))
    def test_pipeline_limits_retries_per_page_on_failure(
        self,
        mock_fetch_holes,
        _mock_fetch_floors,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = PipelineConfig(
                base_urls=["https://forum.fduhole.com/api"],
                output_markdown=root / "daily.md",
                output_holes=root / "holes.json",
                output_ranked=root / "ranked.json",
                prompt_path=root / "prompt.md",
                llm_provider="none",
                post=False,
            )
            with self.assertRaises(RuntimeError):
                run_pipeline(config)

        self.assertEqual(mock_fetch_holes.call_count, config.fetch_retry_per_page)

    @patch("danxi_daily.pipeline.fetch_hole_floors", return_value=[])
    @patch("danxi_daily.pipeline.fetch_holes_with_fallback")
    def test_pipeline_force_webvpn_uses_time_cursor_offset(
        self,
        mock_fetch_holes,
        _mock_fetch_floors,
    ) -> None:
        page1 = [_fake_hole(7000 + idx) for idx in range(10)]
        page2 = [_fake_hole(8000 + idx) for idx in range(3)]
        for idx, hole in enumerate(page1):
            hole["time_updated"] = f"2026-01-01T01:{idx:02d}:00Z"
        for idx, hole in enumerate(page2):
            hole["time_updated"] = f"2026-01-01T00:{idx:02d}:00Z"

        observed_offsets: list[int | str | None] = []

        def _side_effect(*_args, **kwargs):
            offset = kwargs.get("offset")
            observed_offsets.append(offset)
            if len(observed_offsets) == 1:
                return page1, "https://forum.fduhole.com/api"
            return page2, "https://forum.fduhole.com/api"

        mock_fetch_holes.side_effect = _side_effect

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = PipelineConfig(
                base_urls=["https://forum.fduhole.com/api"],
                force_webvpn=True,
                fetch_limit=10,
                output_markdown=root / "daily.md",
                output_holes=root / "holes.json",
                output_ranked=root / "ranked.json",
                prompt_path=root / "prompt.md",
                llm_provider="none",
                post=False,
            )
            run_pipeline(config)

        self.assertGreaterEqual(len(observed_offsets), 2)
        self.assertIsInstance(observed_offsets[0], str)
        self.assertIsInstance(observed_offsets[1], str)

    @patch("danxi_daily.pipeline.fetch_hole_floors", return_value=[])
    @patch("danxi_daily.pipeline.fetch_holes_with_fallback")
    def test_pipeline_start_time_not_before_local_today_start(
        self,
        mock_fetch_holes,
        _mock_fetch_floors,
    ) -> None:
        mock_fetch_holes.return_value = ([_fake_hole(9)], "https://forum.fduhole.com/api")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = PipelineConfig(
                base_urls=["https://forum.fduhole.com/api"],
                hours=72,
                output_markdown=root / "daily.md",
                output_holes=root / "holes.json",
                output_ranked=root / "ranked.json",
                prompt_path=root / "prompt.md",
                llm_provider="none",
                post=False,
            )
            result = run_pipeline(config)

        start_dt = parse_iso8601(result["start_time"])
        self.assertIsNotNone(start_dt)
        assert start_dt is not None
        # With hours=72, start_time should be about 72h ago, NOT today's midnight.
        now_utc = datetime.now(timezone.utc)
        from datetime import timedelta
        expected_approx = now_utc - timedelta(hours=72)
        # Allow 5 minute tolerance for test execution time.
        self.assertLess(abs((start_dt - expected_approx).total_seconds()), 300)

    @patch("danxi_daily.pipeline.fetch_hole_floors", return_value=[])
    @patch("danxi_daily.pipeline.fetch_holes_with_fallback")
    def test_pipeline_start_time_is_today_start_even_for_small_hours(
        self,
        mock_fetch_holes,
        _mock_fetch_floors,
    ) -> None:
        mock_fetch_holes.return_value = ([_fake_hole(11)], "https://forum.fduhole.com/api")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = PipelineConfig(
                base_urls=["https://forum.fduhole.com/api"],
                hours=2,
                output_markdown=root / "daily.md",
                output_holes=root / "holes.json",
                output_ranked=root / "ranked.json",
                prompt_path=root / "prompt.md",
                llm_provider="none",
                post=False,
            )
            result = run_pipeline(config)

        start_dt = parse_iso8601(result["start_time"])
        self.assertIsNotNone(start_dt)
        assert start_dt is not None
        # With hours=2, start_time should be about 2 hours ago.
        now_utc = datetime.now(timezone.utc)
        from datetime import timedelta
        expected_approx = now_utc - timedelta(hours=2)
        self.assertLess(abs((start_dt - expected_approx).total_seconds()), 300)

    @patch("danxi_daily.pipeline.fetch_hole_floors", return_value=[])
    @patch("danxi_daily.pipeline.fetch_holes_with_fallback")
    def test_pipeline_filters_out_non_today_posts(
        self,
        mock_fetch_holes,
        _mock_fetch_floors,
    ) -> None:
        old_hole = _fake_hole(9001)
        old_hole["time_created"] = "2020-01-01T08:00:00Z"
        old_hole["time_updated"] = "2020-01-01T09:00:00Z"

        now_local = datetime.now().astimezone()
        today_local = now_local.replace(hour=12, minute=0, second=0, microsecond=0)
        today_utc = today_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        today_hole = _fake_hole(9002)
        today_hole["time_created"] = today_utc
        today_hole["time_updated"] = today_utc

        call_count = {"value": 0}

        def _side_effect(*_args, **_kwargs):
            call_count["value"] += 1
            if call_count["value"] == 1:
                return [old_hole, today_hole], "https://forum.fduhole.com/api"
            return [], "https://forum.fduhole.com/api"

        mock_fetch_holes.side_effect = _side_effect

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = PipelineConfig(
                base_urls=["https://forum.fduhole.com/api"],
                fetch_limit=10,
                output_markdown=root / "daily.md",
                output_holes=root / "holes.json",
                output_ranked=root / "ranked.json",
                prompt_path=root / "prompt.md",
                llm_provider="none",
                post=False,
            )
            result = run_pipeline(config)

            self.assertEqual(result["fetched"], 1)
            ranked_text = (root / "ranked.json").read_text(encoding="utf-8")
            self.assertIn("9002", ranked_text)
            self.assertNotIn("9001", ranked_text)


if __name__ == "__main__":
    unittest.main()
