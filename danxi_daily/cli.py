from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
from pathlib import Path

from .pipeline import PipelineConfig, run_pipeline
from .security import normalize_allowed_hosts, require_https, validate_allowed_host
from .webvpn import WebVPNAuthError, WebVPNClient, WebVPNCredentials, WebVPNError


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _default_base_urls() -> list[str]:
    text = os.getenv(
        "DANXI_BASE_URLS",
        "https://forum.fduhole.com/api,https://api.fduhole.com",
    )
    return [x.strip().rstrip("/") for x in text.split(",") if x.strip()]


def _bool_from_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be > 0")
    return parsed


def _hhmm_or_none(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    if re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", text) is None:
        raise argparse.ArgumentTypeError("time must be HH:MM in 24-hour format")
    return text


def _upsert_dotenv(path: Path, key: str, value: str) -> None:
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()

    updated = False
    for idx, line in enumerate(lines):
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        current_key = text.split("=", 1)[0].strip()
        if current_key == key:
            lines[idx] = f"{key}={value}"
            updated = True
            break

    if not updated:
        lines.append(f"{key}={value}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _prepare_webvpn_client(
    args: argparse.Namespace,
    env_path: Path,
    allowed_hosts: set[str],
) -> tuple[WebVPNClient | None, bool]:
    mode = args.webvpn_mode
    if mode == "off":
        return None, False

    username = (os.getenv("DANXI_WEBVPN_USERNAME") or "").strip()
    password = (os.getenv("DANXI_WEBVPN_PASSWORD") or "").strip()

    if mode == "auto" and (not username or not password):
        return None, False

    if (not username or not password) and mode == "force":
        prompted = _prompt_webvpn_credentials(args, env_path)
        if prompted is not None:
            username, password = prompted

    if mode == "force" and (not username or not password):
        raise ValueError("webvpn force mode requires DANXI_WEBVPN_USERNAME and DANXI_WEBVPN_PASSWORD")

    if not username or not password:
        return None, mode == "force"

    client = WebVPNClient(
        WebVPNCredentials(username=username, password=password),
        timeout=args.timeout,
        allowed_hosts=allowed_hosts,
    )
    return client, mode == "force"


def _prompt_webvpn_credentials(args: argparse.Namespace, env_path: Path) -> tuple[str, str] | None:
    if args.webvpn_no_prompt or (not sys.stdin.isatty()):
        return None

    username = (os.getenv("DANXI_WEBVPN_USERNAME") or "").strip()
    password = (os.getenv("DANXI_WEBVPN_PASSWORD") or "").strip()

    if username and password:
        return username, password

    print("WebVPN 首次认证：请输入复旦统一身份账号和密码。")
    if not username:
        username = input("WebVPN 用户名: ").strip()
    if not password:
        password = getpass.getpass("WebVPN 密码: ").strip()

    if not username or not password:
        return None

    should_save_credentials = args.webvpn_save_credentials and (not args.webvpn_no_save_credentials)
    if should_save_credentials:
        _upsert_dotenv(env_path, "DANXI_WEBVPN_USERNAME", username)
        _upsert_dotenv(env_path, "DANXI_WEBVPN_PASSWORD", password)
        os.environ.setdefault("DANXI_WEBVPN_USERNAME", username)
        os.environ.setdefault("DANXI_WEBVPN_PASSWORD", password)

    return username, password


def _should_persist_secrets(args: argparse.Namespace) -> bool:
    return args.webvpn_save_credentials and (not args.webvpn_no_save_credentials)


def _maybe_fill_api_token(
    args: argparse.Namespace,
    env_path: Path,
    webvpn_client: WebVPNClient | None,
    api_token: str | None,
) -> str | None:
    if api_token or webvpn_client is None:
        return api_token

    try:
        new_token = webvpn_client.obtain_forum_api_token()
    except (WebVPNAuthError, WebVPNError):
        return api_token

    if not isinstance(new_token, str) or not new_token.strip():
        return api_token

    normalized_token = new_token.strip()

    if _should_persist_secrets(args):
        _upsert_dotenv(env_path, "DANXI_API_TOKEN", normalized_token)
        os.environ.setdefault("DANXI_API_TOKEN", normalized_token)
    return normalized_token


def _refresh_api_token(
    args: argparse.Namespace,
    env_path: Path,
    webvpn_client: WebVPNClient | None,
) -> str | None:
    if webvpn_client is None:
        return None
    try:
        refreshed = webvpn_client.obtain_forum_api_token()
    except (WebVPNAuthError, WebVPNError):
        return None

    if not isinstance(refreshed, str) or not refreshed.strip():
        return None

    token = refreshed.strip()
    if _should_persist_secrets(args):
        _upsert_dotenv(env_path, "DANXI_API_TOKEN", token)
        os.environ.setdefault("DANXI_API_TOKEN", token)
    return token


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate DanXi daily report.")
    parser.add_argument("--hours", type=int, default=24, help="Reserved for compatibility; daily report always uses today's full range.")
    parser.add_argument("--fetch-limit", type=int, default=10, help="How many holes to fetch (API max: 10).")
    parser.add_argument("--top", type=int, default=10, help="How many ranked holes to keep.")
    parser.add_argument("--division-id", type=int, default=None, help="Optional division filter.")
    parser.add_argument("--base-urls", type=str, default=",".join(_default_base_urls()))
    parser.add_argument(
        "--allowed-read-hosts",
        type=str,
        default=os.getenv("DANXI_ALLOWED_READ_HOSTS", "forum.fduhole.com,api.fduhole.com"),
        help="Comma-separated read endpoint host allowlist.",
    )
    parser.add_argument(
        "--allowed-post-hosts",
        type=str,
        default=os.getenv("DANXI_ALLOWED_POST_HOSTS", "forum.fduhole.com,api.fduhole.com"),
        help="Comma-separated post endpoint host allowlist.",
    )
    parser.add_argument(
        "--unsafe-allow-any-host",
        action="store_true",
        help="Bypass URL host allowlist checks. Use only in trusted local dev.",
    )
    parser.add_argument("--llm-provider", type=str, default=os.getenv("DANXI_LLM_PROVIDER", "auto"))
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--floor-enrich-size", type=int, default=int(os.getenv("DANXI_FLOOR_ENRICH_SIZE", "40")))
    parser.add_argument(
        "--floor-enrich-workers",
        type=_positive_int,
        default=int(os.getenv("DANXI_FLOOR_ENRICH_WORKERS", "6")),
        help="Concurrent workers for fetching floor details.",
    )
    parser.add_argument(
        "--floor-enrich-timeout",
        type=_positive_int,
        default=int(os.getenv("DANXI_FLOOR_ENRICH_TIMEOUT", "8")),
        help="Per-floor request timeout seconds.",
    )
    parser.add_argument(
        "--floor-cache-file",
        type=Path,
        default=Path(os.getenv("DANXI_FLOOR_CACHE_FILE", "outputs/floors_cache.json")),
        help="Cache file for prefetched floors.",
    )
    parser.add_argument("--prompt", type=Path, default=Path("prompts/summarize.md"))
    parser.add_argument("--output-markdown", type=Path, default=Path("outputs/daily.md"))
    parser.add_argument("--output-holes", type=Path, default=Path("outputs/holes.raw.json"))
    parser.add_argument("--output-ranked", type=Path, default=Path("outputs/ranked.json"))
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=Path(os.getenv("DANXI_ARCHIVE_DIR", "outputs/history")),
        help="Directory for timestamped report archives.",
    )
    parser.add_argument(
        "--archive-outputs",
        action="store_true",
        default=_bool_from_env("DANXI_ARCHIVE_OUTPUTS", True),
        help="Write timestamped history files on every run.",
    )
    parser.add_argument(
        "--no-archive-outputs",
        action="store_true",
        help="Disable timestamped history files.",
    )
    parser.add_argument("--title-prefix", type=str, default="旦夕热榜日报")
    parser.add_argument(
        "--webvpn-mode",
        choices=["auto", "off", "force"],
        default=os.getenv("DANXI_WEBVPN_MODE", "auto").strip().lower(),
        help="auto: direct first then webvpn fallback; off: disable webvpn; force: webvpn only",
    )
    parser.add_argument(
        "--webvpn-no-prompt",
        action="store_true",
        help="Disable interactive credential prompt when webvpn credentials are missing.",
    )
    parser.add_argument(
        "--webvpn-save-credentials",
        action="store_true",
        default=_bool_from_env("DANXI_WEBVPN_SAVE_CREDENTIALS", True),
        help="Persist prompted webvpn credentials into .env for next runs.",
    )
    parser.add_argument(
        "--webvpn-no-save-credentials",
        action="store_true",
        help="Do not persist prompted webvpn credentials to .env.",
    )
    parser.add_argument("--post", action="store_true", help="Actually post to forum endpoint.")
    parser.add_argument("--post-endpoint", type=str, default=os.getenv("DANXI_POST_ENDPOINT"))
    parser.add_argument(
        "--post-at",
        type=_hhmm_or_none,
        default=(os.getenv("DANXI_POST_AT") or "").strip() or None,
        help="Only post at/after local HH:MM each day. Example: 08:00",
    )
    parser.add_argument("--verbose", action="store_true", help="Print extra details such as post response snippets.")
    return parser


def main() -> int:
    env_path = Path(".env")
    _load_dotenv(env_path)
    parser = build_parser()
    args = parser.parse_args()

    if args.post_at is not None:
        try:
            args.post_at = _hhmm_or_none(str(args.post_at))
        except argparse.ArgumentTypeError as exc:
            parser.error(f"invalid DANXI_POST_AT/--post-at: {exc}")

    if args.webvpn_mode not in {"auto", "off", "force"}:
        parser.error("webvpn mode must be one of: auto, off, force")

    base_urls = [x.strip().rstrip("/") for x in args.base_urls.split(",") if x.strip()]
    if not base_urls:
        parser.error("at least one base URL is required")

    if args.fetch_limit > 10:
        args.fetch_limit = 10

    default_prompt = Path("prompts/summarize.md")
    llm_provider_text = str(args.llm_provider).strip().lower()
    if llm_provider_text not in {"", "auto", "none"} or args.prompt != default_prompt:
        print(
            "[notice] 当前版本已移除“话题解读”输出，--llm-provider 与 --prompt 参数将被忽略。",
            file=sys.stderr,
        )

    read_allowlist = normalize_allowed_hosts(args.allowed_read_hosts)
    post_allowlist = normalize_allowed_hosts(args.allowed_post_hosts)

    for url in base_urls:
        require_https(url)
        if not args.unsafe_allow_any_host:
            validate_allowed_host(url, read_allowlist)

    if args.post:
        if not args.post_endpoint:
            parser.error("--post requires --post-endpoint or DANXI_POST_ENDPOINT")
        require_https(args.post_endpoint)
        if not args.unsafe_allow_any_host:
            validate_allowed_host(args.post_endpoint, post_allowlist)

    try:
        webvpn_client, force_webvpn = _prepare_webvpn_client(args, env_path, read_allowlist)
    except ValueError as exc:
        parser.error(str(exc))

    api_token = _maybe_fill_api_token(args, env_path, webvpn_client, os.getenv("DANXI_API_TOKEN"))

    config = PipelineConfig(
        base_urls=base_urls,
        hours=args.hours,
        fetch_limit=args.fetch_limit,
        top_n=args.top,
        division_id=args.division_id,
        prompt_path=args.prompt,
        output_markdown=args.output_markdown,
        output_holes=args.output_holes,
        output_ranked=args.output_ranked,
        api_token=api_token,
        llm_provider=args.llm_provider,
        timeout=args.timeout,
        floor_enrich_size=max(0, args.floor_enrich_size),
        floor_fetch_workers=max(1, args.floor_enrich_workers),
        floor_fetch_timeout=max(1, args.floor_enrich_timeout),
        floor_cache_file=args.floor_cache_file,
        title_prefix=args.title_prefix,
        archive_outputs=args.archive_outputs and (not args.no_archive_outputs),
        archive_dir=args.archive_dir,
        post=args.post,
        post_endpoint=args.post_endpoint,
        post_token=os.getenv("DANXI_POST_TOKEN"),
        post_schedule_hhmm=args.post_at,
        allowed_read_hosts=read_allowlist,
        allowed_post_hosts=post_allowlist,
        unsafe_allow_any_host=args.unsafe_allow_any_host,
        verbose=args.verbose,
        webvpn_client=webvpn_client,
        force_webvpn=force_webvpn,
    )

    try:
        result = run_pipeline(config)
    except RuntimeError:
        refreshed_token = _refresh_api_token(args, env_path, config.webvpn_client)
        if refreshed_token and refreshed_token != config.api_token:
            config.api_token = refreshed_token
            result = run_pipeline(config)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        can_retry_with_prompt = (
            args.webvpn_mode == "auto"
            and webvpn_client is None
            and (not args.webvpn_no_prompt)
            and sys.stdin.isatty()
        )
        if not can_retry_with_prompt:
            raise

        prompted = _prompt_webvpn_credentials(args, env_path)
        if prompted is None:
            raise

        username, password = prompted
        config.webvpn_client = WebVPNClient(
            WebVPNCredentials(username=username, password=password),
            timeout=args.timeout,
            allowed_hosts=read_allowlist,
        )
        # For prompted first-time credentials, force a fresh token and prefer WebVPN path for this retry.
        config.force_webvpn = True
        refreshed_after_prompt = _refresh_api_token(args, env_path, config.webvpn_client)
        if refreshed_after_prompt:
            config.api_token = refreshed_after_prompt
        else:
            config.api_token = _maybe_fill_api_token(args, env_path, config.webvpn_client, config.api_token)
        result = run_pipeline(config)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
