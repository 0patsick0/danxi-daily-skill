# Troubleshooting

## 1) All endpoints failed

Symptoms:
- Runtime error showing both API endpoints failed.

Checks:
- Verify network connectivity.
- Verify DANXI_BASE_URLS values.
- Try with DANXI_API_TOKEN if endpoint needs authorization.

## 2) Summary always shows [fallback]

Possible causes:
- No OPENAI_API_KEY or ANTHROPIC_API_KEY
- API key invalid or quota exhausted
- LLM request timeout

Actions:
- Set one valid API key.
- Increase --timeout.

## 3) Post mode fails immediately

Cause:
- Missing --post-endpoint or DANXI_POST_TOKEN.
- post endpoint host is not in allowlist.

Fix:
- Provide --post-endpoint and DANXI_POST_TOKEN.
- Update DANXI_ALLOWED_POST_HOSTS or use --unsafe-allow-any-host only in trusted local dev.

## 4) Python import error when running script

Cause:
- Running outside project root.

Fix:
- cd to project root and run:
  python scripts/generate_daily.py

## 5) Token seems ignored

Cause:
- Token passed by CLI argument (unsupported).

Fix:
- Put token in environment variable:
  - DANXI_API_TOKEN
  - DANXI_POST_TOKEN

## 6) Empty report

Cause:
- No recent holes in selected time window or division.

Fix:
- Increase --hours and/or remove --division-id filter.

## 7) GitHub Actions "didn't trigger" / daily post missing

This is usually two separate problems. Check the Actions tab for the
calendar day in UTC+8 before changing cron minutes.

### A) No run at all around 20:17 CST

Cause:
- GitHub native `schedule:` is best-effort. This repo has seen 9+ hour
  delays and complete skips. Editing the cron minute does not fix it.

Fix:
- Use `scripts/dispatch_daily.ps1` / Windows Task Scheduler
  (`-DispatchGitHub`) or cron-job.org to POST `workflow_dispatch`.
- See docs/scheduling.md.

### B) A run exists but failed

2026-09-01 example: `workflow_dispatch` at 00:47 CST failed with:

- forum API `{"exp":"token expired"}`
- then WebVPN re-login: `INVALID_ACCOUNT [local]:用户名或密码错误；还剩4次机会`

Cause:
- `DANXI_API_TOKEN` secret is stale.
- CAS login failed and the old code fell back to WebVPN *local* login,
  which is a different account database and burns password attempts.

Fix:
1. Stop retrying. A wrong password can lock the campus UIS account.
2. Update `DANXI_WEBVPN_USERNAME` / `DANXI_WEBVPN_PASSWORD` repo secrets
   to the current UIS credentials.
3. Optionally refresh `DANXI_API_TOKEN`.
4. Run once with `dry_run=true`, then a real dispatch.

CAS is now the only default WebVPN auth path. Local login is opt-in via
`DANXI_WEBVPN_AUTH=local`.
