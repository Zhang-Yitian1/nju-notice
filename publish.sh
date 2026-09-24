#!/bin/sh
# 抓取公众号 → 提交 → 推送。推送 GitHub 需要梯子。
# 现在公众号也会在 CI 里自动更新，本脚本仅用于本地手动跑。
set -e
cd "$(dirname "$0")"

# 本地密钥（可选，切勿提交）：把下面两行写进同目录的 .env
#   WERSS_AK=你的AccessKey
#   WERSS_SK=你的SecretKey
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

python3 fetch_wechat.py

git add data/wechat.json
if git diff --cached --quiet; then
  echo "公众号数据无变化，无需推送"
  exit 0
fi

git commit -m "更新公众号数据 $(date '+%Y-%m-%d %H:%M')"

# 推送：先直连，失败再走本地代理（端口可用 PROXY_PORT 覆盖，默认 9674）
PROXY="http://127.0.0.1:${PROXY_PORT:-9674}"
if git push; then
  :
elif git -c http.proxy="$PROXY" -c https.proxy="$PROXY" push; then
  :
else
  echo "推送失败：请确认梯子已开启（当前代理 ${PROXY}）"
  exit 1
fi
echo "已推送，GitHub 会自动重新构建网站（约 2 分钟）"
