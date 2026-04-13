#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_FILE="outputs/holes.raw.json"
HOURS="24"
LIMIT="120"
DIVISION_ID=""
BASE_URLS="${DANXI_BASE_URLS:-https://forum.fduhole.com/api,https://api.fduhole.com}"
ALLOWED_READ_HOSTS="${DANXI_ALLOWED_READ_HOSTS:-forum.fduhole.com,api.fduhole.com}"
UNSAFE_ALLOW_ANY_HOST="${DANXI_UNSAFE_ALLOW_ANY_HOST:-0}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT_FILE="$2"; shift 2 ;;
    --hours) HOURS="$2"; shift 2 ;;
    --limit) LIMIT="$2"; shift 2 ;;
    --division-id) DIVISION_ID="$2"; shift 2 ;;
    --base-urls) BASE_URLS="$2"; shift 2 ;;
    --token) echo "--token is disabled for safety; use DANXI_API_TOKEN env var" >&2; exit 1 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

mkdir -p "$(dirname "$OUT_FILE")"

ROOT_DIR="$ROOT_DIR" \
OUT_FILE="$OUT_FILE" \
HOURS="$HOURS" \
LIMIT="$LIMIT" \
DIVISION_ID="$DIVISION_ID" \
BASE_URLS="$BASE_URLS" \
ALLOWED_READ_HOSTS="$ALLOWED_READ_HOSTS" \
UNSAFE_ALLOW_ANY_HOST="$UNSAFE_ALLOW_ANY_HOST" \
python - <<'PY'
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

root = Path(os.environ["ROOT_DIR"]).resolve()
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from danxi_daily.client import fetch_holes_with_fallback
from danxi_daily.security import normalize_allowed_hosts, require_https, validate_allowed_host

out_file = Path(os.environ["OUT_FILE"])
hours = int(os.environ["HOURS"])
limit = int(os.environ["LIMIT"])
division_text = os.environ.get("DIVISION_ID", "").strip()
division_id = int(division_text) if division_text else None
base_urls = [x.strip().rstrip("/") for x in os.environ["BASE_URLS"].split(",") if x.strip()]
allowed_hosts = normalize_allowed_hosts(os.environ["ALLOWED_READ_HOSTS"])
unsafe = os.environ.get("UNSAFE_ALLOW_ANY_HOST", "0").strip() in {"1", "true", "True"}

for url in base_urls:
    require_https(url)
    if not unsafe:
        validate_allowed_host(url, allowed_hosts)

start_time = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat().replace("+00:00", "Z")
holes, endpoint = fetch_holes_with_fallback(
    base_urls=base_urls,
    start_time=start_time,
    limit=limit,
    division_id=division_id,
    token=os.getenv("DANXI_API_TOKEN"),
)

out_file.parent.mkdir(parents=True, exist_ok=True)
out_file.write_text(json.dumps(holes, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"saved={len(holes)} endpoint={endpoint}")
PY
