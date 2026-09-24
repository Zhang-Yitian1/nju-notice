#!/bin/sh
# 抓取公众号 → 提交 → 推送。推送 GitHub 需要梯子。
# 现在由本地 launchd 定时任务自动调用（见 ~/Library/LaunchAgents）。
set -e
cd "$(dirname "$0")"

# 本地密钥（可选，切勿提交）：把 WERSS_AK / WERSS_SK 写进同目录的 .env
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

python3 fetch_wechat.py

git add data/wechat.json
if git diff --cached --quiet; then
  echo "公众号数据无变化"
else
  git commit -m "更新公众号数据 $(date '+%Y-%m-%d %H:%M')"
fi

# 推送：优先走本地代理（直连 GitHub 一般不通），不行再试直连。
# 每次都尝试推送，这样上次没推成的提交也能补上。
PROXY="http://127.0.0.1:${PROXY_PORT:-9674}"
if git -c http.proxy="$PROXY" -c https.proxy="$PROXY" push; then
  :
elif git push; then
  :
else
  echo "推送失败：请确认梯子已开启（当前代理 ${PROXY}）"
  exit 1
fi
echo "已推送，GitHub 会自动重新构建网站（约 2 分钟）"
