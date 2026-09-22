import json
from pathlib import Path

BASE = Path(__file__).parent
DATA_DIR = BASE / "data"
NOTICES_FILE = DATA_DIR / "notices.json"
WECHAT_FILE = DATA_DIR / "wechat.json"


def _load(path):
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def load_all():
    """合并校内源（notices.json）与公众号（wechat.json），去重排序。"""
    items = _load(NOTICES_FILE) + _load(WECHAT_FILE)
    seen = set()
    merged = []
    for n in items:
        url = n.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        merged.append(n)
    merged.sort(key=lambda n: n.get("date", ""), reverse=True)
    for i, n in enumerate(merged, start=1):
        n["id"] = i
    return merged
