# Scheduling

GitHub's native `schedule:` trigger is **not a reliable clock**. This repo
has seen 9+ hour delays and complete skips. Do not keep changing the cron
minute. Do **not** re-add `on.schedule` to the workflow.

The runner stays GitHub Actions. The **clock must be cloud-side**, not this
PC.

```
22:00 CST  Cloudflare Worker cron (primary)
22:20 CST  Cloudflare Worker catch-up
         |
         v
GitHub Actions  workflow_dispatch only
  --post --post-once-per-day --post-at 22:00 --post-window-minutes 60
on failure: open a GitHub issue
```

## Why the 01:48 extra post happened

On 2026-09-03 the workflow still had GitHub `schedule:` crons
(`22:00` / `22:20` / `23:00` CST) **without** `--post-at`. GitHub fired the
22:00 cron ~4 hours late (01:48). `--post-once-per-day` used calendar
midnight, so 01:48 counted as a new day and published. The 23:00 last-chance
cron then fired at 02:30 and published again. That occupied slot `20260903`,
so the real 22:00 digest was skipped.

## Guards now in place

1. Cloudflare Worker cron is the only clock (`0 14 * * *`, `20 14 * * *` UTC).
2. GitHub workflow is `workflow_dispatch` only. `schedule` events are ignored
   even if the trigger is re-added.
3. `--post-at 22:00` is the day boundary, not calendar midnight.
4. `--post-window-minutes 60` refuses anything after 23:00, including delayed
   overnight runs.
5. A due skip (already posted / too early / outside window) exits before
   fetching, so a 22:20 catch-up does not burn WebVPN or fail on an expired
   token after 22:00 already succeeded.

Overlapping fires inside the window are safe: at most one post per 22:00
post-day.

## Clock A (active): Cloudflare Worker

See [cloud-clock/README.md](../cloud-clock/README.md). Independent of this PC.
Needs `wrangler login` plus a GitHub token stored as `GITHUB_DISPATCH_TOKEN`.

## Required repository secrets

Used by the workflow itself:

- `DANXI_POST_ENDPOINT`
- `DANXI_POST_TOKEN`
- `DANXI_API_TOKEN` (optional; CI refreshes it via WebVPN when expired)
- `DANXI_WEBVPN_USERNAME`
- `DANXI_WEBVPN_PASSWORD` (must be the current UIS password)

If WebVPN login fails, **stop retrying**. A wrong password can lock the
campus account.

## Workflow behavior

- Runs `scripts/generate_daily.py` with `--post`, WebVPN force mode,
  `--post-once-per-day`, `--post-at 22:00`, `--post-window-minutes 60`
- Uploads `outputs/daily.md`, `outputs/ranked.json`, `outputs/holes.raw.json`
- Default branch only; never `schedule`
- After a successful post, commits `outputs/last_post.sha256` and
  `outputs/last_post_slot.txt` (`[skip ci]`)
- On failure, opens or comments on a GitHub issue

## Manual dispatch

```powershell
scripts/dispatch_daily.ps1
scripts/dispatch_daily.ps1 -OnlyIfMissed
```

Manual real posts outside 22:00-23:00 Asia/Shanghai are skipped.

## Local generate (optional, not the daily clock)

Windows generate only:

```powershell
scripts/register_daily_task.ps1 -TaskName DanXiDailyReport -Time 08:00
```

Do **not** use this PC as the production clock.
