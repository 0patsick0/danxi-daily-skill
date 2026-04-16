# Configuration

## Priority

Configuration priority is:
1. CLI arguments
2. Environment variables
3. Built-in defaults

## Key Variables

- DANXI_BASE_URLS
  - Comma-separated API base URLs.
  - Default: https://forum.fduhole.com/api,https://api.fduhole.com

- DANXI_ALLOWED_READ_HOSTS
  - Host allowlist for read endpoints.
  - Default: forum.fduhole.com,api.fduhole.com

- DANXI_ALLOWED_POST_HOSTS
  - Host allowlist for post endpoint.
  - Default: forum.fduhole.com,api.fduhole.com

- DANXI_API_TOKEN
  - Optional for read requests, required on some deployments.

- DANXI_LLM_PROVIDER
  - auto | openai | anthropic | none

- OPENAI_API_KEY / OPENAI_MODEL
- ANTHROPIC_API_KEY / ANTHROPIC_MODEL

- DANXI_POST_ENDPOINT
- DANXI_POST_TOKEN

- DANXI_POST_AT
  - Optional daily post window in local time, format HH:MM.
  - Example: 08:00 (posting will only happen at/after this time).

- DANXI_ARCHIVE_OUTPUTS
  - true | false
  - Default: true

- DANXI_ARCHIVE_DIR
  - Directory for timestamped report history.
  - Default: outputs/history

- DANXI_FLOOR_ENRICH_SIZE
  - Number of floors fetched per hole.
  - Default: 40

- DANXI_FLOOR_ENRICH_WORKERS
  - Concurrent workers used for floor fetching.
  - Default: 6

- DANXI_FLOOR_ENRICH_TIMEOUT
  - Per-floor request timeout in seconds.
  - Default: 8

- DANXI_FLOOR_CACHE_FILE
  - JSON cache path for floor prefetch data.
  - Default: outputs/floors_cache.json

Token policy:
- Use environment variables only.
- Do not pass tokens in command line arguments.

## Core CLI Examples

Generate daily report from last 24h:

python scripts/generate_daily.py --hours 24 --top 12

Use only one endpoint:

python scripts/generate_daily.py --base-urls "https://forum.fduhole.com/api"

Disable LLM API and force fallback summaries:

python scripts/generate_daily.py --llm-provider none

Enable posting mode:

python scripts/generate_daily.py --post --post-endpoint "https://example.com/api/post"

Enable posting mode with daily time window:

python scripts/generate_daily.py --post --post-endpoint "https://example.com/api/post" --post-at 08:00

Disable timestamped archives:

python scripts/generate_daily.py --no-archive-outputs

Trusted local development override:

python scripts/generate_daily.py --unsafe-allow-any-host
