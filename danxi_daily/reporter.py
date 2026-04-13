from __future__ import annotations

from datetime import datetime, timezone

from .models import RankedPost


def build_daily_markdown(posts: list[RankedPost], title_prefix: str = "DanXi Daily") -> str:
    now = datetime.now(timezone.utc)
    date_label = now.strftime("%Y-%m-%d")
    lines: list[str] = [
        f"# {title_prefix} | {date_label}",
        "",
        f"Generated at: {now.isoformat().replace('+00:00', 'Z')}",
        "",
        "## Hot Posts",
        "",
    ]

    if not posts:
        lines.extend([
            "No posts were fetched in this run.",
            "",
            "## Notes",
            "- Check API token or endpoint availability.",
        ])
        return "\n".join(lines) + "\n"

    for idx, post in enumerate(posts, start=1):
        lines.extend(
            [
                f"### {idx}. Hole #{post.hole_id}",
                f"- Hot score: {post.hot_score:.3f}",
                f"- Metrics: views={post.view}, replies={post.reply}, likes={post.like_sum}",
                f"- Excerpt: {post.excerpt or 'N/A'}",
                f"- Summary: {post.summary or 'N/A'}",
                "",
            ]
        )

    lines.extend(
        [
            "## Disclaimer",
            "- This report is generated automatically and should be reviewed before posting.",
        ]
    )

    return "\n".join(lines) + "\n"
