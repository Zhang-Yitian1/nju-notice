import json
import shutil
from datetime import datetime
from pathlib import Path

import scraper

BASE = Path(__file__).parent
DATA_FILE = BASE / "data" / "notices.json"
TEMPLATE = BASE / "templates" / "index.html"
CSS = BASE / "static" / "style.css"
OUT_DIR = BASE / "docs"


def main():
    scraper.scrape()

    notices = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    template = TEMPLATE.read_text(encoding="utf-8")
    updated = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = template.replace(
        "__NOTICES__", json.dumps(notices, ensure_ascii=False)
    ).replace("__UPDATED__", updated)

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")
    shutil.copyfile(CSS, OUT_DIR / "style.css")
    (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")

    print(f"静态站点已生成：{OUT_DIR / 'index.html'}（{len(notices)} 条）")


if __name__ == "__main__":
    main()
