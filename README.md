# danxi-daily

A production-ready Skill project for generating DanXi daily reports.

## Features

- Dual endpoint fallback:
  - https://forum.fduhole.com/api
  - https://api.fduhole.com
- Hotness ranking with deterministic tie-breakers.
- LLM summarization (OpenAI or Anthropic) with extractive fallback.
- Markdown output for human review before posting.
- Optional posting mode with explicit --post switch.

## Quick Start

1. Create and activate a Python 3.10+ environment.
2. Copy .env.example to .env and fill required values.
3. Run:

python scripts/generate_daily.py --hours 24 --top 12

Generated files:
- outputs/daily.md
- outputs/holes.raw.json
- outputs/ranked.json

## Script Entry Points

- scripts/generate_daily.py: Full pipeline entry.
- scripts/fetch_holes.sh: Bash fetch-only step.
- scripts/rank_posts.py: Rank-only step from raw JSON.
- scripts/run_daily.sh / scripts/run_daily.ps1: Cross-platform wrappers.

## Posting Mode

Posting is disabled by default.
To post, provide endpoint and token:

python scripts/generate_daily.py --post --post-endpoint "https://your-endpoint.example/api/posts"

Requires environment variable:
- DANXI_POST_TOKEN

Security defaults:
- Only HTTPS endpoints are accepted.
- Read/post endpoint hosts must be in allowlists.
- Tokens are read from environment variables only (no CLI token arguments).

Optional (trusted local dev only):

python scripts/generate_daily.py --unsafe-allow-any-host

## Scheduling

See docs/scheduling.md for:
- Linux/macOS cron at 08:00
- Windows Task Scheduler at 08:00
- CronCreate prompt examples for agent-based setup

## Tests

python -m unittest discover -s tests -v

## Suggested GitHub Setup

Repository name suggestion: danxi-daily-skill

Example:

git init
git add .
git commit -m "feat: initial danxi daily skill"
git branch -M main
git remote add origin https://github.com/0patsick0/danxi-daily-skill.git
git push -u origin main
