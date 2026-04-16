from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from danxi_daily import cli


class CliEnvTests(unittest.TestCase):
    @patch("danxi_daily.cli.run_pipeline", return_value={"ok": True})
    def test_default_top_is_10(self, mock_run_pipeline) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".env").write_text("", encoding="utf-8")

            old_cwd = os.getcwd()
            os.chdir(root)
            try:
                with patch.dict(os.environ, {}, clear=True):
                    argv = [
                        "prog",
                        "--base-urls",
                        "https://forum.fduhole.com/api",
                        "--webvpn-no-prompt",
                    ]
                    with patch("sys.argv", argv):
                        code = cli.main()
                self.assertEqual(code, 0)
            finally:
                os.chdir(old_cwd)

        called_config = mock_run_pipeline.call_args[0][0]
        self.assertEqual(called_config.top_n, 10)

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
                with patch.dict(os.environ, {}, clear=True):
                    os.environ.pop("DANXI_API_TOKEN", None)
                    argv = [
                        "prog",
                        "--base-urls",
                        "https://forum.fduhole.com/api",
                        "--webvpn-no-prompt",
                    ]
                    with patch("sys.argv", argv):
                        code = cli.main()
                self.assertEqual(code, 0)
            finally:
                os.chdir(old_cwd)

        called_config = mock_run_pipeline.call_args[0][0]
        self.assertEqual(called_config.api_token, "dotenv-token")

    @patch("danxi_daily.cli.run_pipeline", return_value={"ok": True})
    def test_first_run_prompts_and_persists_webvpn_credentials(self, mock_run_pipeline) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".env").write_text("", encoding="utf-8")

            old_cwd = os.getcwd()
            os.chdir(root)
            try:
                with patch.dict(os.environ, {}, clear=True):
                    argv = [
                        "prog",
                        "--base-urls",
                        "https://forum.fduhole.com/api",
                        "--webvpn-mode",
                        "force",
                    ]
                    with patch("sys.argv", argv), patch("sys.stdin.isatty", return_value=True), patch(
                        "builtins.input", return_value="stu-id"
                    ), patch("getpass.getpass", return_value="stu-pass"), patch(
                        "danxi_daily.cli.WebVPNClient.obtain_forum_api_token", return_value=None
                    ):
                        code = cli.main()
                self.assertEqual(code, 0)
            finally:
                os.chdir(old_cwd)

            env_text = (root / ".env").read_text(encoding="utf-8")
            self.assertIn("DANXI_WEBVPN_USERNAME=stu-id", env_text)
            self.assertIn("DANXI_WEBVPN_PASSWORD=stu-pass", env_text)

        called_config = mock_run_pipeline.call_args[0][0]
        self.assertIsNotNone(called_config.webvpn_client)
        self.assertTrue(called_config.force_webvpn)

    def test_non_interactive_missing_webvpn_credentials_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".env").write_text("", encoding="utf-8")

            old_cwd = os.getcwd()
            os.chdir(root)
            try:
                with patch.dict(os.environ, {}, clear=True):
                    argv = [
                        "prog",
                        "--base-urls",
                        "https://forum.fduhole.com/api",
                        "--webvpn-mode",
                        "force",
                        "--webvpn-no-prompt",
                    ]
                    with patch("sys.argv", argv), patch("sys.stdin.isatty", return_value=False):
                        with self.assertRaises(SystemExit):
                            cli.main()
            finally:
                os.chdir(old_cwd)

    def test_invalid_webvpn_mode_from_env_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".env").write_text("", encoding="utf-8")

            old_cwd = os.getcwd()
            os.chdir(root)
            try:
                with patch.dict(os.environ, {"DANXI_WEBVPN_MODE": "bad"}, clear=True):
                    argv = [
                        "prog",
                        "--base-urls",
                        "https://forum.fduhole.com/api",
                        "--webvpn-no-prompt",
                    ]
                    with patch("sys.argv", argv):
                        with self.assertRaises(SystemExit):
                            cli.main()
            finally:
                os.chdir(old_cwd)

    def test_invalid_post_at_format_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".env").write_text("", encoding="utf-8")

            old_cwd = os.getcwd()
            os.chdir(root)
            try:
                with patch.dict(os.environ, {}, clear=True):
                    argv = [
                        "prog",
                        "--base-urls",
                        "https://forum.fduhole.com/api",
                        "--post-at",
                        "8:00",
                        "--webvpn-no-prompt",
                    ]
                    with patch("sys.argv", argv):
                        with self.assertRaises(SystemExit):
                            cli.main()
            finally:
                os.chdir(old_cwd)

    def test_invalid_post_at_from_env_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".env").write_text("", encoding="utf-8")

            old_cwd = os.getcwd()
            os.chdir(root)
            try:
                with patch.dict(os.environ, {"DANXI_POST_AT": "8:00"}, clear=True):
                    argv = [
                        "prog",
                        "--base-urls",
                        "https://forum.fduhole.com/api",
                        "--webvpn-no-prompt",
                    ]
                    with patch("sys.argv", argv):
                        with self.assertRaises(SystemExit):
                            cli.main()
            finally:
                os.chdir(old_cwd)

    @patch("danxi_daily.cli.run_pipeline", return_value={"ok": True})
    def test_existing_webvpn_credentials_are_loaded_without_prompt(self, mock_run_pipeline) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".env").write_text(
                "DANXI_WEBVPN_USERNAME=already\nDANXI_WEBVPN_PASSWORD=exists\n",
                encoding="utf-8",
            )

            old_cwd = os.getcwd()
            os.chdir(root)
            try:
                with patch.dict(os.environ, {}, clear=True):
                    argv = [
                        "prog",
                        "--base-urls",
                        "https://forum.fduhole.com/api",
                        "--webvpn-mode",
                        "force",
                    ]
                    with patch("sys.argv", argv), patch("builtins.input") as mock_input, patch(
                        "getpass.getpass"
                    ) as mock_getpass, patch(
                        "danxi_daily.cli.WebVPNClient.obtain_forum_api_token", return_value=None
                    ):
                        code = cli.main()
                self.assertEqual(code, 0)
                mock_input.assert_not_called()
                mock_getpass.assert_not_called()
            finally:
                os.chdir(old_cwd)

        called_config = mock_run_pipeline.call_args[0][0]
        self.assertIsNotNone(called_config.webvpn_client)

    @patch("danxi_daily.cli.run_pipeline")
    def test_auto_mode_prompts_after_first_failure_and_retries(self, mock_run_pipeline) -> None:
        mock_run_pipeline.side_effect = [RuntimeError("network down"), {"ok": True}]

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".env").write_text("", encoding="utf-8")

            old_cwd = os.getcwd()
            os.chdir(root)
            try:
                with patch.dict(os.environ, {}, clear=True):
                    argv = [
                        "prog",
                        "--base-urls",
                        "https://forum.fduhole.com/api",
                        "--webvpn-mode",
                        "auto",
                    ]
                    with patch("sys.argv", argv), patch("sys.stdin.isatty", return_value=True), patch(
                        "builtins.input", return_value="retry-user"
                    ), patch("getpass.getpass", return_value="retry-pass"), patch(
                        "danxi_daily.cli.WebVPNClient.obtain_forum_api_token", return_value="fresh-token"
                    ):
                        code = cli.main()
                self.assertEqual(code, 0)
            finally:
                os.chdir(old_cwd)

            env_text = (root / ".env").read_text(encoding="utf-8")
            self.assertIn("DANXI_WEBVPN_USERNAME=retry-user", env_text)
            self.assertIn("DANXI_WEBVPN_PASSWORD=retry-pass", env_text)
            self.assertIn("DANXI_API_TOKEN=fresh-token", env_text)

        self.assertEqual(mock_run_pipeline.call_count, 2)
        second_config = mock_run_pipeline.call_args_list[1][0][0]
        self.assertTrue(second_config.force_webvpn)
        self.assertEqual(second_config.api_token, "fresh-token")

    @patch("danxi_daily.cli.run_pipeline", return_value={"ok": True})
    def test_auto_obtained_api_token_is_persisted(self, mock_run_pipeline) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".env").write_text(
                "DANXI_WEBVPN_USERNAME=uid\nDANXI_WEBVPN_PASSWORD=pwd\n",
                encoding="utf-8",
            )

            old_cwd = os.getcwd()
            os.chdir(root)
            try:
                with patch.dict(os.environ, {}, clear=True):
                    argv = [
                        "prog",
                        "--base-urls",
                        "https://forum.fduhole.com/api",
                        "--webvpn-mode",
                        "force",
                    ]
                    with patch("sys.argv", argv), patch(
                        "danxi_daily.cli.WebVPNClient.obtain_forum_api_token", return_value="auto-token"
                    ):
                        code = cli.main()
                self.assertEqual(code, 0)
            finally:
                os.chdir(old_cwd)

            env_text = (root / ".env").read_text(encoding="utf-8")
            self.assertIn("DANXI_API_TOKEN=auto-token", env_text)

        called_config = mock_run_pipeline.call_args[0][0]
        self.assertEqual(called_config.api_token, "auto-token")

    @patch("danxi_daily.cli.run_pipeline", return_value={"ok": True})
    def test_cli_passes_schedule_config_to_pipeline(self, mock_run_pipeline) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".env").write_text("", encoding="utf-8")

            old_cwd = os.getcwd()
            os.chdir(root)
            try:
                with patch.dict(os.environ, {}, clear=True):
                    argv = [
                        "prog",
                        "--base-urls",
                        "https://forum.fduhole.com/api",
                        "--post-at",
                        "08:30",
                        "--webvpn-no-prompt",
                    ]
                    with patch("sys.argv", argv):
                        code = cli.main()
                self.assertEqual(code, 0)
            finally:
                os.chdir(old_cwd)

        called_config = mock_run_pipeline.call_args[0][0]
        self.assertEqual(called_config.post_schedule_hhmm, "08:30")


if __name__ == "__main__":
    unittest.main()
