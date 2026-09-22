import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import scraper
import store

BASE = Path(__file__).parent
DATA_FILE = BASE / "data" / "notices.json"
WECHAT_FILE = BASE / "data" / "wechat.json"
CSS_FILE = BASE / "static" / "style.css"

GRADES = ["全部", "2026", "2025", "2024", "2023"]

TYPE_CLASS = {"活动": "activity", "通知": "notice"}

REFRESH_MINUTES = int(os.environ.get("REFRESH_MINUTES", "30"))


def load_notices():
    return store.load_all()


def data_mtime():
    times = [f.stat().st_mtime for f in (DATA_FILE, WECHAT_FILE) if f.exists()]
    return max(times) if times else None


def humanize(ts):
    if not ts:
        return "未知"
    mins = int((time.time() - ts) // 60)
    if mins < 1:
        return "刚刚"
    if mins < 60:
        return f"{mins} 分钟前"
    hours = mins // 60
    if hours < 24:
        return f"{hours} 小时前"
    return f"{hours // 24} 天前"


def render_index(grade, refreshing=False):
    notices = load_notices()
    if grade and grade != "全部":
        notices = [n for n in notices if grade in n["grades"]]
    notices.sort(key=lambda n: n["date"], reverse=True)

    filter_links = ""
    for g in GRADES:
        active = "active" if g == grade else ""
        filter_links += f'<a class="{active}" href="/?grade={g}">{g}</a>'

    if notices:
        items = ""
        for n in notices:
            tags = " ".join("#" + t for t in n["tags"])
            ntype = n.get("type", "通知")
            type_class = TYPE_CLASS.get(ntype, "notice")
            deadline = (
                f'<span class="deadline">截止 {n["deadline"]}</span>'
                if n.get("deadline")
                else ""
            )
            organizer = n.get("organizer") or n["source"]
            items += f"""
            <li class="notice">
              <div class="meta">
                <span class="badge {type_class}">{ntype}</span>
                {n['date']} · {organizer}
              </div>
              <a class="title" href="{n['url']}" target="_blank">{n['title']}</a>
              <div class="tags">{tags}{deadline}</div>
            </li>"""
        body = f"<ul>{items}</ul>"
    else:
        body = '<div class="empty">这个年级暂时没有通知</div>'

    updated = data_mtime()
    if refreshing:
        banner = '<div class="banner">正在更新数据，40 秒后自动刷新…</div>'
        meta_refresh = '<meta http-equiv="refresh" content="40">'
    else:
        banner = ""
        meta_refresh = ""

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {meta_refresh}
  <title>南大新生通知</title>
  <link rel="stylesheet" href="/static/style.css">
  <script>
    (function () {{
      var saved = localStorage.getItem("theme");
      var theme = saved || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      document.documentElement.dataset.theme = theme;
    }})();
  </script>
</head>
<body>
  <div class="header">
    <h1>南大新生通知</h1>
    <div class="actions">
      <a class="btn" href="/refresh">刷新</a>
      <button id="themeToggle">深色</button>
    </div>
  </div>
  <div class="sub">聚合校内通知与活动 · 按年级筛选 · 数据更新于 {humanize(updated)}</div>
  {banner}
  <div class="filters">{filter_links}</div>
  {body}
  <script>
    (function () {{
      var btn = document.getElementById("themeToggle");
      function refresh() {{
        btn.textContent = document.documentElement.dataset.theme === "dark" ? "浅色" : "深色";
      }}
      refresh();
      btn.addEventListener("click", function () {{
        var next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
        document.documentElement.dataset.theme = next;
        localStorage.setItem("theme", next);
        refresh();
      }});
    }})();
  </script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/static/style.css":
            content = CSS_FILE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.end_headers()
            self.wfile.write(content)
            return

        if parsed.path == "/refresh":
            threading.Thread(target=scraper.scrape, daemon=True).start()
            self.send_response(302)
            self.send_header("Location", "/?refreshing=1")
            self.end_headers()
            return

        if parsed.path == "/":
            query = parse_qs(parsed.query)
            grade = query.get("grade", ["全部"])[0]
            refreshing = query.get("refreshing", ["0"])[0] == "1"
            html = render_index(grade, refreshing).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html)
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, *args):
        pass


def auto_update():
    while True:
        try:
            scraper.scrape()
        except Exception as e:
            print(f"自动更新失败：{e}")
        time.sleep(REFRESH_MINUTES * 60)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"服务已启动：http://127.0.0.1:{port}")
    print(f"每 {REFRESH_MINUTES} 分钟自动更新一次 · 按 Ctrl+C 停止")
    threading.Thread(target=auto_update, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
