from __future__ import annotations

import unittest

from danxi_daily.ranking import rank_holes


class RankingTests(unittest.TestCase):
    def test_ranking_is_deterministic(self) -> None:
        holes = [
            {
                "hole_id": 101,
                "division_id": 1,
                "view": 10,
                "reply": 2,
                "time_updated": None,
                "floors": {"prefetch": [{"like": 1, "content": "a"}]},
            },
            {
                "hole_id": 102,
                "division_id": 1,
                "view": 10,
                "reply": 2,
                "time_updated": None,
                "floors": {"prefetch": [{"like": 1, "content": "b"}]},
            },
        ]

        run1 = rank_holes(holes, source_endpoint="https://x")
        run2 = rank_holes(holes, source_endpoint="https://x")

        self.assertEqual([x.hole_id for x in run1], [x.hole_id for x in run2])

    def test_tie_breaker_prefers_higher_hole_id(self) -> None:
        holes = [
            {
                "hole_id": 201,
                "division_id": 1,
                "view": 0,
                "reply": 0,
                "time_updated": None,
                "floors": {"prefetch": []},
            },
            {
                "hole_id": 202,
                "division_id": 1,
                "view": 0,
                "reply": 0,
                "time_updated": None,
                "floors": {"prefetch": []},
            },
        ]

        ranked = rank_holes(holes, source_endpoint="https://x")
        self.assertEqual(ranked[0].hole_id, 202)


if __name__ == "__main__":
    unittest.main()
