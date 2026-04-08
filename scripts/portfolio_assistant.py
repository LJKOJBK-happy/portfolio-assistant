#!/usr/bin/env python3
"""Portable portfolio assistant script for any workspace."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STRATEGY_TEMPLATE = SKILL_ROOT / "assets" / "templates" / "default_strategy.yaml"
DEFAULT_PORTFOLIO_TEMPLATE = SKILL_ROOT / "assets" / "templates" / "empty_portfolio.yaml"


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

    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def resolve_workspace(path_arg: str | None) -> Path:
    raw = Path(path_arg) if path_arg else Path.cwd() / ".portfolio-assistant"
    return raw.resolve()


def workspace_paths(workspace: Path) -> dict[str, Path]:
    data_dir = workspace / "data"
    return {
        "workspace": workspace,
        "data_dir": data_dir,
        "strategy": data_dir / "strategy.yaml",
        "portfolio": data_dir / "portfolio.yaml",
        "prices": data_dir / "price_cache.json",
    }


def ensure_workspace_files(workspace: Path) -> dict[str, Path]:
    paths = workspace_paths(workspace)
    paths["data_dir"].mkdir(parents=True, exist_ok=True)
    if not paths["strategy"].exists():
        shutil.copyfile(DEFAULT_STRATEGY_TEMPLATE, paths["strategy"])
    if not paths["portfolio"].exists():
        shutil.copyfile(DEFAULT_PORTFOLIO_TEMPLATE, paths["portfolio"])
    return paths


def parse_holding_spec(spec: str) -> dict[str, float | str]:
    parts = [item.strip() for item in spec.split(",")]
    if len(parts) < 2:
        raise ValueError(f"holding 格式错误: {spec}")

    ticker = parts[0].upper()
    if not ticker:
        raise ValueError("ticker 不能为空")

    shares = float(parts[1])
    avg_cost = float(parts[2]) if len(parts) >= 3 and parts[2] else 0.0
    last_price = float(parts[3]) if len(parts) >= 4 and parts[3] else 0.0

    if shares < 0:
        raise ValueError(f"{ticker} 的 shares 不能为负数")

    return {
        "ticker": ticker,
        "shares": shares,
        "avg_cost": avg_cost,
        "last_price": last_price,
        "market_value": shares * last_price if last_price > 0 else 0.0,
    }


def build_positions(strategy: dict[str, Any], holding_specs: list[str]) -> list[dict[str, Any]]:
    targets = strategy.get("targets", {})
    positions = {
        ticker: {
            "ticker": ticker,
            "shares": 0.0,
            "avg_cost": 0.0,
            "last_price": 0.0,
            "market_value": 0.0,
        }
        for ticker in targets
    }

    for spec in holding_specs:
        position = parse_holding_spec(spec)
        positions[str(position["ticker"])] = position

    return list(positions.values())


def load_prices(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    prices: dict[str, float] = {}
    for ticker, obj in raw.items():
        if isinstance(obj, dict) and obj.get("price") is not None:
            prices[str(ticker).upper()] = float(obj["price"])
    return prices


def write_prices(path: Path, data: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_positions(portfolio: dict[str, Any]) -> dict[str, dict[str, float]]:
    positions = {}
    for pos in portfolio.get("positions", []):
        ticker = str(pos.get("ticker", "")).upper()
        if not ticker:
            continue
        positions[ticker] = {
            "shares": float(pos.get("shares", 0.0) or 0.0),
            "avg_cost": float(pos.get("avg_cost", 0.0) or 0.0),
            "last_price": float(pos.get("last_price", 0.0) or 0.0),
            "market_value": float(pos.get("market_value", 0.0) or 0.0),
        }
    return positions


def build_snapshot(strategy: dict[str, Any], portfolio: dict[str, Any], prices: dict[str, float]) -> list[AssetSnapshot]:
    targets: dict[str, float] = strategy.get("targets", {})
    positions = normalize_positions(portfolio)

    current_values: dict[str, float] = {}
    for ticker in targets:
        pos = positions.get(ticker, {})
        shares = float(pos.get("shares", 0.0))
        price = prices.get(ticker) or float(pos.get("last_price", 0.0))
        current_values[ticker] = shares * price if price > 0 else 0.0

    total_value = sum(current_values.values())
    snapshots: list[AssetSnapshot] = []
    for ticker, target_weight in targets.items():
        price = prices.get(ticker) or positions.get(ticker, {}).get("last_price", 0.0) or 0.0
        value = current_values[ticker]
        current_weight = (value / total_value) if total_value > 0 else 0.0
        snapshots.append(
            AssetSnapshot(
                ticker=ticker,
                target_weight=float(target_weight),
                price=float(price),
                current_value=float(value),
                current_weight=float(current_weight),
                deviation=float(current_weight - float(target_weight)),
            )
        )
    return snapshots


def allocate_fractional(snapshots: list[AssetSnapshot], contribution: float) -> dict[str, float]:
    underweights = {s.ticker: max(s.target_weight - s.current_weight, 0.0) for s in snapshots}
    total_under = sum(underweights.values())

    if total_under <= 0:
        total_target = sum(s.target_weight for s in snapshots)
        return {
            s.ticker: contribution * (s.target_weight / total_target if total_target > 0 else 0.0)
            for s in snapshots
        }

    return {s.ticker: contribution * (underweights[s.ticker] / total_under) for s in snapshots}


def allocate_whole_shares(
    snapshots: list[AssetSnapshot], desired_amounts: dict[str, float], contribution: float
) -> tuple[dict[str, int], float]:
    shares = {s.ticker: 0 for s in snapshots}
    remaining = contribution

    for snapshot in sorted(snapshots, key=lambda item: item.target_weight - item.current_weight, reverse=True):
        if snapshot.price <= 0:
            continue
        budget = desired_amounts.get(snapshot.ticker, 0.0)
        qty = int(min(math.floor(budget / snapshot.price), math.floor(remaining / snapshot.price)))
        if qty > 0:
            shares[snapshot.ticker] += qty
            remaining -= qty * snapshot.price

    loop_guard = 0
    while remaining > 0 and loop_guard < 10000:
        loop_guard += 1
        candidates = [s for s in snapshots if s.price > 0 and s.price <= remaining]
        if not candidates:
            break
        best = max(candidates, key=lambda item: item.target_weight - item.current_weight)
        shares[best.ticker] += 1
        remaining -= best.price

    return shares, remaining


def build_plan(strategy: dict[str, Any], portfolio: dict[str, Any], prices: dict[str, float], contribution: float) -> dict[str, Any]:
    snapshots = build_snapshot(strategy, portfolio, prices)
    priced_snapshots = [snapshot for snapshot in snapshots if snapshot.price > 0]
    missing_price_tickers = [snapshot.ticker for snapshot in snapshots if snapshot.price <= 0]
    before_total = sum(snapshot.current_value for snapshot in snapshots)
    total_after = before_total + contribution

    frac_amounts = {snapshot.ticker: 0.0 for snapshot in snapshots}
    whole_shares = {snapshot.ticker: 0 for snapshot in snapshots}
    whole_amounts = {snapshot.ticker: 0.0 for snapshot in snapshots}
    remaining_cash = contribution

    if priced_snapshots:
        eligible_frac_amounts = allocate_fractional(priced_snapshots, contribution)
        frac_amounts.update(eligible_frac_amounts)

        eligible_whole_shares, remaining_cash = allocate_whole_shares(priced_snapshots, eligible_frac_amounts, contribution)
        for ticker, qty in eligible_whole_shares.items():
            whole_shares[ticker] = qty
        whole_amounts.update(
            {
                snapshot.ticker: whole_shares[snapshot.ticker] * snapshot.price
                for snapshot in priced_snapshots
            }
        )

    frac_shares = {
        snapshot.ticker: (frac_amounts[snapshot.ticker] / snapshot.price if snapshot.price > 0 else 0.0)
        for snapshot in snapshots
    }

    rows = []
    for snapshot in snapshots:
        after_whole_value = snapshot.current_value + whole_amounts[snapshot.ticker]
        after_frac_value = snapshot.current_value + frac_amounts[snapshot.ticker]
        rows.append(
            {
                "ticker": snapshot.ticker,
                "price": snapshot.price,
                "current_value": snapshot.current_value,
                "current_weight": snapshot.current_weight,
                "target_weight": snapshot.target_weight,
                "deviation": snapshot.deviation,
                "buy_amount_whole": whole_amounts[snapshot.ticker],
                "buy_shares_whole": whole_shares[snapshot.ticker],
                "post_weight_whole": after_whole_value / total_after if total_after > 0 else 0.0,
                "buy_amount_fractional": frac_amounts[snapshot.ticker],
                "buy_shares_fractional": frac_shares[snapshot.ticker],
                "post_weight_fractional": after_frac_value / total_after if total_after > 0 else 0.0,
            }
        )

    return {
        "before_total_value": before_total,
        "contribution": contribution,
        "after_total_value": total_after,
        "whole_remaining_cash": remaining_cash,
        "missing_price_tickers": missing_price_tickers,
        "rows": rows,
    }


def build_report(strategy: dict[str, Any], portfolio: dict[str, Any], prices: dict[str, float]) -> dict[str, Any]:
    snapshots = build_snapshot(strategy, portfolio, prices)
    cash = float(portfolio.get("cash_usd", 0.0) or 0.0)
    total_positions = sum(snapshot.current_value for snapshot in snapshots)
    total = total_positions + cash
    return {
        "as_of": portfolio.get("as_of", ""),
        "cash_usd": cash,
        "total_positions_value": total_positions,
        "total_value": total,
        "missing_price_tickers": [snapshot.ticker for snapshot in snapshots if snapshot.price <= 0],
        "rows": [asdict(snapshot) for snapshot in snapshots],
    }


def print_report(report: dict[str, Any]) -> None:
    print("=" * 86)
    print("投资组合报告")
    print("=" * 86)
    print(f"日期: {report.get('as_of', 'N/A')}")
    print(f"当前总市值(含现金): ${report['total_value']:.2f}")
    print(f"现金: ${report['cash_usd']:.2f}\n")
    if report.get("missing_price_tickers"):
        print(f"缺少价格: {', '.join(report['missing_price_tickers'])}\n")
    print("Ticker | 市值(USD) | 当前占比 | 目标占比 | 偏差 | 价格")
    print("-" * 98)
    total_positions = float(report.get("total_positions_value", 0.0) or 0.0)
    for row in report["rows"]:
        current_weight = (row["current_value"] / total_positions) if total_positions > 0 else 0.0
        print(
            f"{row['ticker']:5s} | "
            f"${row['current_value']:9.2f} | "
            f"{current_weight*100:7.2f}% | "
            f"{row['target_weight']*100:7.2f}% | "
            f"{row['deviation']*100:+7.2f}% | "
            f"${row['price']:8.2f}"
        )


def print_plan(plan: dict[str, Any]) -> None:
    print("=" * 90)
    print("本月补仓计划（规则型，不择时）")
    print("=" * 90)
    print(f"买前总市值: ${plan['before_total_value']:.2f}")
    print(f"本月投入:   ${plan['contribution']:.2f}")
    print(f"买后总市值: ${plan['after_total_value']:.2f}\n")
    if plan.get("missing_price_tickers"):
        print(f"缺少价格，以下资产未纳入完整建议: {', '.join(plan['missing_price_tickers'])}\n")

    headers = (
        "Ticker",
        "买前占比",
        "目标占比",
        "偏差",
        "整股买入$",
        "整股买入股数",
        "整股买后占比",
        "碎股买入$",
        "碎股买入股数",
        "碎股买后占比",
    )
    print(" | ".join(headers))
    print("-" * 150)

    for row in plan["rows"]:
        print(
            f"{row['ticker']:5s} | "
            f"{row['current_weight']*100:7.2f}% | "
            f"{row['target_weight']*100:7.2f}% | "
            f"{row['deviation']*100:+7.2f}% | "
            f"${row['buy_amount_whole']:9.2f} | "
            f"{row['buy_shares_whole']:11d} | "
            f"{row['post_weight_whole']*100:9.2f}% | "
            f"${row['buy_amount_fractional']:9.2f} | "
            f"{row['buy_shares_fractional']:13.4f} | "
            f"{row['post_weight_fractional']*100:9.2f}%"
        )

    print(f"\n整股方案剩余现金: ${plan['whole_remaining_cash']:.2f}")


def fetch_price_for_ticker(ticker: str) -> float | None:
    try:
        import yfinance as yf
    except ImportError as exc:  # noqa: BLE001
        raise RuntimeError("未安装 yfinance，无法刷新价格") from exc

    try:
        ticker_obj = yf.Ticker(ticker)
        fast_price = getattr(ticker_obj, "fast_info", {}).get("lastPrice")
        if fast_price:
            return float(fast_price)

        history = ticker_obj.history(period="1d")
        if not history.empty:
            return float(history["Close"].iloc[-1])
    except Exception as exc:  # noqa: BLE001
        print(f"[警告] 获取 {ticker} 价格失败: {exc}")
    return None


def command_init(args: argparse.Namespace) -> dict[str, Any]:
    workspace = resolve_workspace(args.workspace)
    paths = ensure_workspace_files(workspace)
    strategy = load_yaml(paths["strategy"])
    positions = build_positions(strategy, args.holding or [])

    portfolio = {
        "as_of": args.as_of or str(date.today()),
        "cash_usd": float(args.cash or 0.0),
        "positions": positions,
    }
    write_yaml(paths["portfolio"], portfolio)

    return {
        "workspace": str(workspace),
        "strategy_path": str(paths["strategy"]),
        "portfolio_path": str(paths["portfolio"]),
        "positions_count": len(positions),
        "cash_usd": portfolio["cash_usd"],
    }


def command_sync_holdings(args: argparse.Namespace) -> dict[str, Any]:
    return command_init(args)


def command_refresh_prices(args: argparse.Namespace) -> dict[str, Any]:
    workspace = resolve_workspace(args.workspace)
    paths = ensure_workspace_files(workspace)
    strategy = load_yaml(paths["strategy"])
    existing = load_yaml(paths["portfolio"])
    cache = {}
    if paths["prices"].exists():
        with paths["prices"].open("r", encoding="utf-8") as f:
            loaded = json.load(f)
            if isinstance(loaded, dict):
                cache = loaded

    targets = list((strategy.get("targets") or {}).keys())
    now = datetime.now(timezone.utc).isoformat()
    updated: dict[str, dict[str, Any]] = {}
    refreshed = []
    fallback = []
    missing = []

    portfolio_positions = normalize_positions(existing)
    for ticker in targets:
        price = fetch_price_for_ticker(ticker)
        if price is not None:
            updated[ticker] = {"price": price, "timestamp": now, "source": "yfinance"}
            refreshed.append(ticker)
            continue

        cached_price = cache.get(ticker, {}).get("price")
        if cached_price is not None:
            updated[ticker] = {"price": float(cached_price), "timestamp": now, "source": "cache_fallback"}
            fallback.append(ticker)
            continue

        portfolio_price = portfolio_positions.get(ticker, {}).get("last_price")
        if portfolio_price:
            updated[ticker] = {"price": float(portfolio_price), "timestamp": now, "source": "portfolio_last_price"}
            fallback.append(ticker)
            continue

        missing.append(ticker)

    write_prices(paths["prices"], updated)
    return {
        "workspace": str(workspace),
        "price_cache_path": str(paths["prices"]),
        "refreshed": refreshed,
        "fallback": fallback,
        "missing": missing,
        "prices": updated,
    }


def command_report(args: argparse.Namespace) -> dict[str, Any]:
    workspace = resolve_workspace(args.workspace)
    paths = ensure_workspace_files(workspace)
    strategy = load_yaml(paths["strategy"])
    portfolio = load_yaml(paths["portfolio"])
    prices = load_prices(paths["prices"])
    return build_report(strategy, portfolio, prices)


def command_rebalance(args: argparse.Namespace) -> dict[str, Any]:
    if args.contribution < 0:
        raise ValueError("contribution 必须 >= 0")
    workspace = resolve_workspace(args.workspace)
    paths = ensure_workspace_files(workspace)
    strategy = load_yaml(paths["strategy"])
    portfolio = load_yaml(paths["portfolio"])
    prices = load_prices(paths["prices"])
    return build_plan(strategy, portfolio, prices, args.contribution)


def print_or_json(payload: dict[str, Any], as_json: bool, renderer: Any | None = None) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if renderer is not None:
        renderer(payload)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Portable portfolio assistant")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="初始化工作区并写入首次持仓")
    init_parser.add_argument("--workspace", type=str, default=None)
    init_parser.add_argument("--cash", type=float, default=0.0)
    init_parser.add_argument("--as-of", type=str, default=None)
    init_parser.add_argument("--holding", action="append", default=[])
    init_parser.add_argument("--json", action="store_true")

    sync_parser = subparsers.add_parser("sync-holdings", help="覆盖同步当前持仓")
    sync_parser.add_argument("--workspace", type=str, default=None)
    sync_parser.add_argument("--cash", type=float, default=0.0)
    sync_parser.add_argument("--as-of", type=str, default=None)
    sync_parser.add_argument("--holding", action="append", default=[])
    sync_parser.add_argument("--json", action="store_true")

    refresh_parser = subparsers.add_parser("refresh-prices", help="刷新目标资产价格")
    refresh_parser.add_argument("--workspace", type=str, default=None)
    refresh_parser.add_argument("--json", action="store_true")

    report_parser = subparsers.add_parser("report", help="查看当前组合")
    report_parser.add_argument("--workspace", type=str, default=None)
    report_parser.add_argument("--json", action="store_true")

    rebalance_parser = subparsers.add_parser("rebalance", help="生成补仓建议")
    rebalance_parser.add_argument("--workspace", type=str, default=None)
    rebalance_parser.add_argument("--contribution", type=float, required=True)
    rebalance_parser.add_argument("--json", action="store_true")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init":
        payload = command_init(args)
        print_or_json(payload, args.json)
        return

    if args.command == "sync-holdings":
        payload = command_sync_holdings(args)
        print_or_json(payload, args.json)
        return

    if args.command == "refresh-prices":
        payload = command_refresh_prices(args)
        print_or_json(payload, args.json)
        return

    if args.command == "report":
        payload = command_report(args)
        print_or_json(payload, args.json, print_report)
        return

    if args.command == "rebalance":
        payload = command_rebalance(args)
        print_or_json(payload, args.json, print_plan)
        return

    parser.error(f"未知命令: {args.command}")


if __name__ == "__main__":
    main()
