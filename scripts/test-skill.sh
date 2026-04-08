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
  --cash 1500 \
  --holding 'VOO,4,500,520' \
  --holding 'QQQM,6,180,190' \
  --holding 'TLT,5,92,90' \
  --json

echo "[2/3] 输出组合报告"
"$PYTHON_BIN" "$SCRIPT_DIR/portfolio_assistant.py" report \
  --workspace "$WORKSPACE" \
  --json

echo "[3/3] 输出补仓建议"
"$PYTHON_BIN" "$SCRIPT_DIR/portfolio_assistant.py" rebalance \
  --workspace "$WORKSPACE" \
  --contribution 5000 \
  --json
