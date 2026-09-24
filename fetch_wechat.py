"""抓取公众号文章。

优先走 WeRSS API（需要环境变量 WERSS_AK / WERSS_SK）；
未配置密钥时自动退回公开的 all.rss，保证没有密钥也能正常构建。

密钥不要写进代码或提交到仓库，本地可放在 .env（见 .gitignore），
CI 里放在 GitHub 仓库的 Secrets。
"""

import json
import os
import time
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import scraper

WECHAT_FILE = scraper.BASE / "data" / "wechat.json"

# WeRSS 服务
API_URL = os.environ.get(
    "WERSS_API", "https://werss.lilystudio.space/api/v1/wx/articles"
)
RSS_URL = "https://werss.lilystudio.space/feed/all.rss"
ACCESS_KEY = os.environ.get("WERSS_AK", "")
SECRET_KEY = os.environ.get("WERSS_SK", "")

# 最多保留最近多少条公众号文章（0 表示不限制）
WECHAT_LIMIT = int(os.environ.get("WECHAT_LIMIT", "60"))
PAGE_SIZE = 100


def _fmt_time(ts):
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
    except (ValueError, OSError, TypeError):
        return ""


def fetch_via_api():
    """按发布时间倒序分页拉取，取最近 WECHAT_LIMIT 条。"""
    headers = {
        "Authorization": f"AK-SK {ACCESS_KEY}:{SECRET_KEY}",
        "User-Agent": scraper.HEADERS["User-Agent"],
    }
    out = []
    offset = 0
    while WECHAT_LIMIT <= 0 or len(out) < WECHAT_LIMIT:
        params = urlencode({"offset": offset, "limit": PAGE_SIZE})
        req = Request(f"{API_URL}?{params}", headers=headers)
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8")).get("data") or {}
        batch = data.get("list") or []
        if not batch:
            break
        for a in batch:
            out.append(
                {
                    "title": (a.get("title") or "").strip(),
                    "url": a.get("url") or "",
                    "date": _fmt_time(a.get("publish_time")),
                    "organizer": a.get("mp_name") or "公众号",
                    "summary": (a.get("description") or "").strip(),
                }
            )
        offset += PAGE_SIZE
        if offset >= (data.get("total") or 0):
            break
        time.sleep(0.2)
    return out[:WECHAT_LIMIT] if WECHAT_LIMIT > 0 else out


def fetch_via_rss():
    """退回方案：公开 RSS（只有最近约 30 条）。"""
    text = scraper.fetch(RSS_URL)
    return [
        {
            "title": raw["title"],
            "url": raw["url"],
            "date": raw["date"],
            "organizer": "公众号",
            "summary": "",
        }
        for raw in scraper.parse_rss(text)
    ]


def to_notice(raw):
    grades, tags = scraper.classify(raw["title"], "")
    return {
        "id": 0,
        "title": raw["title"],
        "source": "公众号",
        "organizer": raw["organizer"],
        "type": scraper.classify_type(raw["title"]),
        "date": raw["date"],
        "deadline": "",
        "grades": grades,
        "tags": tags,
        "url": raw["url"],
        "summary": raw["summary"],
    }


def collect():
    if ACCESS_KEY and SECRET_KEY:
        print("使用 WeRSS API 抓取公众号…")
        return fetch_via_api()
    print("未配置 WERSS_AK / WERSS_SK，退回公开 RSS…")
    return fetch_via_rss()


def main():
    raw_items = collect()

    if not raw_items:
        print("公众号未获取到任何内容，保留原有数据，不覆盖。")
        return

    notices = [to_notice(r) for r in raw_items if r["title"] and r["url"]]

    # 按链接去重
    seen = set()
    deduped = []
    for n in notices:
        if n["url"] in seen:
            continue
        seen.add(n["url"])
        deduped.append(n)

    keep, dropped = scraper.filter_expired(deduped)
    keep.sort(key=lambda n: n["date"], reverse=True)
    for i, n in enumerate(keep, start=1):
        n["id"] = i

    scraper.write_json(WECHAT_FILE, keep)
    print(
        f"公众号抓取完成：{len(keep)} 条（过滤 {len(dropped)} 条），已写入 {WECHAT_FILE}"
    )


if __name__ == "__main__":
    main()
