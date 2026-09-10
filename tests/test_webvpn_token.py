from __future__ import annotations

import io
import json
import unittest
import urllib.error
import urllib.request
from http.cookiejar import Cookie
from unittest.mock import MagicMock, patch

from danxi_daily.webvpn import WebVPNClient, WebVPNCredentials, WebVPNAuthError, WebVPNError, _PreserveMethodRedirectHandler, is_webvpn_login_response, is_webvpn_api_bounce


# Structure observed in the authenticated gateway landing page: no forms or
# password inputs, but shared scripts still contain login URLs/password markup.
_AUTHENTICATED_PORTAL_HTML = """<!doctype html>
<html><head><title>资源访问控制系统 - 资源站点</title></head>
<body><input type="text" name="search"><div>资源站点</div>
<script>
const casLogin = "/login?cas_login=true";
const loginTemplate = '<form action="/do-login"><input type="password"></form>';
</script></body></html>"""


def _session_cookie(value: str) -> Cookie:
    return Cookie(
        version=0, name="wengine_vpn_ticket", value=value,
        port=None, port_specified=False,
        domain="webvpn.fudan.edu.cn", domain_specified=False, domain_initial_dot=False,
        path="/", path_specified=True, secure=True, expires=None, discard=True,
        comment=None, comment_url=None, rest={}, rfc2109=False,
    )


def _http_error(code: int, body: dict[str, str]) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://webvpn.fudan.edu.cn/mock",
        code=code,
        msg="error",
        hdrs=None,
        fp=io.BytesIO(json.dumps(body).encode("utf-8")),
    )


class WebvpnTokenTests(unittest.TestCase):
    def test_invalid_retry_env_values_fall_back_to_defaults(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "DANXI_WEBVPN_RETRIES": "bad",
                "DANXI_WEBVPN_BACKOFF_BASE": "oops",
                "DANXI_WEBVPN_TIMEOUT_SCALE": "nah",
            },
            clear=False,
        ):
            client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"), allowed_hosts={"forum.fduhole.com"})

        self.assertEqual(client.max_retries, 5)
        self.assertAlmostEqual(client.backoff_base, 0.8)
        self.assertAlmostEqual(client.timeout_scale, 1.35)

    def test_preserve_redirect_blocks_untrusted_host(self) -> None:
        handler = _PreserveMethodRedirectHandler()
        req = urllib.request.Request(
            "https://webvpn.fudan.edu.cn/mock",
            data=b"email=a&password=b",
            method="POST",
        )

        with self.assertRaises(WebVPNAuthError):
            handler.redirect_request(req, fp=None, code=307, msg="", headers={}, newurl="https://evil.example/steal")

    def test_get_redirect_blocks_untrusted_host(self) -> None:
        handler = _PreserveMethodRedirectHandler()
        req = urllib.request.Request("https://webvpn.fudan.edu.cn/resource", method="GET")

        with self.assertRaises(WebVPNAuthError):
            handler.redirect_request(req, fp=None, code=302, msg="", headers={}, newurl="https://evil.example/path")

    def test_get_redirect_blocks_https_to_http_downgrade(self) -> None:
        handler = _PreserveMethodRedirectHandler()
        req = urllib.request.Request("https://webvpn.fudan.edu.cn/resource", method="GET")

        with self.assertRaises(WebVPNAuthError):
            handler.redirect_request(req, fp=None, code=302, msg="", headers={}, newurl="http://webvpn.fudan.edu.cn/resource")

    def test_preserve_redirect_allows_trusted_host(self) -> None:
        handler = _PreserveMethodRedirectHandler()
        req = urllib.request.Request(
            "https://webvpn.fudan.edu.cn/mock",
            data=b"email=a&password=b",
            method="POST",
        )

        redirected = handler.redirect_request(
            req,
            fp=None,
            code=307,
            msg="",
            headers={},
            newurl="https://webvpn.fudan.edu.cn/next",
        )

        self.assertIsNotNone(redirected)
        assert redirected is not None
        self.assertEqual(redirected.get_full_url(), "https://webvpn.fudan.edu.cn/next")

    def test_cross_host_redirect_strips_authorization(self) -> None:
        handler = _PreserveMethodRedirectHandler()
        req = urllib.request.Request(
            "https://webvpn.fudan.edu.cn/protected",
            headers={"Authorization": "Bearer top-secret"},
            method="GET",
        )

        redirected = handler.redirect_request(
            req,
            fp=None,
            code=302,
            msg="",
            headers={"Location": "https://id.fudan.edu.cn/landing"},
            newurl="https://id.fudan.edu.cn/landing",
        )

        self.assertIsNotNone(redirected)
        assert redirected is not None
        self.assertFalse(any(key.lower() == "authorization" for key, _ in redirected.header_items()))

    def test_preserved_redirect_does_not_copy_stale_cookies(self) -> None:
        handler = _PreserveMethodRedirectHandler()
        for code in (307, 308):
            for target in ("https://webvpn.fudan.edu.cn/next", "https://id.fudan.edu.cn/landing"):
                with self.subTest(code=code, target=target):
                    request = urllib.request.Request("https://webvpn.fudan.edu.cn/protected", data=b"{}", method="POST")
                    request.add_unredirected_header("Cookie", "old-session=value")
                    request.add_header("Cookie2", "$Version=1")
                    redirected = handler.redirect_request(request, None, code, "", {}, target)
                    self.assertIsNotNone(redirected)
                    assert redirected is not None
                    self.assertFalse(any(key.lower() in {"cookie", "cookie2"} for key, _ in redirected.header_items()))
                    self.assertEqual(redirected.data, b"{}")

    def test_reused_request_gets_new_cookie_after_session_reset(self) -> None:
        for method in ("GET", "POST"):
            with self.subTest(method=method):
                client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"))
                client._cookie_jar.set_cookie(_session_cookie("old-value"))
                request = urllib.request.Request(
                    "https://webvpn.fudan.edu.cn/api/holes",
                    data=b"{}" if method == "POST" else None,
                    method=method,
                )
                request.add_header("Cookie2", "$Version=1")
                observed: list[str | None] = []
                opener = MagicMock()

                def open_with_real_cookie_jar(req, timeout):
                    client._cookie_jar.add_cookie_header(req)
                    observed.append(req.get_header("Cookie"))
                    self.assertIsNone(req.get_header("Cookie2"))
                    response = MagicMock()
                    response.__enter__.return_value = response
                    response.read.return_value = b'{"ok": true}'
                    response.geturl.return_value = req.full_url
                    return response

                opener.open.side_effect = open_with_real_cookie_jar
                client._attempt_open_with_retries(opener, request, 10)
                client.reset_session()
                client._cookie_jar.set_cookie(_session_cookie("fresh-value"))
                # Posting, token recovery and GET recovery reuse this Request.
                client._attempt_open_with_retries(opener, request, 10)

                self.assertEqual(observed, ["wengine_vpn_ticket=old-value", "wengine_vpn_ticket=fresh-value"])

    def test_get_retry_uses_cookie_updated_by_previous_attempt(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"))
        client._cookie_jar.set_cookie(_session_cookie("old-value"))
        request = urllib.request.Request("https://webvpn.fudan.edu.cn/api/holes")
        observed: list[str | None] = []
        opener = MagicMock()

        def open_with_real_cookie_jar(req, timeout):
            client._cookie_jar.add_cookie_header(req)
            observed.append(req.get_header("Cookie"))
            if len(observed) == 1:
                client._cookie_jar.set_cookie(_session_cookie("fresh-value"))
                raise TimeoutError("read timeout after session cookie changed")
            response = MagicMock()
            response.__enter__.return_value = response
            response.read.return_value = b'{"ok": true}'
            response.geturl.return_value = req.full_url
            return response

        opener.open.side_effect = open_with_real_cookie_jar
        with patch("danxi_daily.webvpn.time.sleep"):
            client._attempt_open_with_retries(opener, request, 10)

        self.assertEqual(observed, ["wengine_vpn_ticket=old-value", "wengine_vpn_ticket=fresh-value"])

    def test_candidate_email_variants(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="24307100036", password="x"), allowed_hosts={"forum.fduhole.com"})
        self.assertEqual(
            client._candidate_forum_emails(),
            ["24307100036@m.fudan.edu.cn", "24307100036@fudan.edu.cn"],
        )

    def test_obtain_forum_api_token_success(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"), allowed_hosts={"forum.fduhole.com"})
        client._ensure_authenticated = lambda: None  # type: ignore[method-assign]

        calls: list[str] = []

        def fake_open(req, timeout=None):
            calls.append(req.full_url)
            return json.dumps({"access": "token-123"}), req.full_url

        client._open_following_post_redirects = fake_open  # type: ignore[method-assign]

        from unittest.mock import patch

        with patch("danxi_daily.webvpn.translate_to_webvpn", return_value="https://webvpn.fudan.edu.cn/mock"):
            token = client.obtain_forum_api_token()

        self.assertEqual(token, "token-123")
        self.assertEqual(len(calls), 1)

    def test_obtain_forum_api_token_retries_next_email(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="24307100036", password="pwd"), allowed_hosts={"forum.fduhole.com"})
        client._ensure_authenticated = lambda: None  # type: ignore[method-assign]

        first = _http_error(403, {"message": "account not registered"})
        second = (json.dumps({"access": "token-ok"}), "https://webvpn.fudan.edu.cn/mock")
        responses = [first, second]

        def fake_open(req, timeout=None):
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        client._open_following_post_redirects = fake_open  # type: ignore[method-assign]

        from unittest.mock import patch

        with patch("danxi_daily.webvpn.translate_to_webvpn", return_value="https://webvpn.fudan.edu.cn/mock"):
            token = client.obtain_forum_api_token()

        self.assertEqual(token, "token-ok")

    def test_obtain_forum_api_token_raises_when_all_fail(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"), allowed_hosts={"forum.fduhole.com"})
        client._ensure_authenticated = lambda: None  # type: ignore[method-assign]

        def fake_open(req, timeout=None):
            raise _http_error(403, {"message": "no such account"})

        client._open_following_post_redirects = fake_open  # type: ignore[method-assign]

        from unittest.mock import patch

        with patch("danxi_daily.webvpn.translate_to_webvpn", return_value="https://webvpn.fudan.edu.cn/mock"):
            with self.assertRaises(WebVPNAuthError):
                client.obtain_forum_api_token()

    def test_obtain_forum_api_token_wraps_oserror(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"), allowed_hosts={"forum.fduhole.com"})

        def fail_auth():
            raise OSError("socket fail")

        client._ensure_authenticated = fail_auth  # type: ignore[method-assign]
        with self.assertRaises(WebVPNAuthError):
            client.obtain_forum_api_token()

    def test_request_json_wraps_oserror_from_open(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"), allowed_hosts={"forum.fduhole.com"})
        client._ensure_authenticated = lambda: None  # type: ignore[method-assign]

        def fail_open(req, timeout=None):
            raise OSError("socket fail")

        client._open = fail_open  # type: ignore[method-assign]

        with self.assertRaises(WebVPNError) as ctx:
            client.request_json(
                "https://forum.fduhole.com/api/holes",
                params={"length": 1},
                token=None,
                timeout=10,
            )

        self.assertIn("webvpn request failed", str(ctx.exception))

    def test_cas_failure_does_not_fall_back_to_local_login(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"), allowed_hosts={"forum.fduhole.com"})
        local_calls = {"count": 0}

        def fail_cas() -> None:
            raise WebVPNAuthError("cas rejected")

        def mark_local() -> None:
            local_calls["count"] += 1

        client._ensure_authenticated_via_cas = fail_cas  # type: ignore[method-assign]
        client._ensure_authenticated_via_local = mark_local  # type: ignore[method-assign]

        with self.assertRaises(WebVPNAuthError) as ctx:
            client._ensure_authenticated()

        self.assertIn("cas rejected", str(ctx.exception))
        self.assertEqual(local_calls["count"], 0)

    def test_local_auth_mode_uses_local_login(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"), allowed_hosts={"forum.fduhole.com"})
        local_calls = {"count": 0}

        def mark_local() -> None:
            local_calls["count"] += 1
            client._authenticated = True

        def fail_cas() -> None:
            raise AssertionError("CAS should not run in local auth mode")

        client._ensure_authenticated_via_cas = fail_cas  # type: ignore[method-assign]
        client._ensure_authenticated_via_local = mark_local  # type: ignore[method-assign]

        with patch.dict("os.environ", {"DANXI_WEBVPN_AUTH": "local"}, clear=False):
            client._ensure_authenticated()

        self.assertEqual(local_calls["count"], 1)
        self.assertTrue(client._authenticated)

    def test_reset_session_clears_auth_flag(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"), allowed_hosts={"forum.fduhole.com"})
        client._authenticated = True
        old_jar = client._cookie_jar

        client.reset_session()

        self.assertFalse(client._authenticated)
        self.assertIsNot(client._cookie_jar, old_jar)

    def test_post_response_timeout_is_not_replayed(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"))
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        # The server may have created the post before the response times out.
        response.read.side_effect = TimeoutError("response timed out")
        request = urllib.request.Request("https://webvpn.fudan.edu.cn/api/holes", data=b"{}", method="POST")

        with patch("danxi_daily.webvpn.time.sleep") as sleep:
            with self.assertRaises(TimeoutError):
                client._attempt_open_with_retries(opener, request, 10)

        self.assertEqual(opener.open.call_count, 1)
        sleep.assert_not_called()

    def test_get_response_timeout_can_be_retried(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"))
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        response.read.side_effect = [TimeoutError("response timed out"), b'{"ok": true}']
        response.geturl.return_value = "https://webvpn.fudan.edu.cn/api/holes"

        with patch("danxi_daily.webvpn.time.sleep"):
            body, _ = client._attempt_open_with_retries(opener, response.geturl.return_value, 10)

        self.assertEqual(json.loads(body), {"ok": True})
        self.assertEqual(opener.open.call_count, 2)

    def test_http_auth_failure_is_not_retried_by_transport(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"))
        opener = MagicMock()
        opener.open.side_effect = _http_error(401, {"exp": "token expired"})

        with patch("danxi_daily.webvpn.time.sleep") as sleep:
            with self.assertRaises(urllib.error.HTTPError):
                client._attempt_open_with_retries(opener, "https://webvpn.fudan.edu.cn/api/holes", 10)

        opener.open.assert_called_once()
        sleep.assert_not_called()

    def test_cas_ticket_returning_login_page_does_not_mark_authenticated(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"))
        responses = [
            ("", "https://id.fudan.edu.cn/login#/auth?lck=secret&entityId=webvpn"),
            ("ticket page", "https://id.fudan.edu.cn/idp/authCenter/authnEngine"),
            ("<html>login</html>", "https://webvpn.fudan.edu.cn/login"),
        ]
        with (
            patch.object(client, "_open", side_effect=responses),
            patch.object(client, "_load_auth_chain_code", return_value="chain"),
            patch.object(client, "_load_public_key", return_value=object()),
            patch.object(client, "_encrypt_password", return_value="encrypted"),
            patch.object(client, "_execute_cas_auth", return_value="login-token"),
            patch.object(client, "_extract_target_url_with_ticket", return_value="https://webvpn.fudan.edu.cn/login?ticket=secret"),
        ):
            with self.assertRaisesRegex(WebVPNAuthError, "did not establish a session") as ctx:
                client._ensure_authenticated_via_cas()

        self.assertFalse(client._authenticated)
        self.assertNotIn("secret", str(ctx.exception))

    def test_cas_accepts_authenticated_portal_with_generic_title(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"))
        with patch.object(client, "_open", return_value=(_AUTHENTICATED_PORTAL_HTML, "https://webvpn.fudan.edu.cn/")) as opened:
            client._ensure_authenticated_via_cas()

        self.assertTrue(client._authenticated)
        opened.assert_called_once()

    def test_cas_ticket_returning_observed_portal_establishes_session(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"))
        responses = [
            ("", "https://id.fudan.edu.cn/login#/auth?lck=secret&entityId=webvpn"),
            ("ticket page", "https://id.fudan.edu.cn/idp/authCenter/authnEngine"),
            (_AUTHENTICATED_PORTAL_HTML, "https://webvpn.fudan.edu.cn/"),
        ]
        with (
            patch.object(client, "_open", side_effect=responses),
            patch.object(client, "_load_auth_chain_code", return_value="chain"),
            patch.object(client, "_load_public_key", return_value=object()),
            patch.object(client, "_encrypt_password", return_value="encrypted"),
            patch.object(client, "_execute_cas_auth", return_value="login-token"),
            patch.object(client, "_extract_target_url_with_ticket", return_value="https://webvpn.fudan.edu.cn/login?cas_login=true&ticket=secret"),
        ):
            client._ensure_authenticated_via_cas()

        self.assertTrue(client._authenticated)

    def test_portal_is_successful_login_but_not_an_api_response(self) -> None:
        self.assertFalse(is_webvpn_login_response(_AUTHENTICATED_PORTAL_HTML, "https://webvpn.fudan.edu.cn/"))
        self.assertTrue(is_webvpn_api_bounce(_AUTHENTICATED_PORTAL_HTML, "https://webvpn.fudan.edu.cn/"))
        self.assertFalse(is_webvpn_api_bounce('{"id": 123}', "https://webvpn.fudan.edu.cn/"))

    def test_actual_password_input_and_meta_login_redirect_are_detected(self) -> None:
        for body in (
            '<html><input type="password" name="secret"></html>',
            '<html><meta http-equiv="refresh" content="0; url=/login?cas_login=true"></html>',
        ):
            with self.subTest(body=body):
                self.assertTrue(is_webvpn_login_response(body, "https://webvpn.fudan.edu.cn/"))

    def test_json_containing_login_html_is_not_a_gateway_login_response(self) -> None:
        body = json.dumps({"id": 123, "content": '<html><form action="/do-login">password</form></html>'})
        self.assertFalse(is_webvpn_login_response(body, "https://webvpn.fudan.edu.cn/api/holes"))

    def test_login_html_at_original_api_url_is_detected(self) -> None:
        body = '\n<html><title>资源访问控制系统</title><input name="password"></html>'
        self.assertTrue(is_webvpn_login_response(body, "https://webvpn.fudan.edu.cn/api/holes"))

    def test_request_json_recovers_login_page_once_with_same_token(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"), allowed_hosts={"forum.fduhole.com"})
        responses = [
            ("<html>CAS</html>", "https://id.fudan.edu.cn/login#/auth?lck=hidden"),
            ('{"items": []}', "https://webvpn.fudan.edu.cn/mock"),
        ]
        with (
            patch.object(client, "_ensure_authenticated") as authenticated,
            patch.object(client, "reset_session", wraps=client.reset_session) as reset,
            patch.object(client, "_open", side_effect=responses) as opened,
        ):
            result = client.request_json("https://forum.fduhole.com/api/holes", params={}, token="read-token", timeout=10)

        self.assertEqual(result, {"items": []})
        self.assertEqual(authenticated.call_count, 2)
        reset.assert_called_once()
        self.assertEqual(opened.call_count, 2)
        for call in opened.call_args_list:
            self.assertEqual(call.args[0].get_header("Authorization"), "Bearer read-token")

    def test_request_json_stops_after_second_login_page(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"), allowed_hosts={"forum.fduhole.com"})
        with (
            patch.object(client, "_ensure_authenticated"),
            patch.object(client, "_open", return_value=("<html>login</html>", "https://webvpn.fudan.edu.cn/login")) as opened,
        ):
            with self.assertRaisesRegex(WebVPNAuthError, "still expired after re-authentication"):
                client.request_json("https://forum.fduhole.com/api/holes", params={}, token="read-token", timeout=10)

        self.assertEqual(opened.call_count, 2)
        self.assertFalse(client._authenticated)

    def test_request_json_retries_malformed_response_without_password_attempt(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"), allowed_hosts={"forum.fduhole.com"})
        client._authenticated = True
        with (
            patch.object(client, "_ensure_authenticated_via_cas") as authenticate,
            patch.object(client, "reset_session") as reset,
            patch.object(client, "_open", side_effect=[("<html>Bad gateway</html>", "https://webvpn.fudan.edu.cn/mock"), ('{"items": []}', "https://webvpn.fudan.edu.cn/mock")]) as opened,
        ):
            result = client.request_json("https://forum.fduhole.com/api/holes", params={}, token="read-token", timeout=10)

        self.assertEqual(result, {"items": []})
        self.assertEqual(opened.call_count, 2)
        authenticate.assert_not_called()
        reset.assert_not_called()

    def test_request_json_preserves_expired_token_reason_without_gateway_relogin(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="uid", password="pwd"), allowed_hosts={"forum.fduhole.com"})
        with (
            patch.object(client, "_ensure_authenticated"),
            patch.object(client, "reset_session") as reset,
            patch.object(client, "_open", side_effect=_http_error(401, {"exp": "token expired"})) as opened,
        ):
            with self.assertRaisesRegex(WebVPNError, "HTTP 401: token expired"):
                client.request_json("https://forum.fduhole.com/api/holes", params={}, token="read-token", timeout=10)

        opened.assert_called_once()
        reset.assert_not_called()

    def test_token_request_recovers_gateway_session_before_changing_email(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="student", password="password"))
        responses = [
            ("<html>login</html>", "https://webvpn.fudan.edu.cn/login"),
            ('{"access": "new-token"}', "https://webvpn.fudan.edu.cn/mock"),
        ]
        with (
            patch.object(client, "_ensure_authenticated") as authenticated,
            patch.object(client, "reset_session", wraps=client.reset_session) as reset,
            patch.object(client, "_open_following_post_redirects", side_effect=responses) as opened,
        ):
            token = client.obtain_forum_api_token()

        self.assertEqual(token, "new-token")
        self.assertEqual(authenticated.call_count, 2)
        reset.assert_called_once()
        emails = [json.loads(call.args[0].data)["email"] for call in opened.call_args_list]
        self.assertEqual(emails, ["student@m.fudan.edu.cn", "student@m.fudan.edu.cn"])

    def test_token_request_recovers_when_gateway_bounces_to_portal(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="student", password="password"))
        with (
            patch.object(client, "_ensure_authenticated"),
            patch.object(client, "reset_session", wraps=client.reset_session) as reset,
            patch.object(client, "_open_following_post_redirects", side_effect=[
                (_AUTHENTICATED_PORTAL_HTML, "https://webvpn.fudan.edu.cn/"),
                ('{"access": "new-token"}', "https://webvpn.fudan.edu.cn/mock"),
            ]) as opened,
        ):
            token = client.obtain_forum_api_token()

        self.assertEqual(token, "new-token")
        self.assertEqual(opened.call_count, 2)
        reset.assert_called_once()

    def test_token_request_repeated_login_page_stops_after_one_recovery(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="student", password="password"))
        with (
            patch.object(client, "_ensure_authenticated"),
            patch.object(client, "_open_following_post_redirects", return_value=("<html>login</html>", "https://webvpn.fudan.edu.cn/login")) as opened,
        ):
            with self.assertRaisesRegex(WebVPNAuthError, "still returned a login page after WebVPN re-authentication"):
                client.obtain_forum_api_token()

        self.assertEqual(opened.call_count, 2)
        self.assertFalse(client._authenticated)

    def test_token_request_network_failure_does_not_try_another_email(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="student", password="password"))
        with (
            patch.object(client, "_ensure_authenticated"),
            patch.object(client, "_open_following_post_redirects", side_effect=TimeoutError("read timed out")) as opened,
        ):
            with self.assertRaisesRegex(WebVPNAuthError, "forum login network error: read timed out"):
                client.obtain_forum_api_token()

        opened.assert_called_once()

    def test_token_request_malformed_response_does_not_try_another_password(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="student", password="password"))
        with (
            patch.object(client, "_ensure_authenticated"),
            patch.object(client, "reset_session") as reset,
            patch.object(client, "_open_following_post_redirects", return_value=("<html>Bad gateway</html>", "https://webvpn.fudan.edu.cn/mock")) as opened,
        ):
            with self.assertRaisesRegex(WebVPNAuthError, "forum login returned a non-JSON response"):
                client.obtain_forum_api_token()

        opened.assert_called_once()
        reset.assert_not_called()

    def test_authentication_error_redacts_credentials_tokens_and_ticket_urls(self) -> None:
        client = WebVPNClient(WebVPNCredentials(username="student123", password="private-password"))
        message = "denied for student123; password=private-password token=opaque-secret https://id.fudan.edu.cn/login?ticket=cas-secret"
        with patch.object(client, "_post_json", return_value={"message": message}):
            with self.assertRaises(WebVPNAuthError) as ctx:
                client._execute_cas_auth("lck", "entity", "chain", "encrypted")

        detail = str(ctx.exception)
        self.assertIn("denied", detail)
        for secret in ("student123", "private-password", "opaque-secret", "cas-secret"):
            self.assertNotIn(secret, detail)


if __name__ == "__main__":
    unittest.main()
