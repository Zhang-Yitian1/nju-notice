import json
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

BASE = Path(__file__).parent
DATA_FILE = BASE / "data" / "notices.json"

ACTIVITY_WORDS = (
    "活动", "大赛", "比赛", "竞赛", "报名", "招募", "征集", "讲座", "沙龙",
    "演出", "论坛", "分享会", "训练营", "夏令营", "志愿者", "开放日", "展览", "晚会",
)
DEADLINE_KEYWORDS = ("截止", "报名", "提交")
RETENTION_ACTIVITY = 30  # 活动：没有截止日时，发布超过这么多天就当作过期
RETENTION_NOTICE = 120  # 通知：发布超过这么多天清理

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NJUNoticeBot/0.1; personal learning project)"
}

SCRAPE_LOCK = threading.Lock()


def fetch(url):
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=20) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="ignore")


class WebplusParser(HTMLParser):
    """教务处（博达 webplus）：li.news 里有 分类 / 标题 / 日期。"""

    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.items = []
        self.cur = None
        self.in_cat = False
        self.in_meta = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = attrs.get("class", "").split()

        if tag == "li" and "news" in cls:
            self.cur = {"category": "", "title": "", "url": "", "date": ""}
            return
        if self.cur is None:
            return

        if tag == "div" and "lj" in cls:
            self.in_cat = True
        elif tag == "a" and attrs.get("title") and attrs.get("href"):
            self.cur["title"] = attrs["title"].strip()
            self.cur["url"] = urljoin(self.base_url, attrs["href"])
        elif tag == "span" and "news_meta" in cls:
            self.in_meta = True

    def handle_data(self, data):
        if self.cur is None:
            return
        if self.in_cat:
            self.cur["category"] += data.strip()
        elif self.in_meta:
            self.cur["date"] += data.strip()

    def handle_endtag(self, tag):
        if self.cur is None:
            return
        if tag == "div":
            self.in_cat = False
        elif tag == "span":
            self.in_meta = False
        elif tag == "li":
            if self.cur["title"]:
                self.items.append(self.cur)
            self.cur = None


class VsbParser(HTMLParser):
    """图书馆（VSB）：li 里有 <span>日期</span><a title=标题>。"""

    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.items = []
        self.cur = None
        self.in_span = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "li":
            self.cur = {"category": "", "title": "", "url": "", "date": ""}
        elif self.cur is not None and tag == "a" and attrs.get("title") and attrs.get("href"):
            self.cur["title"] = attrs["title"].replace("\u200b", "").strip()
            self.cur["url"] = urljoin(self.base_url, attrs["href"])
        elif self.cur is not None and tag == "span":
            self.in_span = True

    def handle_data(self, data):
        if self.cur is not None and self.in_span:
            self.cur["date"] += data.strip()

    def handle_endtag(self, tag):
        if tag == "span":
            self.in_span = False
        elif tag == "li" and self.cur is not None:
            if self.cur["title"]:
                self.cur["date"] = self.cur["date"].replace(".", "-")
                self.items.append(self.cur)
            self.cur = None


SOURCES = [
    {
        "name": "教务处",
        "parser": WebplusParser,
        "pages": [
            "https://jw.nju.edu.cn/ggtz/list.htm",
            "https://jw.nju.edu.cn/ggtz/list2.htm",
            "https://jw.nju.edu.cn/ggtz/list3.htm",
        ],
        "exclude": ["部分课程调整名额"],
    },
    {
        "name": "图书馆",
        "parser": VsbParser,
        "pages": [
            "https://lib.nju.edu.cn/xw/xwtz.htm",
            "https://lib.nju.edu.cn/xw/xwtz/34.htm",
        ],
        "exclude": ["【新闻】"],
    },
    {
        "name": "公众号",
        "type": "rss",
        "pages": ["https://werss.lilystudio.space/feed/all.rss"],
        "enrich": False,
    },
]


def classify(title, category):
    tags = [t for t in re.split(r"[,，、\s]+", category) if t]
    if "新生" in title or "2026级" in title:
        grades = ["2026"]
    elif "老生" in title:
        grades = ["2025", "2024", "2023"]
    else:
        grades = ["2026", "2025", "2024", "2023"]
    return grades, tags


def classify_type(title):
    return "活动" if any(w in title for w in ACTIVITY_WORDS) else "通知"


DATE_RE = re.compile(r"(?:(\d{4})\s*年)?\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")


def clean_text(html):
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(text))


def extract_deadline(text, publish_date):
    year = int(publish_date[:4]) if publish_date else date.today().year
    found = []
    for m in DATE_RE.finditer(text):
        y = int(m.group(1)) if m.group(1) else year
        try:
            dt = date(y, int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        before = text[max(0, m.start() - 12):m.start()]
        if any(k in before for k in DEADLINE_KEYWORDS):
            found.append(dt)
    if not found:
        return ""
    dt = max(found)
    pub = date.fromisoformat(publish_date) if publish_date else date.today()
    if dt < pub and (pub - dt).days > 180:
        dt = dt.replace(year=dt.year + 1)
    return dt.isoformat()


def enrich(url, publish_date):
    """打开详情页，抽取发布单位和截止日期。"""
    organizer, deadline = "", ""
    try:
        text = clean_text(fetch(url))
        m = re.search(r"发布者[:：]\s*([^\s，,。；;、]{2,20})", text)
        if m:
            organizer = m.group(1)
        deadline = extract_deadline(text, publish_date)
    except Exception:
        pass
    return organizer, deadline


def parse_rss(text):
    """解析 RSS 订阅源（公众号等）。"""
    items = []
    root = ET.fromstring(text)
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or it.findtext("guid") or "").strip()
        pub = it.findtext("pubDate") or ""
        d = ""
        if pub:
            try:
                d = parsedate_to_datetime(pub).strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                d = ""
        items.append(
            {"title": title, "url": link, "date": d, "category": ""}
        )
    return items


def scrape():
    if not SCRAPE_LOCK.acquire(blocking=False):
        print("已有抓取在进行，跳过本次")
        return 0
    try:
        return _scrape()
    finally:
        SCRAPE_LOCK.release()


def _scrape():
    seen = set()
    notices = []

    for source in SOURCES:
        print(f"[{source['name']}]")
        for url in source["pages"]:
            try:
                html = fetch(url)
            except Exception as e:
                print(f"  失败 {url} -> {e}")
                continue

            if source.get("type") == "rss":
                raw_items = parse_rss(html)
            else:
                parser = source["parser"](url)
                parser.feed(html)
                raw_items = parser.items

            added = 0
            for raw in raw_items:
                title = raw["title"]
                if not title or raw["url"] in seen:
                    continue
                if any(word in title for word in source.get("exclude", [])):
                    continue
                seen.add(raw["url"])
                grades, tags = classify(title, raw["category"])
                notices.append(
                    {
                        "id": 0,
                        "title": title,
                        "source": source["name"],
                        "organizer": source["name"],
                        "type": classify_type(title),
                        "date": raw["date"],
                        "deadline": "",
                        "grades": grades,
                        "tags": tags,
                        "url": raw["url"],
                        "summary": "",
                        "_enrich": source.get("enrich", True),
                    }
                )
                added += 1
            print(f"  {url} -> 新增 {added} 条")
            time.sleep(0.5)

    print(f"\n抽取正文信息（发布单位 / 截止日期）…")
    for n in notices:
        if not n.pop("_enrich", True):
            continue
        organizer, deadline = enrich(n["url"], n["date"])
        if organizer:
            n["organizer"] = organizer
        n["deadline"] = deadline

    today = date.today()
    keep = []
    dropped = []
    for n in notices:
        if n["type"] == "活动":
            expired = (
                n["deadline"] and date.fromisoformat(n["deadline"]) < today
            ) or n["date"] < (today - timedelta(days=RETENTION_ACTIVITY)).isoformat()
        else:
            expired = n["date"] < (
                today - timedelta(days=RETENTION_NOTICE)
            ).isoformat()
        if expired:
            dropped.append(n)
        else:
            keep.append(n)

    print(f"过期清理：删除 {len(dropped)} 条")
    for n in dropped[:10]:
        print(f"  - [{n['type']}] {n['title'][:30]}（截止 {n['deadline'] or n['date']}）")

    keep.sort(key=lambda n: n["date"], reverse=True)
    for i, n in enumerate(keep, start=1):
        n["id"] = i

    tmp = DATA_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(keep, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DATA_FILE)
    print(f"\n抓取完成，共 {len(keep)} 条，已写入 {DATA_FILE}")
    return len(keep)


def main():
    scrape()


if __name__ == "__main__":
    main()
