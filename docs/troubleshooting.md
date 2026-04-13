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

## 6) Token seems ignored

Cause:
- Token passed by CLI argument (unsupported).

Fix:
- Put token in environment variable:
  - DANXI_API_TOKEN
  - DANXI_POST_TOKEN

## 5) Empty report

Cause:
- No recent holes in selected time window or division.

Fix:
- Increase --hours and/or remove --division-id filter.
