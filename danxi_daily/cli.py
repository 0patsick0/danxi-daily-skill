from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .pipeline import PipelineConfig, run_pipeline
from .security import normalize_allowed_hosts, require_https, validate_allowed_host


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate DanXi daily report.")
    parser.add_argument("--hours", type=int, default=24, help="How many recent hours to include.")
    parser.add_argument("--fetch-limit", type=int, default=120, help="How many holes to fetch.")
    parser.add_argument("--top", type=int, default=12, help="How many ranked holes to keep.")
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
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--prompt", type=Path, default=Path("prompts/summarize.md"))
    parser.add_argument("--output-markdown", type=Path, default=Path("outputs/daily.md"))
    parser.add_argument("--output-holes", type=Path, default=Path("outputs/holes.raw.json"))
    parser.add_argument("--output-ranked", type=Path, default=Path("outputs/ranked.json"))
    parser.add_argument("--title-prefix", type=str, default="DanXi Daily")
    parser.add_argument("--post", action="store_true", help="Actually post to forum endpoint.")
    parser.add_argument("--post-endpoint", type=str, default=os.getenv("DANXI_POST_ENDPOINT"))
    parser.add_argument("--verbose", action="store_true", help="Print extra details such as post response snippets.")
    return parser


def main() -> int:
    _load_dotenv(Path(".env"))
    parser = build_parser()
    args = parser.parse_args()

    base_urls = [x.strip().rstrip("/") for x in args.base_urls.split(",") if x.strip()]
    if not base_urls:
        parser.error("at least one base URL is required")

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
        api_token=os.getenv("DANXI_API_TOKEN"),
        llm_provider=args.llm_provider,
        timeout=args.timeout,
        title_prefix=args.title_prefix,
        post=args.post,
        post_endpoint=args.post_endpoint,
        post_token=os.getenv("DANXI_POST_TOKEN"),
        allowed_read_hosts=read_allowlist,
        allowed_post_hosts=post_allowlist,
        unsafe_allow_any_host=args.unsafe_allow_any_host,
        verbose=args.verbose,
    )

    result = run_pipeline(config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
