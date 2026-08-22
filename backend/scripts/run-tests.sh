#!/usr/bin/env bash
# 内存受限的 pytest 运行器（本机 3.7GB 内存，防 OOM 拖垮整机）。
#
# 默认逐文件跑主测试集（每个文件独立进程，内存不叠加），聚合输出统计。
# 这是本机唯一稳定的全量跑法：单进程一次跑 3391 个测试会在 pytest 收尾
# 阶段因虚拟内存上限(3GB) OOM，丢失统计；逐文件跑稳定且更快(~1-2 分钟)。
#
# 用法：
#   scripts/run-tests.sh                     # 主测试集（tests/test_*.py 逐文件）
#   scripts/run-tests.sh tests/test_xxx.py   # 指定文件（透传 pytest）
#   scripts/run-tests.sh -k 关键字           # 关键字过滤（透传）
#   scripts/run-tests.sh tests/primitives/   # 目录（单进程内跑，非逐文件）
#
# 环境变量：
#   TEST_VMEM_LIMIT_KB  虚拟内存上限 KB（默认 3000000=3GB，超限只杀测试进程）
#   FAIL_FAST=1         任一文件失败立即停止
#   COVERAGE=1          逐文件跑且带 coverage 统计（聚合 xml，供 CI 复现）
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "$#" -gt 0 ]; then
  # 显式传参：保持 pytest 语义（单进程）
  ulimit -v "${TEST_VMEM_LIMIT_KB:-3000000}"
  exec ./.venv/bin/python -m pytest -q --no-header -p no:cacheprovider "$@"
fi

# ── 逐文件聚合跑（默认） ────────────────────────────────────────────────
PASS=0; FAIL=0; ERR=0; SKIP=0
FAILED_FILES=()
COVERAGE_FLAGS=()
if [ "${COVERAGE:-0}" = "1" ]; then
  COVERAGE_FLAGS=(--cov=. --cov-config=.coveragerc --cov-report=term-missing:skip-covered --cov-append)
  rm -f .coverage
fi

while IFS= read -r f; do
  ulimit -v "${TEST_VMEM_LIMIT_KB:-3000000}"
  if [ "${COVERAGE:-0}" = "1" ]; then
    out=$(./.venv/bin/python -m pytest "$f" -q --no-header -p no:cacheprovider "${COVERAGE_FLAGS[@]}" 2>&1 || true)
  else
    out=$(./.venv/bin/python -m pytest "$f" -q --no-header -p no:cacheprovider 2>&1 || true)
  fi
  summary=$(echo "$out" | grep -E "^[0-9]+ (passed|failed)" | tail -1 || true)
  p=$(echo "$summary" | grep -oE "[0-9]+ passed" | grep -oE "[0-9]+" || echo 0)
  fa=$(echo "$summary" | grep -oE "[0-9]+ failed" | grep -oE "[0-9]+" || echo 0)
  e=$(echo "$summary" | grep -oE "[0-9]+ error" | grep -oE "[0-9]+" || echo 0)
  sk=$(echo "$summary" | grep -oE "[0-9]+ skipped" | grep -oE "[0-9]+" || echo 0)
  PASS=$((PASS+p)); FAIL=$((FAIL+fa)); ERR=$((ERR+e)); SKIP=$((SKIP+sk))
  printf "%-50s passed=%-4s failed=%-3s error=%-3s skipped=%-3s\n" "$f" "$p" "$fa" "$e" "$sk"
  if [ "$fa" -gt 0 ] || [ "$e" -gt 0 ]; then
    FAILED_FILES+=("$f")
    echo "--- $f 失败详情 ---"
    echo "$out" | tail -25
    if [ "${FAIL_FAST:-0}" = "1" ]; then
      echo "FAIL_FAST=1 已停止"
      exit 1
    fi
  fi
done < <(find tests -name "test_*.py" -not -path "*/dom/*" | sort)

echo
echo "════════ 汇总: passed=$PASS failed=$FAIL errors=$ERR skipped=$SKIP ════════"
if [ "${#FAILED_FILES[@]}" -gt 0 ]; then
  printf "失败文件: %s\n" "${FAILED_FILES[@]}"
  exit 1
fi
if [ "${COVERAGE:-0}" = "1" ]; then
  echo "coverage 统计已写入 .coverage（可用 pytest --cov-report=term 查看）"
fi
