from __future__ import annotations

import tempfile
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


if __name__ == "__main__":
    unittest.main()
