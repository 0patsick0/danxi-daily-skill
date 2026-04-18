from __future__ import annotations

from datetime import datetime, timezone

from .models import RankedPost


def build_daily_markdown(
    posts: list[RankedPost],
    title_prefix: str = "旦夕热榜日报",
    github_repo: str = "https://github.com/0patsick0/danxi-daily-skill",
) -> str:
    now = datetime.now(timezone.utc)
    date_label = now.astimezone().strftime("%Y年%m月%d日")
    time_label = now.astimezone().strftime("%Y-%m-%d %H:%M")

    lines: list[str] = [
        f"# {title_prefix}｜{date_label}",
        "",
        f"> 数据整理时间：{time_label}",
        "",
        "## 今日热门话题",
        "",
    ]

    if not posts:
        lines.append("今天暂未抓取到符合条件的热点讨论。")
        return "\n".join(lines) + "\n"

    for idx, post in enumerate(posts, start=1):
        lines.append(
            f"{idx}. #{post.hole_id}"
            f"　热度 {post.hot_score:.1f}"
            f"　👀{post.view} 💬{post.reply} 👍{post.like_sum}"
        )

    lines.extend([
        "",
        f"🔗 {github_repo}",
    ])

    return "\n".join(lines) + "\n"
