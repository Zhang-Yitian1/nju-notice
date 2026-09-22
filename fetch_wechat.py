import scraper

RSS_URL = "https://werss.lilystudio.space/feed/all.rss"
WECHAT_FILE = scraper.BASE / "data" / "wechat.json"


def main():
    text = scraper.fetch(RSS_URL)
    raw_items = scraper.parse_rss(text)

    notices = []
    for raw in raw_items:
        title = raw["title"]
        if not title:
            continue
        grades, tags = scraper.classify(title, raw["category"])
        notices.append(
            {
                "id": 0,
                "title": title,
                "source": "公众号",
                "organizer": "公众号",
                "type": scraper.classify_type(title),
                "date": raw["date"],
                "deadline": "",
                "grades": grades,
                "tags": tags,
                "url": raw["url"],
                "summary": "",
            }
        )

    keep, dropped = scraper.filter_expired(notices)
    keep.sort(key=lambda n: n["date"], reverse=True)
    for i, n in enumerate(keep, start=1):
        n["id"] = i

    scraper.write_json(WECHAT_FILE, keep)
    print(f"公众号抓取完成：{len(keep)} 条（过滤 {len(dropped)} 条），已写入 {WECHAT_FILE}")


if __name__ == "__main__":
    main()
