from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from danxi_daily.pipeline import PipelineConfig, run_pipeline
from danxi_daily.poster import PostError
from danxi_daily.webvpn import WebVPNAuthError, WebVPNCredentials


class PostRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.client = Mock()
        self.client.credentials = WebVPNCredentials("test-user", "test-password")
        self.client.obtain_forum_api_token.return_value = "fresh-token"
        self.config = PipelineConfig(
            base_urls=["https://forum.fduhole.com/api"],
            output_markdown=self.root / "daily.md",
            output_holes=self.root / "holes.json",
            output_ranked=self.root / "ranked.json",
            post_dedupe_file=self.root / "last.sha256",
            post_schedule_state_file=self.root / "slot.txt",
            floor_enrich_size=0,
            archive_outputs=False,
            post=True,
            post_endpoint="https://forum.fduhole.com/api/holes",
            post_token="expired-token",
            api_token="expired-token",
            post_once_per_day=True,
            webvpn_client=self.client,
            force_webvpn=True,
        )
        self.config.post_dedupe_file.write_text("previous-hash", encoding="utf-8")
        self.config.post_schedule_state_file.write_text("20000101", encoding="utf-8")
        fetch = patch("danxi_daily.pipeline._fetch_hot_candidates", return_value=([], "https://forum.fduhole.com/api"))
        self.fetch = fetch.start()
        self.addCleanup(fetch.stop)

    def assert_not_posted(self) -> None:
        self.assertEqual(self.config.post_dedupe_file.read_text(), "previous-hash")
        self.assertEqual(self.config.post_schedule_state_file.read_text(), "20000101")
        self.assertTrue(self.config.output_markdown.exists())
        self.assertFalse((self.root / "last.sha256.lock").exists())

    @patch("danxi_daily.pipeline.post_markdown", side_effect=[(401, "token expired"), (201, '{"hole_id":123}')])
    def test_expired_forum_token_refreshes_once_and_reuses_report(self, post) -> None:
        result = run_pipeline(self.config)
        self.assertEqual(result["post_result"]["status"], 201)
        self.assertEqual(post.call_count, 2)
        self.client.obtain_forum_api_token.assert_called_once()
        self.fetch.assert_called_once()
        first, second = (call.kwargs for call in post.call_args_list)
        self.assertEqual(first["content"], second["content"])
        self.assertEqual(first["token"], "expired-token")
        self.assertEqual(second["token"], "fresh-token")
        self.assertNotEqual(self.config.post_dedupe_file.read_text(), "previous-hash")
        self.assertNotEqual(self.config.post_schedule_state_file.read_text(), "20000101")

    @patch("danxi_daily.pipeline.post_markdown", return_value=(401, "still expired"))
    def test_second_401_fails_without_changing_dedupe(self, post) -> None:
        with self.assertRaisesRegex(PostError, "HTTP 401"):
            run_pipeline(self.config)
        self.assertEqual(post.call_count, 2)
        self.client.obtain_forum_api_token.assert_called_once()
        self.assert_not_posted()

    @patch("danxi_daily.pipeline.post_markdown", side_effect=WebVPNAuthError("CAS session not established"))
    def test_webvpn_auth_failure_does_not_attempt_forum_login(self, post) -> None:
        with self.assertRaisesRegex(PostError, "CAS session not established"):
            run_pipeline(self.config)
        post.assert_called_once()
        self.client.obtain_forum_api_token.assert_not_called()
        self.assert_not_posted()

    @patch("danxi_daily.pipeline.post_markdown", side_effect=TimeoutError("connection timed out"))
    def test_ambiguous_network_failure_is_not_replayed(self, post) -> None:
        with self.assertRaisesRegex(PostError, "connection timed out"):
            run_pipeline(self.config)
        post.assert_called_once()
        self.client.obtain_forum_api_token.assert_not_called()
        self.assert_not_posted()

    @patch("danxi_daily.pipeline.post_markdown", return_value=(503, "upstream unavailable"))
    def test_server_error_does_not_replay_post(self, post) -> None:
        with self.assertRaisesRegex(PostError, "HTTP 503"):
            run_pipeline(self.config)
        post.assert_called_once()
        self.assert_not_posted()

    @patch("danxi_daily.pipeline.post_markdown", return_value=(401, "token expired"))
    def test_refresh_error_keeps_stage_and_redacts_credentials(self, post) -> None:
        self.client.obtain_forum_api_token.side_effect = WebVPNAuthError("CAS rejected test-user test-password")
        with self.assertRaises(PostError) as caught:
            run_pipeline(self.config)
        message = str(caught.exception)
        self.assertIn("refreshing forum token", message)
        self.assertIn("CAS rejected", message)
        self.assertNotIn("test-user", message)
        self.assertNotIn("test-password", message)
        post.assert_called_once()
        self.assert_not_posted()

    @patch("danxi_daily.pipeline.post_markdown", return_value=(401, "token expired"))
    def test_refresh_cannot_bypass_post_window(self, post) -> None:
        # Early generation and initial post are in the window; refresh ends late.
        with patch("danxi_daily.pipeline._should_skip_post_for_schedule", side_effect=[
            (False, None, "20260910"), (False, None, "20260910"),
            (True, "outside_post_window", "20260910"),
        ]):
            with self.assertRaisesRegex(PostError, "outside_post_window"):
                run_pipeline(self.config)
        post.assert_called_once()
        self.assert_not_posted()
