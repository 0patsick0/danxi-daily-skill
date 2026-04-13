from __future__ import annotations

import unittest

from danxi_daily.pipeline import PipelineConfig, run_pipeline


class PipelineSecurityTests(unittest.TestCase):
    def test_pipeline_rejects_non_https_endpoint(self) -> None:
        config = PipelineConfig(base_urls=["http://forum.fduhole.com/api"])
        with self.assertRaises(ValueError):
            run_pipeline(config)


if __name__ == "__main__":
    unittest.main()
