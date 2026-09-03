# Scheduling

GitHub's native `schedule:` trigger is **not a reliable clock**. This repo
has seen 9+ hour delays and complete skips. Do not keep changing the cron
minute.

The runner stays GitHub Actions. The **clock must be cloud-side**, not this
PC.

```
22:00 CST  Cloudflare Worker cron (primary)
22:20 CST  Cloudflare Worker catch-up
         |
         v
GitHub Actions  --post --post-once-per-day --post-at 22:00
on failure: open a GitHub issue

GitHub native `schedule:` is disabled. It ran ~4 hours late on
2026-09-03 01:48 CST and posted again because calendar-day dedupe
treated 01:48 as a new day. Day boundary is now 22:00, not midnight.
```

Overlapping fires are safe. The workflow posts at most once per
Asia/Shanghai calendar day.

## Clock A (active): Grok cloud automation

Runs on xAI, not on this PC.

- `danxi-daily-dispatch` at **22:00 Asia/Shanghai**
- `danxi-daily-dispatch-catchup` at **22:30 Asia/Shanghai**
- Dispatches `DanXi Daily Auto Post` on `0patsick0/danxi-daily-skill`
- Skips if `outputs/last_post_slot.txt` is already today's date
- Emails on failure

## Clock B (optional extra): Cloudflare Worker

See [cloud-clock/README.md](../cloud-clock/README.md). Independent of Grok
and of this PC. Needs `wrangler login` plus a fine-grained GitHub PAT
stored as `GITHUB_DISPATCH_TOKEN`.

## Clock C (last resort): GitHub native schedule

`.github/workflows/daily-post.yml` still has a catch-up window. Treat as
backup only.

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

- Runs `scripts/generate_daily.py` with `--post`, WebVPN force mode, `--post-once-per-day`
- Uploads `outputs/daily.md`, `outputs/ranked.json`, `outputs/holes.raw.json`
- Default branch only
- After a successful post, commits `outputs/last_post.sha256` and
  `outputs/last_post_slot.txt` (`[skip ci]`)
- On failure, opens or comments on a GitHub issue

## Manual dispatch

```powershell
scripts/dispatch_daily.ps1
scripts/dispatch_daily.ps1 -OnlyIfMissed
```

## Local generate (optional, not the daily clock)

Windows generate only:

```powershell
scripts/register_daily_task.ps1 -TaskName DanXiDailyReport -Time 08:00
```

Do **not** use this PC as the production clock.
