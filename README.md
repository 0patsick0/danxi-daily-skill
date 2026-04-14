# danxi-daily

A production-ready Skill project for generating DanXi daily reports.

## Install To Claude (1 minute)

### Option A: Git clone (recommended)

Windows (PowerShell):

git clone https://github.com/0patsick0/danxi-daily-skill.git "$HOME/.claude/skills/danxi-daily"

macOS/Linux:

git clone https://github.com/0patsick0/danxi-daily-skill.git ~/.claude/skills/danxi-daily

### Option B: Download ZIP

1. Download this repository as ZIP.
2. Extract to:
  - Windows: %USERPROFILE%/.claude/skills/danxi-daily
  - macOS/Linux: ~/.claude/skills/danxi-daily

Then restart Claude Code / reopen your session.

## Features

- Dual endpoint fallback:
  - https://forum.fduhole.com/api
  - https://api.fduhole.com
- Multi-window hotspot sampling across recent 24h slices (1/2/4/8/12/24h), then dedupe.
- Hotness ranking focused on view/reply signals with deterministic tie-breakers.
- Invalid-discussion filtering for low-value threads (e.g., 收资料/出资料/代课).
- LLM summarization (OpenAI or Anthropic) with extractive fallback.
- Markdown output for human review before posting.
- Optional posting mode with explicit --post switch.

## Quick Start

1. Create and activate a Python 3.10+ environment.
2. Copy .env.example to .env and fill required values.
3. Run:

python scripts/generate_daily.py --hours 24 --top 12

Note: current forum API limits `length` to 10 per request. The CLI clamps `--fetch-limit` to 10 automatically.

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

WebVPN fallback:
- Default mode is `auto`: direct first, then WebVPN fallback on connection failures.
- First interactive run can prompt for WebVPN student credentials and persist to `.env`.
- If `DANXI_API_TOKEN` is empty, the tool will try to exchange WebVPN credentials for a forum API token automatically.
- Set `DANXI_WEBVPN_MODE=off` to disable, or `DANXI_WEBVPN_MODE=force` to use WebVPN only.

Optional (trusted local dev only):

python scripts/generate_daily.py --unsafe-allow-any-host

Non-interactive runs can disable prompts:

python scripts/generate_daily.py --webvpn-no-prompt

Do not persist prompted WebVPN credentials:

python scripts/generate_daily.py --webvpn-no-save-credentials

## Scheduling

See docs/scheduling.md for:
- Linux/macOS cron at 08:00
- Windows Task Scheduler at 08:00
- CronCreate prompt examples for agent-based setup

## Tests

python -m unittest discover -s tests -v
