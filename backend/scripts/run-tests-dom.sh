#!/usr/bin/env bash
# DOM 契约测试运行器：tests/dom/ 逐个文件独立进程跑（单文件峰值 ~1GB 内存）。
# 每文件之间自动等待内存回落；任一文件失败不中断后续文件，全部跑完汇总。
# 环境变量：
#   TEST_VMEM_LIMIT_KB  虚拟内存上限 KB（默认 3000000=3GB）
set -euo pipefail
cd "$(dirname "$0")/.."
ulimit -v "${TEST_VMEM_LIMIT_KB:-3000000}"
fail=0
for f in tests/dom/test_*_platform_dom.py; do
  echo "===== $f ====="
  if ./.venv/bin/python -m pytest -q --no-header -p no:cacheprovider "$f"; then
    :
  else
    echo "!!! FAILED: $f"
    fail=1
  fi
  sleep 2  # 让内存回落再跑下一个
done
exit $fail
