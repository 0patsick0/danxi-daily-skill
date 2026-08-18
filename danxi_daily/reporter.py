from __future__ import annotations

from datetime import date, datetime, timezone

from .models import RankedPost

SHOP_AD_START_DATE = date(2026, 8, 18)


def build_daily_markdown(
    posts: list[RankedPost],
    title_prefix: str = "旦夕热榜日报",
    github_repo: str = "https://github.com/0patsick0/danxi-daily-skill",
    shop_url: str = "https://pay.ldxp.cn/shop/Q14UBAR8",
    shop_ad_interval_days: int = 5,
) -> str:
    now = datetime.now(timezone.utc)
    local_now = now.astimezone()
    date_label = local_now.strftime("%Y年%m月%d日")
    time_label = local_now.strftime("%Y-%m-%d %H:%M")
    show_shop_ad = (
        shop_ad_interval_days > 0
        and (local_now.date() - SHOP_AD_START_DATE).days % shop_ad_interval_days == 0
    )
    shop_ad = f"ai小店:[{shop_url}]" if show_shop_ad else None
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
        if shop_ad:
            lines.append(shop_ad)
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
    if shop_ad:
        lines.append(shop_ad)

    return "\n".join(lines) + "\n"
