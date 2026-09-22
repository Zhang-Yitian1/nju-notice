#!/bin/sh
# 抓取公众号 → 提交 → 推送。推送 GitHub 需要梯子。
set -e
cd "$(dirname "$0")"

python3 fetch_wechat.py

git add data/wechat.json
if git diff --cached --quiet; then
  echo "公众号数据无变化，无需推送"
  exit 0
fi

git commit -m "更新公众号数据 $(date '+%Y-%m-%d %H:%M')"
git push
echo "已推送，GitHub 会自动重新构建网站（约 2 分钟）"
