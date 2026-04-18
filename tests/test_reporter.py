from __future__ import annotations

import unittest

from danxi_daily.models import RankedPost
from danxi_daily.reporter import build_daily_markdown


class ReporterFormatTests(unittest.TestCase):
    def _make_post(self, hole_id: int = 123456, excerpt: str = "节选内容") -> RankedPost:
        return RankedPost(
            hole_id=hole_id,
            division_id=1,
            time_created="2026-04-14T08:00:00+08:00",
            time_updated="2026-04-14T10:00:00+08:00",
            reply=21,
            view=860,
            like_sum=14,
            hot_score=98.1234,
            excerpt=excerpt,
        )

    def test_build_daily_markdown_basic_structure(self) -> None:
        text = build_daily_markdown([self._make_post()])

        self.assertIn("今日热门话题", text)
        self.assertIn("#123456", text)
        self.assertIn("热度", text)
        self.assertIn("👀", text)
        self.assertIn("💬", text)
        self.assertIn("👍", text)
        # No excerpt / summary sections
        self.assertNotIn("摘要", text)
        self.assertNotIn("话题解读", text)
        # No English headers
        self.assertNotIn("Generated at", text)
        self.assertNotIn("Hot Posts", text)

    def test_build_daily_markdown_no_excerpt_in_output(self) -> None:
        """Excerpt field should never appear in output regardless of content."""
        text = build_daily_markdown([self._make_post(excerpt="这段话不应该出现")])

        self.assertNotIn("这段话不应该出现", text)
        self.assertNotIn("摘要", text)

    def test_build_daily_markdown_numbered_list(self) -> None:
        posts = [self._make_post(hole_id=100 + i) for i in range(3)]
        text = build_daily_markdown(posts)

        self.assertIn("1. #100", text)
        self.assertIn("2. #101", text)
        self.assertIn("3. #102", text)

    def test_build_daily_markdown_empty_case(self) -> None:
        text = build_daily_markdown([])

        self.assertIn("暂未抓取到符合条件", text)


if __name__ == "__main__":
    unittest.main()
