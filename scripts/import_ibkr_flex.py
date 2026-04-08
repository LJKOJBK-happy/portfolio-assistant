#!/usr/bin/env python3
"""IBKR 导入初版：支持本地 CSV/Flex 导出解析并写回 portfolio.yaml。"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO_PATH = ROOT / "data" / "portfolio.yaml"


class IbkrImporter:
    """后续可扩展到 Flex Web Service / Client Portal API。"""

    def parse_local_export(self, path: Path) -> tuple[list[dict[str, float]], float]:
        df = pd.read_csv(path)
        cols = {c.lower(): c for c in df.columns}

        ticker_col = cols.get("ticker") or cols.get("symbol")
        shares_col = cols.get("shares") or cols.get("position") or cols.get("quantity")
        avg_col = cols.get("avg_cost") or cols.get("averagecost") or cols.get("cost")
        cash_col = cols.get("cash") or cols.get("cash_usd")

        if not ticker_col or not shares_col:
            raise ValueError("无法识别持仓列，请至少提供 ticker/symbol 与 shares/position")

        positions = []
        for _, row in df.iterrows():
            ticker = str(row[ticker_col]).upper().strip()
            if not ticker:
                continue
            shares = float(row[shares_col])
            avg_cost = float(row[avg_col]) if avg_col and pd.notna(row.get(avg_col)) else 0.0
            positions.append(
                {
                    "ticker": ticker,
                    "shares": shares,
                    "avg_cost": avg_cost,
                    "last_price": 0.0,
                    "market_value": 0.0,
                }
            )

        cash = 0.0
        if cash_col and len(df) > 0 and pd.notna(df.iloc[0][cash_col]):
            cash = float(df.iloc[0][cash_col])

        return positions, cash


def load_portfolio(path: Path) -> dict[str, Any]:
    import yaml

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_portfolio(path: Path, portfolio: dict[str, Any]) -> None:
    import yaml

    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(portfolio, f, allow_unicode=True, sort_keys=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导入 IBKR 本地导出文件")
    parser.add_argument("--input", type=Path, required=True, help="IBKR 导出的 CSV/Flex 文件路径")
    parser.add_argument("--portfolio", type=Path, default=PORTFOLIO_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    importer = IbkrImporter()

    positions, cash = importer.parse_local_export(args.input)
    portfolio = load_portfolio(args.portfolio)
    portfolio["positions"] = positions
    portfolio["cash_usd"] = cash
    portfolio["as_of"] = str(date.today())

    write_portfolio(args.portfolio, portfolio)
    print(f"已导入 {len(positions)} 条持仓，现金 {cash:.2f} USD")
    print(f"已写回: {args.portfolio}")


if __name__ == "__main__":
    main()
