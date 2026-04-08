#!/usr/bin/env python3
"""Simple portfolio rebalance calculator.

Usage:
  python rebalance.py --strategy strategy.yaml --portfolio portfolio.yaml
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List



@dataclass
class Position:
    symbol: str
    market_value: float


def _load_yaml_module():
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError as exc:
        raise SystemExit("缺少依赖: PyYAML。请先执行 `pip install pyyaml`。") from exc
    return yaml


def load_yaml(path: Path) -> dict:
    yaml = _load_yaml_module()
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def extract_targets(strategy: dict) -> Dict[str, float]:
    targets: Dict[str, float] = {}
    alloc = strategy.get("allocation", {})
    for bucket in ("core", "satellite"):
        for item in alloc.get(bucket, []):
            targets[item["symbol"]] = float(item["target_pct"]) / 100.0
    return targets


def extract_values(portfolio: dict) -> Dict[str, float]:
    values: Dict[str, float] = {}
    for p in portfolio.get("positions", []):
        symbol = p["symbol"]
        qty = float(p.get("quantity", 0))
        # 示例项目中没有实时价格，先用 avg_cost 近似
        price = float(p.get("avg_cost", 0))
        values[symbol] = qty * price
    return values


def plan_rebalance(targets: Dict[str, float], values: Dict[str, float]) -> List[str]:
    total_value = sum(values.values())
    if total_value <= 0:
        return ["组合总市值为 0，无法计算再平衡。"]

    lines: List[str] = []
    lines.append(f"组合总市值(估算): ${total_value:,.2f}")
    lines.append("建议调仓(正数=买入, 负数=卖出):")

    for symbol, target_weight in targets.items():
        current = values.get(symbol, 0.0)
        target_value = total_value * target_weight
        delta = target_value - current
        lines.append(
            f"- {symbol}: 当前 ${current:,.2f}, 目标 ${target_value:,.2f}, 差额 ${delta:,.2f}"
        )

    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Portfolio rebalance helper")
    parser.add_argument("--strategy", type=Path, default=Path("strategy.yaml"))
    parser.add_argument("--portfolio", type=Path, default=Path("portfolio.yaml"))
    args = parser.parse_args()

    strategy = load_yaml(args.strategy)
    portfolio = load_yaml(args.portfolio)

    targets = extract_targets(strategy)
    values = extract_values(portfolio)
    report = plan_rebalance(targets, values)
    print("\n".join(report))


if __name__ == "__main__":
    main()
