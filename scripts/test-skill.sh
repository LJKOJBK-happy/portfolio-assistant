#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
TMP_DIR="$(mktemp -d)"
WORKSPACE="$TMP_DIR/.portfolio-assistant"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

echo "[1/3] 初始化示例工作区"
"$PYTHON_BIN" "$SCRIPT_DIR/portfolio_assistant.py" init \
  --workspace "$WORKSPACE" \
  --base-currency USD \
  --cash 1500 \
  --cash-currency USD \
  --rebalance-level 1 \
  --rebalance-override '股票/海外=3' \
  --group '股票/海外/美国市场/S&P 500=VOO,CSPX' \
  --group '股票/海外/美国市场/纳斯达克 100=QQQM,CSNDX' \
  --group '股票/海外/日本市场=EWJ' \
  --group '商品/大宗商品=ICOM,PDBC' \
  --target '股票/海外/美国市场/S&P 500=0.20' \
  --target '股票/海外/美国市场/纳斯达克 100=0.20' \
  --target '股票/海外/日本市场=0.05' \
  --target 'TLT=0.10' \
  --target 'IDTL=0.15' \
  --target 'IDTP=0.10' \
  --target 'BOXX=0.05' \
  --target 'GLDM=0.05' \
  --target '商品/大宗商品=0.10' \
  --holding 'VOO,4,500,520' \
  --holding 'CSPX,1,700,706.3' \
  --holding 'QQQM,6,180,190' \
  --holding 'ICOM,10,19,20' \
  --holding 'TLT,5,92,90' \
  --json

echo "[2/3] 输出组合报告"
"$PYTHON_BIN" "$SCRIPT_DIR/portfolio_assistant.py" report \
  --workspace "$WORKSPACE" \
  --skip-refresh \
  --json

echo "[3/3] 输出补仓建议"
"$PYTHON_BIN" "$SCRIPT_DIR/portfolio_assistant.py" rebalance \
  --workspace "$WORKSPACE" \
  --contribution 5000 \
  --contribution-currency USD \
  --skip-refresh \
  --json
