# Cloud clock (Cloudflare Worker)

Independent of this PC. Cloudflare cron POSTs `workflow_dispatch` to
GitHub Actions. Overlapping fires are safe (`--post-once-per-day`).

Cron (UTC):

- `30 15 * * *` = 23:30 CST
- `40 15 * * *` = 23:40 CST

Deployed as `danxi-daily-clock` on account `msa689704@gmail.com`.

- URL: https://danxi-daily-clock.msa689704.workers.dev (HTTP is auth-gated; cron does not use HTTP)
- Secret: `GITHUB_DISPATCH_TOKEN`
- Next fires: 23:30 and 23:40 Asia/Shanghai

To redeploy after code changes:

```
npx wrangler deploy
```
