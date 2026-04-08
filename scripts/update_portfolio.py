#!/usr/bin/env python3
"""根据单条交易或 CSV 批量交易更新 portfolio.yaml。"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO_PATH = ROOT / "data" / "portfolio.yaml"
TXN_PATH = ROOT / "data" / "transactions.csv"


def load_portfolio(path: Path) -> dict[str, Any]:
    import yaml

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("cash_usd", 0.0)
    data.setdefault("positions", [])
    return data


def position_map(portfolio: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output = {}
    for p in portfolio.get("positions", []):
        t = str(p.get("ticker", "")).upper()
        if t:
            output[t] = p
    return output


def apply_trade(pos: dict[str, Any], side: str, shares: float, price: float) -> None:
    cur_shares = float(pos.get("shares", 0.0) or 0.0)
    cur_avg = float(pos.get("avg_cost", 0.0) or 0.0)

    if side == "buy":
        new_shares = cur_shares + shares
        if new_shares <= 0:
            raise ValueError("买入后持仓股数异常")
        new_avg = ((cur_shares * cur_avg) + (shares * price)) / new_shares
        pos["shares"] = new_shares
        pos["avg_cost"] = new_avg
    elif side == "sell":
        if shares > cur_shares:
            raise ValueError("卖出数量超过当前持仓")
        new_shares = cur_shares - shares
        pos["shares"] = new_shares
        pos["avg_cost"] = cur_avg if new_shares > 0 else 0.0
    else:
        raise ValueError(f"未知 side: {side}")

    last_price = float(pos.get("last_price", 0.0) or 0.0)
    ref_price = last_price if last_price > 0 else price
    pos["market_value"] = float(pos["shares"]) * ref_price


def ensure_position(portfolio: dict[str, Any], ticker: str) -> dict[str, Any]:
    mapping = position_map(portfolio)
    if ticker in mapping:
        return mapping[ticker]

    new_pos = {
        "ticker": ticker,
        "shares": 0.0,
        "avg_cost": 0.0,
        "last_price": 0.0,
        "market_value": 0.0,
    }
    portfolio.setdefault("positions", []).append(new_pos)
    return new_pos


def write_portfolio_atomic(path: Path, portfolio: dict[str, Any]) -> None:
    import yaml

    tmp_path = path.with_suffix(".yaml.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(portfolio, f, allow_unicode=True, sort_keys=False)
    tmp_path.replace(path)


def update_from_manual(portfolio: dict[str, Any], ticker: str, shares: float, price: float, side: str) -> None:
    ticker = ticker.upper()
    pos = ensure_position(portfolio, ticker)
    apply_trade(pos, side.lower(), shares, price)


def update_from_csv(portfolio: dict[str, Any], csv_path: Path) -> None:
    if not csv_path.exists():
        raise FileNotFoundError(f"交易文件不存在: {csv_path}")

    df = pd.read_csv(csv_path)
    required = {"ticker", "side", "shares", "price"}
    if not required.issubset(set(df.columns)):
        raise ValueError(f"CSV 缺少必要列: {required}")

    errors = []
    for idx, row in df.iterrows():
        try:
            ticker = str(row["ticker"]).upper().strip()
            side = str(row["side"]).lower().strip()
            shares = float(row["shares"])
            price = float(row["price"])
            if not ticker or shares <= 0 or price <= 0:
                raise ValueError("ticker 为空或 shares/price 非正数")

            pos = ensure_position(portfolio, ticker)
            apply_trade(pos, side, shares, price)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"第 {idx + 2} 行: {exc}")

    if errors:
        print("[警告] 以下行处理失败，已跳过：")
        for e in errors:
            print(f"  - {e}")


def refresh_market_values(portfolio: dict[str, Any]) -> None:
    for pos in portfolio.get("positions", []):
        shares = float(pos.get("shares", 0.0) or 0.0)
        last_price = float(pos.get("last_price", 0.0) or 0.0)
        pos["market_value"] = shares * last_price


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="更新 portfolio.yaml")
    parser.add_argument("--portfolio", type=Path, default=PORTFOLIO_PATH)
    parser.add_argument("--from-csv", type=Path, default=None, help="从 CSV 批量导入交易")
    parser.add_argument("--ticker", type=str, default=None)
    parser.add_argument("--shares", type=float, default=None)
    parser.add_argument("--price", type=float, default=None)
    parser.add_argument("--side", type=str, default=None, choices=["buy", "sell"])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    portfolio = load_portfolio(args.portfolio)

    used_manual = all(v is not None for v in [args.ticker, args.shares, args.price, args.side])
    used_csv = args.from_csv is not None

    if not used_manual and not used_csv:
        raise ValueError("请使用手动模式参数或 --from-csv")

    if used_manual:
        update_from_manual(portfolio, args.ticker, args.shares, args.price, args.side)
    if used_csv:
        update_from_csv(portfolio, args.from_csv)

    portfolio["as_of"] = str(date.today())
    refresh_market_values(portfolio)
    write_portfolio_atomic(args.portfolio, portfolio)
    print(f"已更新持仓文件: {args.portfolio}")


if __name__ == "__main__":
    main()
