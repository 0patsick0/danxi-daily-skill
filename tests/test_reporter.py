from __future__ import annotations

import unittest

from danxi_daily.models import RankedPost
from danxi_daily.reporter import build_daily_markdown


class ReporterFormatTests(unittest.TestCase):
    def test_build_daily_markdown_uses_publishable_chinese_style(self) -> None:
        posts = [
            RankedPost(
                hole_id=123456,
                division_id=1,
                time_created="2026-04-14T08:00:00+08:00",
                time_updated="2026-04-14T10:00:00+08:00",
                reply=21,
                view=860,
                like_sum=14,
                hot_score=98.1234,
                excerpt="这是原文节选![](dx_guilty)",
                summary="这是话题解读![](dx_call)",
            )
        ]

        text = build_daily_markdown(posts)

        self.assertIn("🌟", text)
        self.assertIn("今日热门话题", text)
        self.assertIn("开源仓库", text)
        self.assertIn("No.1 #123456", text)
        self.assertNotIn("Generated at", text)
        self.assertNotIn("Hot Posts", text)
        self.assertNotIn("GitHub 仓库", text)
        self.assertNotIn("热门洞", text)
        self.assertNotIn("话题解读", text)
        self.assertNotIn("原文节选", text)
        self.assertNotIn("本文为自动整理的旦夕 24 小时热点话题精选", text)
        self.assertNotIn("dx_guilty", text)
        self.assertNotIn("dx_call", text)

    def test_build_daily_markdown_empty_case_still_has_chinese_footer(self) -> None:
        text = build_daily_markdown([])

        self.assertIn("暂未抓取到符合条件", text)
        self.assertIn("开源仓库", text)


if __name__ == "__main__":
    unittest.main()
