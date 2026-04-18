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
        f"# 🌟 {title_prefix}｜{date_label}",
        "",
        f"> 🕒 数据整理时间：{time_label}",
        "",
        "## 🔥 今日热门话题",
        "",
    ]

    if not posts:
        lines.extend([
            "今天暂未抓取到符合条件的热点讨论，建议稍后再看。",
            "",
            "## 📮 结语",
            "欢迎持续关注，我们会在下一次推送里带来新的校园热点。",
            "",
            f"🔗 开源仓库：{github_repo}",
        ])
        return "\n".join(lines) + "\n"

    for idx, post in enumerate(posts, start=1):
        excerpt_line = ""
        if post.excerpt and post.excerpt.strip():
            excerpt_line = f"- 📝 摘要：{post.excerpt}"

        entry = [
            f"### No.{idx} #{post.hole_id}",
            f"- 🔥 热度指数：{post.hot_score:.2f}",
            f"- 👀 浏览：{post.view} ｜ 💬 回复：{post.reply} ｜ 👍 点赞：{post.like_sum}",
        ]
        if excerpt_line:
            entry.append(excerpt_line)
        entry.append("")
        lines.extend(entry)

    lines.extend(
        [
            "---",
            "",
            "## 📮 结语",
            "以上就是今天的旦夕热点，欢迎在评论区分享你的看法。",
            "",
            f"🔗 开源仓库：{github_repo}",
        ]
    )

    return "\n".join(lines) + "\n"
