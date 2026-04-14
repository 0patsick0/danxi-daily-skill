from __future__ import annotations

import unittest

from danxi_daily.ranking import rank_holes


class RankingStrategyTests(unittest.TestCase):
    def test_filters_invalid_trade_discussions(self) -> None:
        holes = [
            {
                "hole_id": 1,
                "time_updated": "2026-04-14T10:00:00+08:00",
                "reply": 20,
                "view": 500,
                "floors": {
                    "first_floor": {
                        "content": "收资料，出资料，代课请私聊",
                    }
                },
            },
            {
                "hole_id": 2,
                "time_updated": "2026-04-14T10:00:00+08:00",
                "reply": 20,
                "view": 500,
                "floors": {
                    "first_floor": {
                        "content": "今天这门课讨论真激烈",
                    }
                },
            },
        ]

        ranked = rank_holes(holes, source_endpoint="https://forum.fduhole.com/api")
        self.assertEqual([x.hole_id for x in ranked], [2])

    def test_filters_outsourcing_discussions(self) -> None:
        holes = [
            {
                "hole_id": 3,
                "time_updated": "2026-04-14T10:00:00+08:00",
                "reply": 15,
                "view": 800,
                "floors": {
                    "first_floor": {
                        "content": "接代刷锻，晚锻可代跑",
                    }
                },
            },
            {
                "hole_id": 4,
                "time_updated": "2026-04-14T10:00:00+08:00",
                "reply": 15,
                "view": 800,
                "floors": {
                    "first_floor": {
                        "content": "今天课程讨论非常激烈",
                    }
                },
            },
        ]

        ranked = rank_holes(holes, source_endpoint="https://forum.fduhole.com/api")
        self.assertEqual([x.hole_id for x in ranked], [4])

    def test_prefers_high_view_and_reply(self) -> None:
        holes = [
            {
                "hole_id": 10,
                "time_updated": "2026-04-14T10:00:00+08:00",
                "reply": 45,
                "view": 1200,
                "floors": {"first_floor": {"content": "热点讨论A"}},
            },
            {
                "hole_id": 11,
                "time_updated": "2026-04-14T10:00:00+08:00",
                "reply": 9,
                "view": 130,
                "floors": {"first_floor": {"content": "普通讨论B"}},
            },
        ]

        ranked = rank_holes(holes, source_endpoint="https://forum.fduhole.com/api")
        self.assertGreaterEqual(len(ranked), 2)
        self.assertEqual(ranked[0].hole_id, 10)

    def test_filters_low_signal_posts(self) -> None:
        holes = [
            {
                "hole_id": 20,
                "time_updated": "2026-04-14T10:00:00+08:00",
                "reply": 1,
                "view": 30,
                "floors": {"first_floor": {"content": "低信号内容"}},
            },
            {
                "hole_id": 21,
                "time_updated": "2026-04-14T10:00:00+08:00",
                "reply": 10,
                "view": 140,
                "floors": {"first_floor": {"content": "高信号内容"}},
            },
        ]

        ranked = rank_holes(holes, source_endpoint="https://forum.fduhole.com/api")
        self.assertEqual([x.hole_id for x in ranked], [21])


if __name__ == "__main__":
    unittest.main()
