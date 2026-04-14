from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from danxi_daily.models import RankedPost
from danxi_daily.summarizer import summarize_post


class SummarizerTests(unittest.TestCase):
    def test_extractive_summary_when_provider_none(self) -> None:
        post = RankedPost(
            hole_id=1,
            division_id=1,
            time_created=None,
            time_updated=None,
            reply=12,
            view=300,
            like_sum=5,
            hot_score=0.0,
            excerpt="长得丑怎么才能谈恋爱![](dx_guilty)",
            raw={
                "floors": {
                    "prefetch": [
                        {"content": "我觉得先把心态放稳，再多认识人"},
                        {"content": "提升表达和社交频率会有帮助"},
                    ]
                }
            },
        )
        with tempfile.TemporaryDirectory() as td:
            prompt = Path(td) / "missing_prompt.md"
            result = summarize_post(post, prompt_path=prompt, provider="none")
        self.assertIn("该帖主要围绕", result)
        self.assertNotIn("当前互动为", result)
        self.assertNotIn("[fallback]", result)
        self.assertNotIn("dx_guilty", result)

    @patch("danxi_daily.summarizer._anthropic_summary", side_effect=ValueError("bad payload"))
    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "x"}, clear=False)
    def test_fallback_summary_when_anthropic_fails(self, _mock_anthropic) -> None:
        post = RankedPost(
            hole_id=2,
            division_id=1,
            time_created=None,
            time_updated=None,
            reply=1,
            view=3,
            like_sum=0,
            hot_score=1.0,
            excerpt="another excerpt",
        )
        with tempfile.TemporaryDirectory() as td:
            prompt = Path(td) / "prompt.md"
            prompt.write_text("test", encoding="utf-8")
            result = summarize_post(post, prompt_path=prompt, provider="anthropic")
        self.assertIn("该帖主要围绕", result)
        self.assertNotIn("[fallback]", result)
        self.assertNotIn("当前互动为", result)


if __name__ == "__main__":
    unittest.main()
