#!/usr/bin/env bash
# 重新生成 requirements.lock（国内源，针对 CI Python 3.12）
# 用法: bash scripts/refresh-deps-lock.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_DEFAULT_INDEX="${UV_DEFAULT_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
uv pip compile requirements.txt \
  --python-version 3.12 \
  --output-file requirements.lock \
  --no-annotate
echo "✓ requirements.lock 已更新 ($(grep -cE '==' requirements.lock) 个精确版本)"
