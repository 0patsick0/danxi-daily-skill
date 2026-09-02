# Cloud clock (Cloudflare Worker)

Independent of this PC. Cloudflare cron POSTs `workflow_dispatch` to
GitHub Actions. Overlapping fires are safe (`--post-once-per-day`).

Cron (UTC):

- `17 12 * * *` = 20:17 CST
- `30 13 * * *` = 21:30 CST

## Deploy

1. Fine-grained GitHub PAT, this repo only, **Actions: Read and write**.
2. `npx wrangler login`
3. `npx wrangler secret put GITHUB_DISPATCH_TOKEN` (paste the PAT)
4. `npx wrangler deploy`

Manual poke: `npx wrangler dev` then GET the worker URL, or
`npx wrangler deployments list`.
