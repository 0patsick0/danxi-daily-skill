from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from danxi_daily.pipeline import PipelineConfig, run_pipeline


def _fake_hole(hole_id: int) -> dict:
    return {
        "hole_id": hole_id,
        "division_id": 1,
        "view": 120,
        "reply": 12,
        "time_created": "2026-01-01T00:00:00Z",
        "time_updated": "2026-01-01T01:00:00Z",
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


if __name__ == "__main__":
    unittest.main()
