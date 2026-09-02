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
- Daily full-range fetching from local 00:00 to now, with paged aggregation and dedupe.
- Concurrent floor prefetch with local cache for faster repeated runs.
- Timestamped history archive on every run (no overwrite of old reports).
- Hotness ranking focused on view/reply signals with deterministic tie-breakers.
- Invalid-discussion filtering for low-value threads (e.g., 收资料/出资料/代课).
- LLM summarization (OpenAI or Anthropic) with extractive fallback.
- Markdown output for human review before posting.
- Optional posting mode with explicit --post switch.
- Optional post window control (`--post-at HH:MM`) to avoid accidental early posts.

## Quick Start

1. Create and activate a Python 3.10+ environment.
2. Copy .env.example to .env and fill required values.
3. Run:

Windows (PowerShell):

py scripts/generate_daily.py --hours 24 --top 10

macOS/Linux:

python3 scripts/generate_daily.py --hours 24 --top 10

Wrapper command (auto-select interpreter):

PowerShell: scripts/run_daily.ps1 --hours 24 --top 10
Bash: bash scripts/run_daily.sh --hours 24 --top 10

Note: current forum API limits `length` to 10 per request. The CLI clamps `--fetch-limit` to 10 automatically.

Generated files:
- outputs/daily.md
- outputs/holes.raw.json
- outputs/ranked.json
- outputs/history/YYYYMM/daily_*.md
- outputs/history/YYYYMM/holes_*.json
- outputs/history/YYYYMM/ranked_*.json

## Script Entry Points

- scripts/generate_daily.py: Full pipeline entry.
- scripts/fetch_holes.sh: Bash fetch-only step.
- scripts/rank_posts.py: Rank-only step from raw JSON.
- scripts/run_daily.sh / scripts/run_daily.ps1: Cross-platform wrappers.

## Posting Mode

Posting is disabled by default.
To post, provide endpoint and token:

PowerShell: py scripts/generate_daily.py --post --post-endpoint "https://your-endpoint.example/api/posts"
macOS/Linux: python3 scripts/generate_daily.py --post --post-endpoint "https://your-endpoint.example/api/posts"

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
- For first-time setup in unstable networks, prefer forcing WebVPN once:
  - PowerShell: `py scripts/generate_daily.py --webvpn-mode force --hours 24 --top 10`
  - Bash: `bash scripts/run_daily.sh --webvpn-mode force --hours 24 --top 10`
- Stability tuning (optional):
  - `DANXI_WEBVPN_RETRIES` (default 5)
  - `DANXI_WEBVPN_BACKOFF_BASE` (default 0.8)
  - `DANXI_WEBVPN_TIMEOUT_SCALE` (default 1.35)

Optional (trusted local dev only):

PowerShell: py scripts/generate_daily.py --unsafe-allow-any-host
macOS/Linux: python3 scripts/generate_daily.py --unsafe-allow-any-host

Non-interactive runs can disable prompts:

PowerShell: py scripts/generate_daily.py --webvpn-no-prompt
macOS/Linux: python3 scripts/generate_daily.py --webvpn-no-prompt

Do not persist prompted WebVPN credentials:

PowerShell: py scripts/generate_daily.py --webvpn-no-save-credentials
macOS/Linux: python3 scripts/generate_daily.py --webvpn-no-save-credentials

## Scheduling

GitHub's native `schedule:` trigger is not a reliable clock. Keep GitHub
Actions as the **runner**. The production clock is **cloud-side** (Grok
automation at 20:17 / 21:30 Asia/Shanghai), not this PC.

Manual dispatch:

```powershell
scripts/dispatch_daily.ps1
```

See [docs/scheduling.md](docs/scheduling.md). Do not use Windows Task
Scheduler as the daily clock.

## GitHub Actions (external dispatch + catch-up)

[.github/workflows/daily-post.yml](.github/workflows/daily-post.yml) is started
by `workflow_dispatch`. Native `schedule:` times are a last-resort catch-up
window only.

Required repository secrets:
- DANXI_POST_ENDPOINT
- DANXI_POST_TOKEN
- DANXI_API_TOKEN (optional; refreshed via WebVPN when expired)
- DANXI_WEBVPN_USERNAME (required for CI)
- DANXI_WEBVPN_PASSWORD (required for CI; must match the current UIS password)

Safety behavior:
- Workflow only runs on the repository default branch.
- `--post-once-per-day` so overlapping triggers do not double-post.
- Failed runs open a GitHub issue. Do not keep retrying after a password error.

## Tests

python -m unittest discover -s tests -v
