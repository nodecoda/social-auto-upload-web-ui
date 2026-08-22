#!/usr/bin/env bash
# 内存受限的 pytest 运行器（本机 3.7GB 内存，防 OOM 拖垮整机）。
# 用法：
#   scripts/run-tests.sh                 # 主测试集（排除 tests/dom/，逐个文件跑）
#   scripts/run-tests.sh tests/test_xxx.py   # 指定文件
#   scripts/run-tests-dom.sh             # DOM 契约测试（tests/dom/，逐个文件跑）
# 环境变量：
#   TEST_VMEM_LIMIT_KB  虚拟内存上限 KB（默认 3000000=3GB，超限只杀测试进程）
set -euo pipefail
cd "$(dirname "$0")/.."
ulimit -v "${TEST_VMEM_LIMIT_KB:-3000000}"
exec ./.venv/bin/python -m pytest -q --no-header -p no:cacheprovider --ignore=tests/dom "$@"
