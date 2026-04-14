---
name: danxi-daily
description: >
  Generate DanXi daily report from hot holes.
  Trigger: When user asks for DanXi hot posts, forum digest, or daily summary.
license: MIT
metadata:
  author: 0patsick0
  contact: msa689704@gmail.com
  version: "1.0.0"
---

## Purpose

This skill generates a publish-ready daily report:
1. Fetch recent DanXi holes from API.
2. Rank posts by hotness.
3. Render Markdown for manual review and posting.

## Safety Defaults

- Dry-run by default.
- No posting is performed unless --post is explicitly enabled.

## Command

bash scripts/run_daily.sh --hours 24 --top 12

Windows (PowerShell) alternative:

scripts/run_daily.ps1 --hours 24 --top 12

First-time credential setup (recommended):

bash scripts/run_daily.sh --webvpn-mode force --hours 24 --top 12

## Common Options

- --hours: Time window in hours.
- --fetch-limit: Number of holes to fetch before ranking.
- --top: Number of posts in final report.
- --division-id: Optional division filter.
- --llm-provider: auto | openai | anthropic | none.
- --post: Enable posting.
- --post-endpoint: API endpoint for post submission.

## Environment Variables

- DANXI_BASE_URLS
- DANXI_API_TOKEN
- OPENAI_API_KEY / ANTHROPIC_API_KEY
- DANXI_POST_ENDPOINT
- DANXI_POST_TOKEN

## Output

- outputs/daily.md
- outputs/holes.raw.json
- outputs/ranked.json

## Trigger Examples

- Generate today's DanXi daily report.
- Summarize top DanXi holes in the last 24h.
- Prepare a post-ready forum digest for this morning.
