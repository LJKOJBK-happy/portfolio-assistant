#!/usr/bin/env python3
"""根据策略与持仓，生成补仓建议（整股 + 碎股）。"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STRATEGY_PATH = ROOT / "data" / "strategy.yaml"
PORTFOLIO_PATH = ROOT / "data" / "portfolio.yaml"
PRICE_CACHE_PATH = ROOT / "data" / "price_cache.json"


@dataclass
class AssetSnapshot:
    ticker: str
    target_weight: float
    price: float
    current_value: float
    current_weight: float
    deviation: float


def load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_prices(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    prices: dict[str, float] = {}
    for ticker, obj in raw.items():
        if isinstance(obj, dict) and obj.get("price") is not None:
            prices[ticker] = float(obj["price"])
    return prices


def normalize_positions(portfolio: dict[str, Any]) -> dict[str, dict[str, float]]:
    positions = {}
    for pos in portfolio.get("positions", []):
        ticker = str(pos.get("ticker", "")).upper()
        if not ticker:
            continue
        positions[ticker] = {
            "shares": float(pos.get("shares", 0.0) or 0.0),
            "last_price": float(pos.get("last_price", 0.0) or 0.0),
            "market_value": float(pos.get("market_value", 0.0) or 0.0),
        }
    return positions


def build_snapshot(strategy: dict[str, Any], portfolio: dict[str, Any], prices: dict[str, float]) -> list[AssetSnapshot]:
    targets: dict[str, float] = strategy.get("targets", {})
    positions = normalize_positions(portfolio)

    current_values: dict[str, float] = {}
    for t in targets:
        pos = positions.get(t, {})
        shares = float(pos.get("shares", 0.0))
        price = prices.get(t) or float(pos.get("last_price", 0.0))
        if price <= 0:
            price = 0.0
        current_values[t] = shares * price

    total_value = sum(current_values.values())
    snapshots: list[AssetSnapshot] = []

    for t, target_w in targets.items():
        price = prices.get(t) or positions.get(t, {}).get("last_price", 0.0) or 0.0
        value = current_values[t]
        current_w = (value / total_value) if total_value > 0 else 0.0
        snapshots.append(
            AssetSnapshot(
                ticker=t,
                target_weight=float(target_w),
                price=float(price),
                current_value=float(value),
                current_weight=float(current_w),
                deviation=float(current_w - float(target_w)),
            )
        )
    return snapshots


def allocate_fractional(snapshots: list[AssetSnapshot], contribution: float) -> dict[str, float]:
    underweights = {
        s.ticker: max(s.target_weight - s.current_weight, 0.0)
        for s in snapshots
    }
    total_under = sum(underweights.values())

    if total_under <= 0:
        total_target = sum(s.target_weight for s in snapshots)
        return {
            s.ticker: contribution * (s.target_weight / total_target if total_target > 0 else 0.0)
            for s in snapshots
        }

    return {
        s.ticker: contribution * (underweights[s.ticker] / total_under)
        for s in snapshots
    }


def allocate_whole_shares(snapshots: list[AssetSnapshot], desired_amounts: dict[str, float], contribution: float) -> tuple[dict[str, int], float]:
    shares = {s.ticker: 0 for s in snapshots}
    remaining = contribution

    for s in sorted(snapshots, key=lambda x: x.target_weight - x.current_weight, reverse=True):
        if s.price <= 0:
            continue
        budget = desired_amounts.get(s.ticker, 0.0)
        qty = int(min(math.floor(budget / s.price), math.floor(remaining / s.price)))
        if qty > 0:
            shares[s.ticker] += qty
            remaining -= qty * s.price

    # 贪心分配剩余现金给最缺配资产
    loop_guard = 0
    while remaining > 0 and loop_guard < 10000:
        loop_guard += 1
        candidates = [s for s in snapshots if s.price > 0 and s.price <= remaining]
        if not candidates:
            break
        best = max(candidates, key=lambda x: x.target_weight - x.current_weight)
        shares[best.ticker] += 1
        remaining -= best.price

    return shares, remaining


def build_plan(strategy: dict[str, Any], portfolio: dict[str, Any], prices: dict[str, float], contribution: float) -> dict[str, Any]:
    snapshots = build_snapshot(strategy, portfolio, prices)
    before_total = sum(s.current_value for s in snapshots)
    total_after = before_total + contribution

    frac_amounts = allocate_fractional(snapshots, contribution)
    frac_shares = {
        s.ticker: (frac_amounts[s.ticker] / s.price if s.price > 0 else 0.0)
        for s in snapshots
    }

    whole_shares, remaining_cash = allocate_whole_shares(snapshots, frac_amounts, contribution)
    whole_amounts = {s.ticker: whole_shares[s.ticker] * s.price for s in snapshots}

    rows = []
    for s in snapshots:
        after_whole_value = s.current_value + whole_amounts[s.ticker]
        after_frac_value = s.current_value + frac_amounts[s.ticker]

        rows.append(
            {
                "ticker": s.ticker,
                "price": s.price,
                "current_value": s.current_value,
                "current_weight": s.current_weight,
                "target_weight": s.target_weight,
                "deviation": s.deviation,
                "buy_amount_whole": whole_amounts[s.ticker],
                "buy_shares_whole": whole_shares[s.ticker],
                "post_weight_whole": after_whole_value / total_after if total_after > 0 else 0.0,
                "buy_amount_fractional": frac_amounts[s.ticker],
                "buy_shares_fractional": frac_shares[s.ticker],
                "post_weight_fractional": after_frac_value / total_after if total_after > 0 else 0.0,
            }
        )

    return {
        "before_total_value": before_total,
        "contribution": contribution,
        "after_total_value": total_after,
        "whole_remaining_cash": remaining_cash,
        "rows": rows,
    }


def print_plan(plan: dict[str, Any]) -> None:
    print("=" * 90)
    print("本月补仓计划（规则型，不择时）")
    print("=" * 90)
    print(f"买前总市值: ${plan['before_total_value']:.2f}")
    print(f"本月投入:   ${plan['contribution']:.2f}")
    print(f"买后总市值: ${plan['after_total_value']:.2f}\n")

    headers = (
        "Ticker", "买前占比", "目标占比", "偏差", "整股买入$", "整股买入股数", "整股买后占比", "碎股买入$", "碎股买入股数", "碎股买后占比"
    )
    print(" | ".join(headers))
    print("-" * 150)

    for r in plan["rows"]:
        print(
            f"{r['ticker']:5s} | "
            f"{r['current_weight']*100:7.2f}% | "
            f"{r['target_weight']*100:7.2f}% | "
            f"{r['deviation']*100:+7.2f}% | "
            f"${r['buy_amount_whole']:9.2f} | "
            f"{r['buy_shares_whole']:11d} | "
            f"{r['post_weight_whole']*100:9.2f}% | "
            f"${r['buy_amount_fractional']:9.2f} | "
            f"{r['buy_shares_fractional']:13.4f} | "
            f"{r['post_weight_fractional']*100:9.2f}%"
        )

    print("\n整股方案剩余现金: ${:.2f}".format(plan["whole_remaining_cash"]))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成本月补仓计划")
    parser.add_argument("--contribution", type=float, required=True, help="本月计划投入金额（USD）")
    parser.add_argument("--strategy", type=Path, default=STRATEGY_PATH)
    parser.add_argument("--portfolio", type=Path, default=PORTFOLIO_PATH)
    parser.add_argument("--prices", type=Path, default=PRICE_CACHE_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.contribution < 0:
        raise ValueError("contribution 必须 >= 0")

    strategy = load_yaml(args.strategy)
    portfolio = load_yaml(args.portfolio)
    prices = load_prices(args.prices)
    plan = build_plan(strategy, portfolio, prices, args.contribution)
    print_plan(plan)


if __name__ == "__main__":
    main()
