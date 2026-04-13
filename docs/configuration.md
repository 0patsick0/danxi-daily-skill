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

Trusted local development override:

python scripts/generate_daily.py --unsafe-allow-any-host
