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
        "view": 20,
        "reply": 2,
        "time_created": "2026-01-01T00:00:00Z",
        "time_updated": "2026-01-01T01:00:00Z",
        "floors": {"prefetch": [{"like": 1, "content": "post body"}]},
    }


class PostDedupeTests(unittest.TestCase):
    @patch("danxi_daily.pipeline.fetch_hole_floors", return_value=[])
    @patch("danxi_daily.pipeline.fetch_holes_with_fallback")
    @patch("danxi_daily.pipeline.post_markdown", return_value=(200, "ok"))
    def test_second_post_is_skipped_as_duplicate(
        self,
        mock_post,
        mock_fetch_holes,
        _mock_fetch_floors,
    ) -> None:
        mock_fetch_holes.return_value = ([_fake_hole(88)], "https://forum.fduhole.com/api")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = PipelineConfig(
                base_urls=["https://forum.fduhole.com/api"],
                output_markdown=root / "daily.md",
                output_holes=root / "holes.json",
                output_ranked=root / "ranked.json",
                post_dedupe_file=root / "last.sha256",
                prompt_path=root / "prompt.md",
                llm_provider="none",
                post=True,
                post_endpoint="https://forum.fduhole.com/api/post",
                post_token="x",
            )

            first = run_pipeline(config)
            second = run_pipeline(config)

            self.assertEqual(first["post_result"]["status"], 200)
            self.assertEqual(second["post_result"]["status"], "skipped")
            self.assertEqual(mock_post.call_count, 1)


if __name__ == "__main__":
    unittest.main()
