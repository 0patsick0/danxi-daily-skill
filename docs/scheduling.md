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

## Option D: GitHub Actions (21:23 daily auto post, externally triggered)

Workflow file:

.github/workflows/daily-post.yml

GitHub's built-in `schedule:` trigger proved unreliable for this repo:
runs fired ~9.5-9.7 hours late on 2026-08-27 and 2026-08-28 regardless of
which cron minute was configured (tested 22:00, 21:30, and the off-minute
21:23 — same delay every time). This points to GitHub deprioritizing
`schedule:` events on low-activity repos rather than a config mistake.

The fix: drop `schedule:` entirely and trigger the workflow via its REST
API `workflow_dispatch` endpoint from an external cron service, at the
exact intended time (21:23 China Standard Time / UTC+8 daily).

### 1. Create a GitHub token

Create a fine-grained personal access token (Settings → Developer settings
→ Fine-grained tokens) scoped to just this repository, with:
- Repository permissions → **Actions: Read and write**

Fine-grained tokens with minimal scope are preferred over a classic PAT
with full `repo` access, since this token only needs to dispatch one
workflow.

### 2. Pick an external cron service

Any service that can send an HTTPS POST with custom headers on a schedule
works, e.g. cron-job.org, EasyCron, or a scheduled job on a VPS. Configure
it to fire daily at **13:23 UTC** (= 21:23 CST) and send:

Method: POST
URL: https://api.github.com/repos/{owner}/{repo}/actions/workflows/daily-post.yml/dispatches
Headers:
  Accept: application/vnd.github+json
  Authorization: Bearer <the fine-grained token from step 1>
  X-GitHub-Api-Version: 2022-11-28
Body (JSON):
  {"ref": "main"}

Store the token as a secret/credential inside the cron service's own
dashboard — never commit it to the repo or paste it into the workflow
file.

### 3. Verify

Trigger the same request manually once (e.g. with `curl` or Postman) to
confirm it returns HTTP 204 and a new run appears under the Actions tab,
then let the external service take over the daily firing.

Required repository secrets (used by the workflow itself, unrelated to
the token above):
- DANXI_POST_ENDPOINT
- DANXI_POST_TOKEN
- DANXI_API_TOKEN (optional)
- DANXI_WEBVPN_USERNAME (required for CI, since runners can't reach campus endpoints directly and must go through WebVPN)
- DANXI_WEBVPN_PASSWORD (required for CI, same reason)

Behavior:
- Runs `scripts/generate_daily.py` with `--post`, WebVPN force mode
- No `--post-at` gate — the external service's fire time controls timing
- Uploads `outputs/daily.md`, `outputs/ranked.json`, `outputs/holes.raw.json` as artifacts
- Only runs on the repository default branch (manual runs on other branches are skipped)
- After a successful post, commits `outputs/last_post.sha256` back to the
  repo (`[skip ci]`) so duplicate-post detection survives across runs

## Recommended Safety

- Keep posting disabled in scheduled runs unless fully verified.
- Monitor outputs/cron.log and outputs/daily.md each morning.
- If posting is enabled, set --post-at HH:MM to avoid early execution before your desired window.
