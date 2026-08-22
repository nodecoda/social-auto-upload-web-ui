#!/usr/bin/env bash
# 内存受限的 pytest 运行器（本机 3.7GB 内存，防 OOM 拖垮整机）。
#
# 逐文件跑主测试集（每个文件独立进程，内存不叠加），并行 P=3（可调 TEST_PARALLEL），
# 聚合输出统计。这是本机唯一稳定的全量跑法：单进程一次跑 3391 个测试会在 pytest
# 收尾阶段因虚拟内存上限(3GB) OOM，丢失统计；逐文件并行稳定且快(~40-60s)。
#
# 用法：
#   scripts/run-tests.sh                     # 主测试集（tests/test_*.py 逐文件并行）
#   scripts/run-tests.sh tests/test_xxx.py   # 指定文件（透传 pytest，单进程）
#   scripts/run-tests.sh -k 关键字           # 关键字过滤（透传）
#   scripts/run-tests.sh tests/primitives/   # 目录（单进程内跑，非逐文件）
#
# 环境变量：
#   TEST_VMEM_LIMIT_KB  虚拟内存上限 KB（默认 3000000=3GB，超限只杀测试进程）
#   TEST_PARALLEL       并行进程数（默认 3；FAIL_FAST=1 或 COVERAGE=1 时强制 1）
#   FAIL_FAST=1         任一文件失败立即停止
#   COVERAGE=1          逐文件带 coverage 统计（聚合 xml，供 CI 复现；强制串行）
set -uo pipefail
cd "$(dirname "$0")/.."

if [ "$#" -gt 0 ]; then
  # 显式传参：保持 pytest 语义（单进程）
  ulimit -v "${TEST_VMEM_LIMIT_KB:-3000000}"
  exec ./.venv/bin/python -m pytest -q --no-header -p no:cacheprovider "$@"
fi

# coverage 聚合有文件写竞态、FAIL_FAST 并行下无法即时中断 → 两者强制串行
PARALLEL="${TEST_PARALLEL:-3}"
[ "${COVERAGE:-0}" = "1" ] && PARALLEL=1
[ "${FAIL_FAST:-0}" = "1" ] && PARALLEL=1

OUTDIR=$(mktemp -d)
trap 'rm -rf "$OUTDIR"' EXIT

run_one() {
  f="$1"
  ulimit -v "${TEST_VMEM_LIMIT_KB:-3000000}"
  if [ "${COVERAGE:-0}" = "1" ]; then
    out=$(./.venv/bin/python -m pytest "$f" -q --no-header -p no:cacheprovider \
          --cov=. --cov-config=.coveragerc --cov-report=term-missing:skip-covered --cov-append 2>&1 || true)
  else
    out=$(./.venv/bin/python -m pytest "$f" -q --no-header -p no:cacheprovider 2>&1 || true)
  fi
  summary=$(echo "$out" | grep -E "^[0-9]+ (passed|failed)" | tail -1 || true)
  p=$(echo "$summary" | grep -oE "[0-9]+ passed" | grep -oE "[0-9]+" || echo 0)
  fa=$(echo "$summary" | grep -oE "[0-9]+ failed" | grep -oE "[0-9]+" || echo 0)
  e=$(echo "$summary" | grep -oE "[0-9]+ error" | grep -oE "[0-9]+" || echo 0)
  sk=$(echo "$summary" | grep -oE "[0-9]+ skipped" | grep -oE "[0-9]+" || echo 0)
  key=$(echo "$f" | tr '/' '_')
  echo "$p $fa $e $sk" > "$OUTDIR/$key.result"
  if [ "$fa" -gt 0 ] || [ "$e" -gt 0 ]; then
    echo "$f" >> "$OUTDIR/failed.list"
    {
      echo "--- $f 失败详情 ---"
      echo "$out" | tail -25
    } >> "$OUTDIR/failures.log"
  fi
}
export -f run_one
export OUTDIR

if [ "${COVERAGE:-0}" = "1" ]; then
  rm -f .coverage
fi

FILES=$(find tests -name "test_*.py" -not -path "*/dom/*" | sort)
echo "$FILES" | xargs -P "$PARALLEL" -I{} bash -c 'run_one "$@"' _ {}

# ── 聚合 ──────────────────────────────────────────────────────────────────
PASS=0; FAIL=0; ERR=0; SKIP=0
for r in "$OUTDIR"/*.result; do
  read -r p fa e sk < "$r"
  PASS=$((PASS+p)); FAIL=$((FAIL+fa)); ERR=$((ERR+e)); SKIP=$((SKIP+sk))
done

if [ -f "$OUTDIR/failed.list" ]; then
  printf "失败文件:\n"
  sort -u "$OUTDIR/failed.list"
  cat "$OUTDIR/failures.log"
fi

echo
echo "════════ 汇总: passed=$PASS failed=$FAIL errors=$ERR skipped=$SKIP ════════"
if [ -f "$OUTDIR/failed.list" ]; then
  exit 1
fi
if [ "${COVERAGE:-0}" = "1" ]; then
  echo "coverage 统计已写入 .coverage（可用 pytest --cov-report=term 查看）"
fi
