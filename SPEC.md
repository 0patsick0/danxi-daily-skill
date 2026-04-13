# DanXi Daily Skill Specification

## Goal

Generate a daily DanXi forum digest that can be reviewed and posted quickly.

## Scope

In scope:
- Fetch recent holes from DanXi-compatible endpoints.
- Compute hotness ranking.
- Generate concise summaries.
- Render publish-ready Markdown.
- Optional posting to a configured endpoint.

Out of scope:
- Automatic posting without explicit opt-in.
- Forum-specific private API reverse engineering.

## Architecture

Pipeline:
1. Fetch holes with endpoint fallback.
2. Enrich floors for top candidates (best effort).
3. Rank posts by weighted score.
4. Summarize each ranked post.
5. Render markdown report.
6. Optionally post report.

## Ranking Formula

hot_score =
- view * 0.03
- reply * 1.6
- likes * 2.4
- recency_factor * 3.2

recency_factor uses exponential decay with 12h half-life.

## Failure Handling

- API fallback to secondary endpoint.
- Summarization fallback to extractive summary.
- Post mode hard-fails if token is missing.
- Dry-run mode always available.

## Outputs

- outputs/holes.raw.json
- outputs/ranked.json
- outputs/daily.md

## Security

- No hardcoded tokens in code.
- Secrets loaded only from env.
- Post operation requires explicit --post.

## Extensibility

- Add provider adapters for more LLM services.
- Add richer ranking factors (engagement velocity, tag weights).
- Add retry queue for failed posting.
