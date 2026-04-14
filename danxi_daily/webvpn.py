from __future__ import annotations

import json
import base64
import html as html_lib
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.cookiejar import CookieJar
from typing import Any

try:
    from Crypto.Cipher import AES
    from Crypto.Cipher import PKCS1_v1_5
    from Crypto.PublicKey import RSA
except ImportError:  # pragma: no cover
    AES = None  # type: ignore[assignment]
    PKCS1_v1_5 = None  # type: ignore[assignment]
    RSA = None  # type: ignore[assignment]


WEBVPN_HOST = "webvpn.fudan.edu.cn"
WEBVPN_LOGIN_URL = f"https://{WEBVPN_HOST}/login?cas_login=true"
WEBVPN_DO_LOGIN_URL = f"https://{WEBVPN_HOST}/do-login"
_WEBVPN_KEY = "wrdvpnisthebest!"
_ID_HOST = "id.fudan.edu.cn"
_AUTH_HOST = "auth.fduhole.com"
_SAFE_REDIRECT_HOSTS = {WEBVPN_HOST, _ID_HOST, _AUTH_HOST}


class WebVPNError(RuntimeError):
    pass


class WebVPNAuthError(WebVPNError):
    pass


class _PreserveMethodRedirectHandler(urllib.request.HTTPRedirectHandler):
    def _origin(self, url: str) -> tuple[str, str, int | None]:
        parsed = urllib.parse.urlparse(url)
        return parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port

    def _validated_hosts(self, old_url: str, new_url: str) -> tuple[tuple[str, str, int | None], tuple[str, str, int | None]]:
        old_origin = self._origin(old_url)
        new_origin = self._origin(new_url)
        old_scheme, old_host, _ = old_origin
        new_scheme, new_host, _ = new_origin

        if new_scheme != "https":
            raise WebVPNAuthError("unsafe redirect target scheme for authenticated request")
        if (not new_host) or (new_host not in _SAFE_REDIRECT_HOSTS) or (old_host and old_host not in _SAFE_REDIRECT_HOSTS):
            raise WebVPNAuthError("unsafe redirect target for authenticated request")
        if old_scheme not in {"http", "https"}:
            raise WebVPNAuthError("unsafe source scheme for authenticated request")
        return old_origin, new_origin

    def _sanitize_headers_on_origin_change(
        self,
        headers: dict[str, str],
        old_origin: tuple[str, str, int | None],
        new_origin: tuple[str, str, int | None],
    ) -> dict[str, str]:
        if old_origin == new_origin:
            return headers
        sanitized = dict(headers)
        for key in list(sanitized.keys()):
            if key.lower() == "authorization":
                sanitized.pop(key, None)
        return sanitized

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        old_origin, new_origin = self._validated_hosts(req.full_url, newurl)
        if code in {307, 308}:
            safe_headers = self._sanitize_headers_on_origin_change(dict(req.header_items()), old_origin, new_origin)
            return urllib.request.Request(
                newurl,
                data=req.data,
                headers=safe_headers,
                method=req.get_method(),
            )

        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        safe_headers = self._sanitize_headers_on_origin_change(dict(redirected.header_items()), old_origin, new_origin)
        redirected.headers.clear()
        for key, value in safe_headers.items():
            redirected.headers[key] = value
        return redirected


@dataclass
class WebVPNCredentials:
    username: str
    password: str


def _right_pad_with_zeroes(text: str, block_size: int = 16) -> str:
    remainder = len(text) % block_size
    if remainder == 0:
        return text
    return text + ("0" * (block_size - remainder))


def _encrypt_host(host: str) -> str:
    if AES is None:
        raise WebVPNError("webvpn support requires pycryptodome")

    source = host if ":" not in host else f"[{host}]"
    original_len = len(source)
    padded = _right_pad_with_zeroes(source, block_size=16)

    key_bytes = _WEBVPN_KEY.encode("utf-8")
    iv_bytes = _WEBVPN_KEY.encode("utf-8")
    cipher = AES.new(key_bytes, AES.MODE_CFB, iv=iv_bytes, segment_size=128)
    encrypted = cipher.encrypt(padded.encode("utf-8"))

    return iv_bytes.hex() + encrypted.hex()[: original_len * 2]


def translate_to_webvpn(url: str, allowed_hosts: set[str] | None = None) -> str | None:
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        return None

    host = (parsed.hostname or "").lower()
    if not host:
        return None
    if allowed_hosts is not None and host not in allowed_hosts:
        return None

    segment = scheme if parsed.port is None else f"{scheme}-{parsed.port}"
    encoded_host = _encrypt_host(host)
    path = parsed.path or "/"
    components = path
    if parsed.query:
        components = f"{components}?{parsed.query}"
    if parsed.fragment:
        components = f"{components}#{parsed.fragment}"

    return f"https://{WEBVPN_HOST}/{segment}/{encoded_host}{components}"


def _json_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "danxi-daily-skill/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


class WebVPNClient:
    def __init__(
        self,
        credentials: WebVPNCredentials,
        *,
        timeout: int = 15,
        allowed_hosts: set[str] | None = None,
    ) -> None:
        self.credentials = credentials
        self.timeout = timeout
        self.allowed_hosts = {x.lower() for x in allowed_hosts} if allowed_hosts else None
        self._cookie_jar = CookieJar()
        self._opener = urllib.request.build_opener(
            _PreserveMethodRedirectHandler(),
            urllib.request.HTTPCookieProcessor(self._cookie_jar),
        )
        self._authenticated = False

    def _open(self, request: str | urllib.request.Request, timeout: int | None = None) -> tuple[str, str]:
        final_timeout = timeout if timeout is not None else self.timeout
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with self._opener.open(request, timeout=final_timeout) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    final_url = resp.geturl()
                return body, final_url
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
                if attempt == 2:
                    break
                time.sleep(0.8 * (attempt + 1))

        assert last_error is not None
        raise last_error

    def _open_following_post_redirects(
        self,
        request: str | urllib.request.Request,
        timeout: int | None = None,
    ) -> tuple[str, str]:
        final_timeout = timeout if timeout is not None else self.timeout
        opener = urllib.request.build_opener(
            _PreserveMethodRedirectHandler(),
            urllib.request.HTTPCookieProcessor(self._cookie_jar),
        )

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with opener.open(request, timeout=final_timeout) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    final_url = resp.geturl()
                return body, final_url
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
                if attempt == 2:
                    break
                time.sleep(0.8 * (attempt + 1))

        assert last_error is not None
        raise last_error

    def _post_json(self, url: str, payload: dict[str, Any], timeout: int | None = None) -> dict[str, Any]:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "danxi-daily-skill/1.0",
            },
        )
        body, _ = self._open(req, timeout=timeout)
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise WebVPNAuthError("id service returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise WebVPNAuthError("id service returned invalid payload")
        return data

    def _get_auth_params_from_redirect(self, redirected_url: str) -> tuple[str, str]:
        parsed = urllib.parse.urlparse(redirected_url)
        fragment = parsed.fragment or ""
        if "?" not in fragment:
            raise WebVPNAuthError("CAS redirect missing auth fragment")
        query = fragment.split("?", 1)[1]
        values = urllib.parse.parse_qs(query)
        lck = (values.get("lck") or [""])[0]
        entity_id = (values.get("entityId") or [""])[0]
        if not lck or not entity_id:
            raise WebVPNAuthError("CAS redirect missing lck/entityId")
        return lck, entity_id

    def _load_auth_chain_code(self, lck: str, entity_id: str) -> str:
        data = self._post_json(
            f"https://{_ID_HOST}/idp/authn/queryAuthMethods",
            {
                "lck": lck,
                "entityId": entity_id,
            },
        )

        if data.get("second") is True:
            raise WebVPNAuthError("CAS requires enhanced authentication (2FA)")

        methods = data.get("data")
        if not isinstance(methods, list):
            raise WebVPNAuthError("CAS auth methods missing")
        for method in methods:
            if not isinstance(method, dict):
                continue
            if method.get("moduleCode") == "userAndPwd":
                chain = method.get("authChainCode")
                if isinstance(chain, str) and chain:
                    return chain

        raise WebVPNAuthError("CAS userAndPwd auth method not found")

    def _load_public_key(self) -> Any:
        if RSA is None or PKCS1_v1_5 is None:
            raise WebVPNAuthError("CAS login requires pycryptodome RSA support")
        data = self._post_json(f"https://{_ID_HOST}/idp/authn/getJsPublicKey", {})
        encoded = data.get("data")
        if not isinstance(encoded, str) or not encoded.strip():
            raise WebVPNAuthError("CAS public key is missing")
        pem = f"-----BEGIN PUBLIC KEY-----\n{encoded}\n-----END PUBLIC KEY-----"
        try:
            return RSA.import_key(pem)
        except (ValueError, TypeError) as exc:
            raise WebVPNAuthError("CAS public key parse failed") from exc

    def _encrypt_password(self, public_key: Any, password: str) -> str:
        if PKCS1_v1_5 is None:
            raise WebVPNAuthError("RSA encrypt support unavailable")
        cipher = PKCS1_v1_5.new(public_key)
        encrypted = cipher.encrypt(password.encode("utf-8"))
        return base64.b64encode(encrypted).decode("ascii")

    def _execute_cas_auth(self, lck: str, entity_id: str, chain_code: str, encrypted_password: str) -> str:
        data = self._post_json(
            f"https://{_ID_HOST}/idp/authn/authExecute",
            {
                "authModuleCode": "userAndPwd",
                "authChainCode": chain_code,
                "entityId": entity_id,
                "requestType": "chain_type",
                "lck": lck,
                "authPara": {
                    "loginName": self.credentials.username,
                    "password": encrypted_password,
                    "verifyCode": "",
                },
            },
        )

        token = data.get("loginToken")
        if isinstance(token, str) and token:
            return token

        message = str(data.get("message") or "")
        raise WebVPNAuthError(f"CAS auth failed: {message or 'missing loginToken'}")

    def _extract_target_url_with_ticket(self, html: str) -> str:
        normalized = html_lib.unescape(html)

        # New id.fudan pages often redirect with JS instead of a strict form submit.
        redirect_match = re.search(r'locationValue\s*=\s*"([^"]+)"', normalized, flags=re.IGNORECASE)
        if redirect_match:
            redirect_url = redirect_match.group(1)
            if "ticket=" in redirect_url:
                return redirect_url

        form_tag_match = re.search(
            r'<form[^>]*\bid\s*=\s*["\']logon["\'][^>]*>',
            normalized,
            flags=re.IGNORECASE,
        )
        input_tag_match = re.search(
            r'<input[^>]*\bid\s*=\s*["\']ticket["\'][^>]*>',
            normalized,
            flags=re.IGNORECASE,
        )
        if not form_tag_match or not input_tag_match:
            raise WebVPNAuthError("CAS response missing ticket redirect form")

        action_match = re.search(r'\baction\s*=\s*["\']([^"\']+)', form_tag_match.group(0), flags=re.IGNORECASE)
        ticket_match = re.search(r'\bvalue\s*=\s*["\']([^"\']+)', input_tag_match.group(0), flags=re.IGNORECASE)
        if not action_match or not ticket_match:
            raise WebVPNAuthError("CAS response missing ticket action/value")

        action_url = action_match.group(1)
        ticket = ticket_match.group(1)
        parsed = urllib.parse.urlparse(action_url)
        query = urllib.parse.parse_qs(parsed.query)
        query["ticket"] = [ticket]
        return urllib.parse.urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                urllib.parse.urlencode(query, doseq=True),
                parsed.fragment,
            )
        )

    def _ensure_authenticated_via_cas(self) -> None:
        _, final_url = self._open(WEBVPN_LOGIN_URL)
        if final_url.startswith(f"https://{WEBVPN_HOST}/") and "login" not in final_url:
            self._authenticated = True
            return

        lck, entity_id = self._get_auth_params_from_redirect(final_url)
        chain_code = self._load_auth_chain_code(lck, entity_id)
        public_key = self._load_public_key()
        encrypted_password = self._encrypt_password(public_key, self.credentials.password)
        login_token = self._execute_cas_auth(lck, entity_id, chain_code, encrypted_password)

        req = urllib.request.Request(
            f"https://{_ID_HOST}/idp/authCenter/authnEngine",
            data=urllib.parse.urlencode({"loginToken": login_token}).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "danxi-daily-skill/1.0",
            },
        )
        body, _ = self._open(req)
        target_url = self._extract_target_url_with_ticket(body)
        self._open(target_url)
        self._authenticated = True

    def _ensure_authenticated(self) -> None:
        if self._authenticated:
            return

        # Prefer CAS flow because many campus accounts are not valid local WebVPN accounts.
        try:
            self._ensure_authenticated_via_cas()
            return
        except WebVPNAuthError:
            pass

        try:
            self._open(WEBVPN_LOGIN_URL)
            payload = urllib.parse.urlencode(
                {
                    "auth_type": "local",
                    "username": self.credentials.username,
                    "password": self.credentials.password,
                    "captcha": "",
                    "needCaptcha": "false",
                    "remember_cookie": "on",
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                WEBVPN_DO_LOGIN_URL,
                data=payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                    "User-Agent": "danxi-daily-skill/1.0",
                },
                method="POST",
            )
            body, _ = self._open(req)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise WebVPNAuthError(f"webvpn login request failed: {exc}") from exc

        try:
            result = json.loads(body)
        except json.JSONDecodeError as exc:
            raise WebVPNAuthError("webvpn login response is not valid JSON") from exc

        if not isinstance(result, dict):
            raise WebVPNAuthError("webvpn login response has unexpected format")

        if not result.get("success"):
            err = str(result.get("error") or "unknown_error")
            msg = str(result.get("message") or "")
            raise WebVPNAuthError(f"webvpn login failed: {err} {msg}".strip())

        redirect_url = str(result.get("url") or "/")
        absolute_url = urllib.parse.urljoin(WEBVPN_LOGIN_URL, redirect_url)
        try:
            self._open(absolute_url)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise WebVPNAuthError(f"webvpn post-login redirect failed: {exc}") from exc

        self._authenticated = True

    def _parse_auth_error_message(self, exc: urllib.error.HTTPError) -> str:
        try:
            payload = exc.read().decode("utf-8", errors="replace")
            data = json.loads(payload)
            if isinstance(data, dict):
                message = data.get("message")
                if isinstance(message, str) and message.strip():
                    return message
        except Exception:
            pass
        return f"HTTP {exc.code}"

    def _candidate_forum_emails(self) -> list[str]:
        username = self.credentials.username.strip()
        if not username:
            return []
        if "@" in username:
            return [username]
        return [f"{username}@m.fudan.edu.cn", f"{username}@fudan.edu.cn"]

    def obtain_forum_api_token(self) -> str:
        try:
            self._ensure_authenticated()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise WebVPNAuthError(f"webvpn auth session init failed: {exc}") from exc

        proxied_login_url = translate_to_webvpn(
            f"https://{_AUTH_HOST}/api/login",
            allowed_hosts={_AUTH_HOST},
        )
        if not proxied_login_url:
            raise WebVPNAuthError("cannot build auth service webvpn url")

        last_error: str = "login failed"
        for email in self._candidate_forum_emails():
            payload = {
                "email": email,
                "password": self.credentials.password,
            }
            req = urllib.request.Request(
                proxied_login_url,
                data=json.dumps(payload).encode("utf-8"),
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "danxi-daily-skill/1.0",
                },
            )

            try:
                body, _ = self._open_following_post_redirects(req, timeout=max(self.timeout, 20))
                data = json.loads(body)
                if not isinstance(data, dict):
                    raise WebVPNAuthError("auth login response format is invalid")
                access = data.get("access")
                if isinstance(access, str) and access.strip():
                    return access.strip()
                raise WebVPNAuthError("auth login response missing access token")
            except urllib.error.HTTPError as exc:
                message = self._parse_auth_error_message(exc)
                last_error = f"{email}: {message}"
                continue
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = f"{email}: network error: {exc}"
                continue
            except (json.JSONDecodeError, WebVPNAuthError) as exc:
                last_error = f"{email}: {exc}"
                continue

        raise WebVPNAuthError(f"cannot obtain DANXI_API_TOKEN via WebVPN: {last_error}")

    def request_json(
        self,
        target_url: str,
        *,
        params: dict[str, Any],
        token: str | None,
        timeout: int,
    ) -> Any:
        encoded = urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None},
            safe=":-TZ+.,",
        )
        full_target = f"{target_url}?{encoded}" if encoded else target_url
        proxied_url = translate_to_webvpn(full_target, allowed_hosts=self.allowed_hosts)
        if not proxied_url:
            raise WebVPNError("url is not supported by webvpn")

        self._ensure_authenticated()

        req = urllib.request.Request(proxied_url, method="GET", headers=_json_headers(token))
        try:
            payload, final_url = self._open(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace").strip()
            except Exception:
                detail = ""
            extra = f" body={detail[:200]}" if detail else ""
            raise WebVPNError(f"webvpn request failed: HTTP {exc.code} {exc.reason}{extra}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise WebVPNError(f"webvpn request failed: {exc}") from exc

        if final_url.startswith(f"https://{WEBVPN_HOST}/login"):
            self._authenticated = False
            raise WebVPNAuthError("webvpn session expired")

        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise WebVPNError("webvpn response is not valid JSON") from exc
