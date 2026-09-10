from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from danxi_daily import cli
from danxi_daily.poster import PostError
from danxi_daily.security import safe_error_message
from danxi_daily.webvpn import WebVPNAuthError


class CliEnvTests(unittest.TestCase):
    @contextmanager
    def _isolated_cli(self, env=None, *, prompt=False):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".env").write_text("", encoding="utf-8")
            previous_cwd = os.getcwd()
            os.chdir(root)
            stdout, stderr = io.StringIO(), io.StringIO()
            argv = ["prog", "--base-urls", "https://forum.fduhole.com/api"]
            if not prompt:
                argv.append("--webvpn-no-prompt")
            try:
                with patch.dict(os.environ, env or {}, clear=True), patch("sys.argv", argv), \
                        redirect_stdout(stdout), redirect_stderr(stderr):
                    yield root, stdout, stderr
            finally:
                os.chdir(previous_cwd)

    def test_post_failure_exits_nonzero_without_regenerating_or_refreshing(self) -> None:
        with self._isolated_cli() as (_, stdout, stderr), patch(
            "danxi_daily.cli.run_pipeline", side_effect=PostError("Publishing failed: HTTP 401")
        ) as run, patch("danxi_daily.cli._refresh_api_token") as refresh:
            self.assertEqual(cli.main(), 1)
        run.assert_called_once()
        refresh.assert_not_called()
        self.assertIn("HTTP 401", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")

    def test_numeric_failed_post_results_exit_nonzero_without_refreshing(self) -> None:
        for status in (0, 199, 301, 401, 403, 500):
            with self.subTest(status=status), self._isolated_cli(), patch(
                "danxi_daily.cli.run_pipeline", return_value={"post_result": {"status": status}}
            ) as run, patch("danxi_daily.cli._refresh_api_token") as refresh:
                self.assertEqual(cli.main(), 1)
                run.assert_called_once()
                refresh.assert_not_called()

    def test_success_skipped_and_dry_run_results_exit_zero(self) -> None:
        for result in (
            {"post_result": {"status": 200}},
            {"post_result": {"status": 201}},
            {"post_result": {"status": 204}},
            {"post_result": {"status": "skipped", "reason": "already posted"}},
            {"post_result": None},
        ):
            with self.subTest(result=result), self._isolated_cli(), patch(
                "danxi_daily.cli.run_pipeline", return_value=result
            ), patch("danxi_daily.cli._refresh_api_token") as refresh:
                self.assertEqual(cli.main(), 0)
                refresh.assert_not_called()

    def test_failed_token_refresh_preserves_safe_reason(self) -> None:
        env = {
            "DANXI_API_TOKEN": "old-token-secret",
            "DANXI_WEBVPN_USERNAME": "student-secret",
            "DANXI_WEBVPN_PASSWORD": "password-secret",
        }
        error = WebVPNAuthError(
            "CAS requires enhanced authentication (2FA): student-secret password-secret "
            "https://student-secret:password-secret@id.fudan.edu.cn/login?ticket=private-ticket#private-fragment "
            "Authorization: Bearer old-token-secret"
        )
        with self._isolated_cli(env) as (_, _, stderr), patch(
            "danxi_daily.cli.run_pipeline", side_effect=RuntimeError("HTTP 401 token expired")
        ) as run, patch("danxi_daily.cli.WebVPNClient.reset_session") as reset, patch(
            "danxi_daily.cli.WebVPNClient.obtain_forum_api_token", side_effect=error
        ) as obtain:
            self.assertEqual(cli.main(), 1)
        run.assert_called_once()
        reset.assert_called_once()
        obtain.assert_called_once()
        self.assertIn("HTTP 401 token expired", stderr.getvalue())
        self.assertIn("forum token refresh failed", stderr.getvalue())
        self.assertIn("CAS requires enhanced authentication (2FA)", stderr.getvalue())
        for secret in (*env.values(), "private-ticket", "private-fragment"):
            self.assertNotIn(secret, stderr.getvalue())

    def test_failure_after_token_refresh_exits_nonzero_without_further_retry(self) -> None:
        for retry_result in (
            PostError("Publishing failed: HTTP 401"),
            RuntimeError("webvpn response is not valid JSON"),
            {"post_result": {"status": 503}},
        ):
            with self.subTest(retry_result=retry_result), self._isolated_cli({
                "DANXI_API_TOKEN": "old-token",
                "DANXI_WEBVPN_USERNAME": "student",
                "DANXI_WEBVPN_PASSWORD": "secret",
            }) as (_, stdout, stderr), patch(
                "danxi_daily.cli.run_pipeline", side_effect=[RuntimeError("token expired"), retry_result]
            ) as run, patch("danxi_daily.cli.WebVPNClient.reset_session") as reset, patch(
                "danxi_daily.cli.WebVPNClient.obtain_forum_api_token", return_value="fresh-token"
            ) as obtain:
                self.assertEqual(cli.main(), 1)
                self.assertEqual(run.call_count, 2)
                reset.assert_called_once()
                obtain.assert_called_once()
                self.assertIn("[error]", stderr.getvalue())
                self.assertEqual(stdout.getvalue(), "")

    def test_token_refresh_retries_once_and_honors_no_save_credentials(self) -> None:
        env = {
            "DANXI_API_TOKEN": "old-token",
            "DANXI_WEBVPN_USERNAME": "student",
            "DANXI_WEBVPN_PASSWORD": "secret",
            "DANXI_WEBVPN_SAVE_CREDENTIALS": "false",
        }
        with self._isolated_cli(env) as (root, _, _), patch(
            "danxi_daily.cli.run_pipeline", side_effect=[RuntimeError("token expired"), {"ok": True}]
        ) as run, patch("danxi_daily.cli.WebVPNClient.reset_session") as reset, patch(
            "danxi_daily.cli.WebVPNClient.obtain_forum_api_token", return_value="fresh-token"
        ):
            self.assertEqual(cli.main(), 0)
            self.assertEqual((root / ".env").read_text(encoding="utf-8"), "")
            self.assertEqual(os.environ["DANXI_API_TOKEN"], "old-token")
        reset.assert_called_once()
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args.args[0].api_token, "fresh-token")
        self.assertEqual(run.call_args.args[0].post_token, "fresh-token")

    def test_prompt_retry_cannot_hide_post_failure(self) -> None:
        for retry_result in (
            PostError("Publishing failed: HTTP 401"),
            {"post_result": {"status": 401}},
            RuntimeError("HTTP 401 token expired"),
        ):
            with self.subTest(retry_result=retry_result), self._isolated_cli(prompt=True) as (_, _, stderr), patch(
                "danxi_daily.cli.run_pipeline", side_effect=[RuntimeError("network down"), retry_result]
            ) as run, patch("sys.stdin.isatty", return_value=True), patch(
                "builtins.input", return_value="student"
            ), patch("getpass.getpass", return_value="secret"), patch(
                "danxi_daily.cli.WebVPNClient.obtain_forum_api_token", return_value="fresh-token"
            ) as obtain:
                self.assertEqual(cli.main(), 1)
                self.assertEqual(run.call_count, 2)
                obtain.assert_called_once()
                self.assertIn("HTTP 401", stderr.getvalue())

    def test_safe_error_message_redacts_credentials_and_preserves_reason(self) -> None:
        message = safe_error_message(
            'HTTP 401 token expired; password="private password"; access_token=private-token; '
            'Authorization: Bearer opaque-secret; loginToken=login-secret; '
            'https://user:pass@example.com/auth?code=private-code#fragment; '
            'encoded=p%40ss+word; bare=eyJabc.payload.signature',
            secrets=("p@ss word",),
        )
        self.assertIn("HTTP 401 token expired", message)
        self.assertIn("https://example.com/auth", message)
        for secret in (
            "private password", "private-token", "opaque-secret", "login-secret", "private-code",
            "fragment", "user:pass", "p%40ss+word", "eyJabc.payload.signature",
        ):
            self.assertNotIn(secret, message)

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
                        "--post-window-minutes",
                        "60",
                        "--webvpn-no-prompt",
                    ]
                    with patch("sys.argv", argv):
                        code = cli.main()
                self.assertEqual(code, 0)
            finally:
                os.chdir(old_cwd)

        called_config = mock_run_pipeline.call_args[0][0]
        self.assertEqual(called_config.post_schedule_hhmm, "08:30")
        self.assertEqual(called_config.post_window_minutes, 60)


if __name__ == "__main__":
    unittest.main()
