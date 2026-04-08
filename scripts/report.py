#!/usr/bin/env python3
"""输出当前组合报告。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STRATEGY_PATH = ROOT / "data" / "strategy.yaml"
PORTFOLIO_PATH = ROOT / "data" / "portfolio.yaml"


def load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="查看组合当前状态")
    parser.add_argument("--strategy", type=Path, default=STRATEGY_PATH)
    parser.add_argument("--portfolio", type=Path, default=PORTFOLIO_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    strategy = load_yaml(args.strategy)
    portfolio = load_yaml(args.portfolio)

    targets = strategy.get("targets", {})
    positions = {
        str(p.get("ticker", "")).upper(): p
        for p in portfolio.get("positions", [])
        if p.get("ticker")
    }

    cash = float(portfolio.get("cash_usd", 0.0) or 0.0)
    total_positions = 0.0
    for t in targets:
        p = positions.get(t, {})
        shares = float(p.get("shares", 0.0) or 0.0)
        price = float(p.get("last_price", 0.0) or 0.0)
        total_positions += shares * price

    total = total_positions + cash

    print("=" * 86)
    print("投资组合报告")
    print("=" * 86)
    print(f"日期: {portfolio.get('as_of', 'N/A')}")
    print(f"当前总市值(含现金): ${total:.2f}")
    print(f"现金: ${cash:.2f}\n")
    print("Ticker | 市值(USD) | 当前占比 | 目标占比 | 偏差")
    print("-" * 86)

    for t, target in targets.items():
        p = positions.get(t, {})
        shares = float(p.get("shares", 0.0) or 0.0)
        price = float(p.get("last_price", 0.0) or 0.0)
        value = shares * price
        current_w = (value / total) if total > 0 else 0.0
        deviation = current_w - float(target)
        print(
            f"{t:5s} | ${value:9.2f} | {current_w*100:7.2f}% | {float(target)*100:7.2f}% | {deviation*100:+7.2f}%"
        )


if __name__ == "__main__":
    main()
