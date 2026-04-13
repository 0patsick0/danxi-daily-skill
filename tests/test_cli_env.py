from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from danxi_daily import cli


class CliEnvTests(unittest.TestCase):
    @patch("danxi_daily.cli.run_pipeline", return_value={"ok": True})
    def test_dotenv_is_loaded_for_token(self, mock_run_pipeline) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".env").write_text(
                "DANXI_API_TOKEN=dotenv-token\n",
                encoding="utf-8",
            )

            old_cwd = os.getcwd()
            os.chdir(root)
            try:
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("DANXI_API_TOKEN", None)
                    argv = [
                        "prog",
                        "--base-urls",
                        "https://forum.fduhole.com/api",
                    ]
                    with patch("sys.argv", argv):
                        code = cli.main()
                self.assertEqual(code, 0)
            finally:
                os.chdir(old_cwd)

        called_config = mock_run_pipeline.call_args[0][0]
        self.assertEqual(called_config.api_token, "dotenv-token")


if __name__ == "__main__":
    unittest.main()
