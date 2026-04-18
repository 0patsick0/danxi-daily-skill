# Scheduling

## Option A: Linux/macOS cron

Run at 08:00 every day:

0 8 * * * cd /path/to/danxi-daily && /usr/bin/python3 scripts/generate_daily.py --hours 24 --top 12 >> outputs/cron.log 2>&1

## Option B: Windows Task Scheduler

Create a daily task at 08:00:

Program/script:
python

Arguments:
scripts/generate_daily.py --hours 24 --top 12

Start in:
C:\path\to\danxi-daily

Or use the built-in helper script:

Generate only:

scripts/register_daily_task.ps1 -TaskName DanXiDailyReport -Time 08:00

Generate + publish after 08:00:

scripts/register_daily_task.ps1 -TaskName DanXiDailyPublish -Time 08:00 -EnablePost

Prerequisite for `-EnablePost`:
- `DANXI_POST_ENDPOINT` and `DANXI_POST_TOKEN` must exist in environment variables or `.env`.

The helper writes logs to outputs/cron.log.

## Option C: Agent-based CronCreate prompt

Use this prompt inside your coding agent:

Create a daily scheduled task at 08:00 local time to run:
python scripts/generate_daily.py --hours 24 --top 12
in the danxi-daily project root, and write logs to outputs/cron.log.

## Option D: GitHub Actions (23:30 daily auto post)

Workflow file:

.github/workflows/daily-post.yml

Schedule:
- 23:30 China Standard Time (UTC+8)
- Cron in GitHub Actions is UTC, so it uses: `30 15 * * *`

Required repository secrets:
- DANXI_POST_ENDPOINT
- DANXI_POST_TOKEN
- DANXI_API_TOKEN (optional)
- DANXI_WEBVPN_USERNAME (optional, for auto token refresh)
- DANXI_WEBVPN_PASSWORD (optional, for auto token refresh)

Behavior:
- Runs `scripts/generate_daily.py` with `--post` and `--post-at 23:30`
- Uses WebVPN auto mode for token refresh in CI
- Uploads `outputs/daily.md`, `outputs/ranked.json`, `outputs/holes.raw.json` as artifacts
- Only runs on the repository default branch (manual runs on other branches are skipped)

## Recommended Safety

- Keep posting disabled in scheduled runs unless fully verified.
- Monitor outputs/cron.log and outputs/daily.md each morning.
- If posting is enabled, set --post-at HH:MM to avoid early execution before your desired window.
