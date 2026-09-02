# Scheduling

GitHub's native `schedule:` trigger is **not a reliable clock**. For this
repository it has:

- fired ~9.5 hours late (2026-08-27 / 2026-08-28), independent of cron minute
- gone silent after the workflow was edited back and forth
- been confused with "didn't run" when a manual/external `workflow_dispatch`
  later failed for a different reason (expired token / WebVPN login)

Do **not** keep changing the cron minute. That does not fix platform delay,
and it resets GitHub's scheduler state.

**Never-miss setup = independent clocks + one-post-per-day + failure issue.**
The runner stays GitHub Actions. At least one clock must live *outside*
GitHub's scheduler.

```
20:17  Clock A: this PC (Task Scheduler)  -->  workflow_dispatch
20:17  Clock B: cron-job.org (cloud)      -->  workflow_dispatch
21:30  Clock A catch-up
22:45  Clock A catch-up
20:17/21:47/23:17  Clock C: GitHub cron (last resort)
                    |
                    v
         GitHub Actions job
         --post --post-once-per-day
         on failure: open a GitHub issue
```

Overlapping fires are safe: `dispatch_daily.ps1 -OnlyIfMissed` skips when
`outputs/last_post_slot.txt` is already today's CST date, and the workflow
also refuses a second post the same local day.

## Clock A (required): Windows Task Scheduler

Calls `gh workflow run` immediately. Does not wait for GitHub cron.

Prerequisite:

- GitHub CLI installed and authenticated (`gh auth status`)
- This Windows user logged on (lock screen is OK; full shutdown is not)
- Repository secrets up to date (see below)

Register primary + evening catch-ups. Prefer an ASCII working directory
(Chinese paths break Task Scheduler encoding). This repo is linked at
`C:\danxi-daily`:

```powershell
scripts/register_daily_task.ps1 -TaskName DanXiDailyDispatch -Time 20:17 -CatchUpTimes 21:30,22:45 -DispatchGitHub -ProjectRoot C:\danxi-daily
```

The task uses `-StartWhenAvailable` and `-OnlyIfMissed`. If the PC was
asleep at 20:17, Windows should run it when it next wakes the same day.

Manual fire:

```powershell
scripts/dispatch_daily.ps1
scripts/dispatch_daily.ps1 -OnlyIfMissed
```

Logs: `outputs/cron.log`.

**Limit:** if this PC is powered off or the user is logged out all evening,
Clock A cannot fire until the next login. Add Clock B.

## Clock B (required if the PC may be off): cron-job.org

Cloud HTTPS cron. Independent of this PC and of GitHub's scheduler.

1. GitHub → Settings → Developer settings → Fine-grained tokens.
   Repo `danxi-daily-skill` only, permission **Actions: Read and write**.
2. https://cron-job.org → create two jobs, timezone **UTC**:

| When (UTC) | Meaning |
|---|---|
| `17 12 * * *` | 20:17 CST primary |
| `30 13 * * *` | 21:30 CST catch-up |

3. Each job:

```
POST https://api.github.com/repos/0patsick0/danxi-daily-skill/actions/workflows/daily-post.yml/dispatches
Accept: application/vnd.github+json
Authorization: Bearer <the fine-grained token>
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json

{"ref": "main"}
```

Store the token in cron-job.org, never in this repo. A 204 response means
GitHub accepted the dispatch.

## Backup clock: cron-job.org / EasyCron / a VPS

Any HTTPS cron that can POST with an Authorization header works.

1. Create a fine-grained PAT scoped to this repo, permission **Actions: Read and write**.
2. Fire daily at **12:17 UTC** (= 20:17 CST):

```
POST https://api.github.com/repos/0patsick0/danxi-daily-skill/actions/workflows/daily-post.yml/dispatches
Accept: application/vnd.github+json
Authorization: Bearer <token>
X-GitHub-Api-Version: 2022-11-28

{"ref": "main"}
```

Store the token in the cron service, never in the repo.

## Last-resort: GitHub native schedule

`.github/workflows/daily-post.yml` still has a catch-up window:

- 20:17 CST target
- 21:47 CST catch-up
- 23:17 CST last-chance

Treat these as backups only. `--post-once-per-day` makes overlapping
triggers safe.

## Required repository secrets

Used by the workflow itself (unrelated to the dispatch token above):

- `DANXI_POST_ENDPOINT`
- `DANXI_POST_TOKEN`
- `DANXI_API_TOKEN` (optional; CI refreshes it via WebVPN when expired)
- `DANXI_WEBVPN_USERNAME` (required for CI)
- `DANXI_WEBVPN_PASSWORD` (required for CI; must be the current UIS password)

If WebVPN login fails, **stop retrying**. A wrong password can lock the
campus account. Update the secrets first, then dispatch once.

## Workflow behavior

- Runs `scripts/generate_daily.py` with `--post`, WebVPN force mode, `--post-once-per-day`
- No `--post-at` gate — the external clock controls timing
- Uploads `outputs/daily.md`, `outputs/ranked.json`, `outputs/holes.raw.json`
- Default branch only
- After a successful post, commits `outputs/last_post.sha256` and
  `outputs/last_post_slot.txt` (`[skip ci]`)
- On failure, opens or comments on a GitHub issue so a silent skip is visible

## Local generate (no GitHub)

Windows generate only:

```powershell
scripts/register_daily_task.ps1 -TaskName DanXiDailyReport -Time 08:00
```

Windows generate + local publish after 08:00:

```powershell
scripts/register_daily_task.ps1 -TaskName DanXiDailyPublish -Time 08:00 -EnablePost
```

Linux/macOS cron:

```
0 8 * * * cd /path/to/danxi-daily && /usr/bin/python3 scripts/generate_daily.py --hours 24 --top 12 >> outputs/cron.log 2>&1
```

## Recommended Safety

- Confirm WebVPN secrets with one dry-run before enabling posting:
  Actions tab → DanXi Daily Auto Post → Run workflow → `dry_run=true`
- Do not keep re-dispatching after `INVALID_ACCOUNT` / `还剩N次机会`
- Monitor the Actions tab and any auto-opened failure issues
