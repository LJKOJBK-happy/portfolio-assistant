#!/usr/bin/env python3
"""Portable portfolio assistant script for any workspace."""

from __future__ import annotations

import argparse
import json
import math
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STRATEGY_TEMPLATE = SKILL_ROOT / "assets" / "templates" / "default_strategy.yaml"
DEFAULT_PORTFOLIO_TEMPLATE = SKILL_ROOT / "assets" / "templates" / "empty_portfolio.yaml"
SUPPORTED_CURRENCIES = {"CNY", "USD", "GBP", "JPY"}
CURRENCY_ALIASES = {
    "CNY": "CNY",
    "RMB": "CNY",
    "CNH": "CNY",
    "人民币": "CNY",
    "元": "CNY",
    "USD": "USD",
    "US$": "USD",
    "$": "USD",
    "美元": "USD",
    "美金": "USD",
    "刀": "USD",
    "GBP": "GBP",
    "英镑": "GBP",
    "JPY": "JPY",
    "日元": "JPY",
    "YEN": "JPY",
}


@dataclass
class HoldingSnapshot:
    category_name: str
    ticker: str
    shares: float
    price: float
    value: float


@dataclass
class CategorySnapshot:
    name: str
    target_weight: float
    current_value: float
    current_weight: float
    deviation: float
    holdings: list[HoldingSnapshot]


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
    raw = Path(path_arg) if path_arg else SKILL_ROOT
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


def normalize_ticker(value: Any) -> str:
    return str(value or "").upper().strip()


def canonicalize_currency(value: Any, default: str = "CNY") -> str:
    raw = str(value or "").strip()
    if not raw:
        return default
    normalized = CURRENCY_ALIASES.get(raw.upper()) or CURRENCY_ALIASES.get(raw) or raw.upper()
    if normalized not in SUPPORTED_CURRENCIES:
        raise ValueError(f"不支持的货币: {value}")
    return normalized


def unique_ordered(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def parse_strategy(strategy: dict[str, Any]) -> dict[str, Any]:
    raw_groups = strategy.get("groups") or {}
    raw_targets = strategy.get("targets") or {}
    base_currency = canonicalize_currency(strategy.get("base_currency", "CNY"))

    groups: dict[str, list[str]] = {}
    ticker_to_group: dict[str, str] = {}
    for group_name, tickers in raw_groups.items():
        label = str(group_name)
        normalized_tickers = unique_ordered([normalize_ticker(ticker) for ticker in (tickers or [])])
        groups[label] = normalized_tickers
        for ticker in normalized_tickers:
            ticker_to_group.setdefault(ticker, label)

    targets: dict[str, float] = {}
    category_to_tickers: dict[str, list[str]] = {}
    tracked_tickers: list[str] = []

    for name, weight in raw_targets.items():
        label = str(name)
        targets[label] = float(weight)
        if label in groups:
            category_tickers = groups[label][:]
        else:
            category_tickers = [normalize_ticker(label)]
        category_to_tickers[label] = unique_ordered(category_tickers)
        tracked_tickers.extend(category_to_tickers[label])

    for tickers in groups.values():
        tracked_tickers.extend(tickers)

    return {
        "base_currency": base_currency,
        "groups": groups,
        "targets": targets,
        "category_to_tickers": category_to_tickers,
        "ticker_to_group": ticker_to_group,
        "tracked_tickers": unique_ordered(tracked_tickers),
    }


def parse_holding_spec(spec: str) -> dict[str, float | str]:
    parts = [item.strip() for item in spec.split(",")]
    if len(parts) < 2:
        raise ValueError(f"holding 格式错误: {spec}")

    ticker = normalize_ticker(parts[0])
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


def parse_group_spec(spec: str) -> tuple[str, list[str]]:
    if "=" not in spec:
        raise ValueError(f"group 格式错误，应为 组名=TICKER1,TICKER2: {spec}")
    raw_name, raw_tickers = spec.split("=", 1)
    group_name = raw_name.strip()
    if not group_name:
        raise ValueError("group 名称不能为空")
    tickers = unique_ordered([normalize_ticker(item) for item in raw_tickers.split(",") if item.strip()])
    if not tickers:
        raise ValueError(f"group {group_name} 不能为空")
    return group_name, tickers


def parse_target_spec(spec: str) -> tuple[str, float]:
    if "=" not in spec:
        raise ValueError(f"target 格式错误，应为 目标名=权重: {spec}")
    raw_name, raw_weight = spec.split("=", 1)
    name = raw_name.strip()
    if not name:
        raise ValueError("target 名称不能为空")
    weight = float(raw_weight.strip())
    if weight < 0:
        raise ValueError(f"target {name} 权重不能为负数")
    return name, weight


def apply_rebalance_rule_overrides(
    strategy: dict[str, Any],
    optional_threshold: float | None,
    mandatory_threshold: float | None,
) -> dict[str, Any]:
    rules = dict(strategy.get("rules") or {})

    if optional_threshold is not None:
        rules["optional_rebalance_threshold"] = float(optional_threshold)
    if mandatory_threshold is not None:
        rules["mandatory_rebalance_threshold"] = float(mandatory_threshold)

    optional_value = float(rules.get("optional_rebalance_threshold", 0.05) or 0.05)
    mandatory_value = float(rules.get("mandatory_rebalance_threshold", 0.08) or 0.08)

    if optional_value < 0 or mandatory_value < 0:
        raise ValueError("再平衡阈值不能为负数")
    if optional_value > 1 or mandatory_value > 1:
        raise ValueError("再平衡阈值应使用 0 到 1 之间的小数")
    if optional_value > mandatory_value:
        raise ValueError("optional_rebalance_threshold 不能大于 mandatory_rebalance_threshold")

    strategy["rules"] = rules
    return strategy


def build_strategy_from_init_args(args: argparse.Namespace, current_strategy: dict[str, Any]) -> tuple[dict[str, Any], str]:
    has_rule_overrides = (
        args.optional_rebalance_threshold is not None or args.mandatory_rebalance_threshold is not None
    )

    if not args.group and not args.target and args.base_currency is None and not has_rule_overrides:
        return current_strategy, "default"

    if not args.group and not args.target:
        strategy = dict(current_strategy or load_yaml(DEFAULT_STRATEGY_TEMPLATE))
        strategy["base_currency"] = canonicalize_currency(args.base_currency or strategy.get("base_currency", "CNY"))
        strategy = apply_rebalance_rule_overrides(
            strategy,
            args.optional_rebalance_threshold,
            args.mandatory_rebalance_threshold,
        )
        return strategy, "default"

    strategy = load_yaml(DEFAULT_STRATEGY_TEMPLATE)
    strategy["base_currency"] = canonicalize_currency(args.base_currency or strategy.get("base_currency", "CNY"))
    strategy["groups"] = {}
    strategy["targets"] = {}

    for spec in args.group:
        group_name, tickers = parse_group_spec(spec)
        strategy["groups"][group_name] = tickers

    for spec in args.target:
        target_name, weight = parse_target_spec(spec)
        strategy["targets"][target_name] = weight

    strategy = apply_rebalance_rule_overrides(
        strategy,
        args.optional_rebalance_threshold,
        args.mandatory_rebalance_threshold,
    )
    return strategy, "custom"


def build_positions(strategy: dict[str, Any], holding_specs: list[str]) -> list[dict[str, Any]]:
    strategy_spec = parse_strategy(strategy)
    positions = {
        ticker: {
            "ticker": ticker,
            "shares": 0.0,
            "avg_cost": 0.0,
            "last_price": 0.0,
            "market_value": 0.0,
        }
        for ticker in strategy_spec["tracked_tickers"]
    }

    for spec in holding_specs:
        position = parse_holding_spec(spec)
        positions[str(position["ticker"])] = position

    return list(positions.values())


def load_price_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return raw if isinstance(raw, dict) else {}


def load_prices(path: Path) -> dict[str, float]:
    raw = load_price_cache(path)
    prices: dict[str, float] = {}
    for ticker, obj in raw.items():
        if str(ticker).startswith("_"):
            continue
        if isinstance(obj, dict) and obj.get("price") is not None:
            prices[normalize_ticker(ticker)] = float(obj["price"])
    return prices


def load_fx_rates(path: Path) -> dict[str, float]:
    raw = load_price_cache(path)
    meta = raw.get("_meta", {}) if isinstance(raw.get("_meta", {}), dict) else {}
    fx_raw = meta.get("fx_rates", {}) if isinstance(meta.get("fx_rates", {}), dict) else {}
    fx_rates = {"USD": 1.0}
    for currency, rate in fx_raw.items():
        try:
            fx_rates[canonicalize_currency(currency, default="USD")] = float(rate)
        except Exception:  # noqa: BLE001
            continue
    return fx_rates


def write_price_cache(path: Path, prices: dict[str, dict[str, Any]], fx_rates: dict[str, float], timestamp: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "_meta": {
            "timestamp": timestamp,
            "fx_rates": fx_rates,
        }
    }
    payload.update(prices)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def usd_to_currency_rate(fx_rates: dict[str, float], currency: str) -> float:
    canonical = canonicalize_currency(currency)
    if canonical == "USD":
        return 1.0
    rate = fx_rates.get(canonical)
    if rate is None or rate <= 0:
        raise ValueError(f"缺少 USD -> {canonical} 汇率")
    return rate


def convert_usd_to_currency(amount_usd: float, currency: str, fx_rates: dict[str, float]) -> float:
    return amount_usd * usd_to_currency_rate(fx_rates, currency)


def convert_currency_to_usd(amount: float, currency: str, fx_rates: dict[str, float]) -> float:
    canonical = canonicalize_currency(currency)
    if canonical == "USD":
        return amount
    return amount / usd_to_currency_rate(fx_rates, canonical)


def convert_amount(amount: float, from_currency: str, to_currency: str, fx_rates: dict[str, float]) -> float:
    source = canonicalize_currency(from_currency)
    target = canonicalize_currency(to_currency)
    if source == target:
        return amount
    return convert_usd_to_currency(convert_currency_to_usd(amount, source, fx_rates), target, fx_rates)


def get_portfolio_cash(portfolio: dict[str, Any]) -> float:
    if "cash" in portfolio:
        return float(portfolio.get("cash", 0.0) or 0.0)
    return float(portfolio.get("cash_usd", 0.0) or 0.0)


def build_portfolio_payload(
    as_of: str,
    cash: float,
    cash_currency: str,
    positions: list[dict[str, Any]],
) -> dict[str, Any]:
    canonical_currency = canonicalize_currency(cash_currency)
    return {
        "as_of": as_of,
        "cash": cash,
        "cash_currency": canonical_currency,
        "cash_usd": cash,
        "positions": positions,
    }


def merge_fx_rates(refreshed: dict[str, float], fallback: dict[str, float]) -> dict[str, float]:
    merged = {"USD": 1.0}
    merged.update(fallback)
    merged.update(refreshed)
    return merged


def ensure_fx_rates_available(fx_rates: dict[str, float], currencies: list[str]) -> None:
    missing = [currency for currency in currencies if canonicalize_currency(currency) not in fx_rates]
    if missing:
        joined = ", ".join(unique_ordered([canonicalize_currency(currency) for currency in missing]))
        raise ValueError(f"缺少汇率: {joined}，请先执行 refresh-prices 或取消 --skip-refresh")


def normalize_positions(portfolio: dict[str, Any]) -> dict[str, dict[str, float]]:
    positions = {}
    for pos in portfolio.get("positions", []):
        ticker = normalize_ticker(pos.get("ticker", ""))
        if not ticker:
            continue
        positions[ticker] = {
            "shares": float(pos.get("shares", 0.0) or 0.0),
            "avg_cost": float(pos.get("avg_cost", 0.0) or 0.0),
            "last_price": float(pos.get("last_price", 0.0) or 0.0),
            "market_value": float(pos.get("market_value", 0.0) or 0.0),
        }
    return positions


def tracked_tickers_for_runtime(strategy: dict[str, Any], portfolio: dict[str, Any]) -> list[str]:
    strategy_spec = parse_strategy(strategy)
    positions = normalize_positions(portfolio)
    return unique_ordered(strategy_spec["tracked_tickers"] + list(positions.keys()))


def build_category_snapshots(
    strategy: dict[str, Any], portfolio: dict[str, Any], prices: dict[str, float]
) -> tuple[list[CategorySnapshot], float, list[str]]:
    strategy_spec = parse_strategy(strategy)
    positions = normalize_positions(portfolio)
    positions_value = 0.0
    holding_cache: dict[str, HoldingSnapshot] = {}
    missing_price_tickers: list[str] = []

    for ticker in tracked_tickers_for_runtime(strategy, portfolio):
        position = positions.get(ticker, {})
        shares = float(position.get("shares", 0.0) or 0.0)
        price = float(prices.get(ticker) or position.get("last_price", 0.0) or 0.0)
        value = shares * price if price > 0 else 0.0
        holding_cache[ticker] = HoldingSnapshot(
            category_name=strategy_spec["ticker_to_group"].get(ticker, ticker),
            ticker=ticker,
            shares=shares,
            price=price,
            value=value,
        )
        positions_value += value
        if price <= 0:
            missing_price_tickers.append(ticker)

    category_specs: list[tuple[str, float, list[str]]] = []
    included_tickers: set[str] = set()

    for category_name, target_weight in strategy_spec["targets"].items():
        tickers = strategy_spec["category_to_tickers"].get(category_name, [])
        category_specs.append((category_name, target_weight, tickers))
        included_tickers.update(tickers)

    for ticker in positions.keys():
        if ticker not in included_tickers:
            category_specs.append((ticker, 0.0, [ticker]))
            included_tickers.add(ticker)

    categories: list[CategorySnapshot] = []
    for category_name, target_weight, tickers in category_specs:
        holdings = [holding_cache[ticker] for ticker in tickers if ticker in holding_cache]
        if not holdings:
            holdings = [
                HoldingSnapshot(
                    category_name=category_name,
                    ticker=ticker,
                    shares=0.0,
                    price=0.0,
                    value=0.0,
                )
                for ticker in tickers
            ]
        current_value = sum(holding.value for holding in holdings)
        current_weight = (current_value / positions_value) if positions_value > 0 else 0.0
        categories.append(
            CategorySnapshot(
                name=category_name,
                target_weight=float(target_weight),
                current_value=current_value,
                current_weight=current_weight,
                deviation=current_weight - float(target_weight),
                holdings=holdings,
            )
        )

    return categories, positions_value, unique_ordered(missing_price_tickers)


def build_rebalance_decision(strategy: dict[str, Any], categories: list[CategorySnapshot]) -> dict[str, Any]:
    rules = strategy.get("rules") or {}
    optional_threshold = float(rules.get("optional_rebalance_threshold", 0.05) or 0.05)
    mandatory_threshold = float(rules.get("mandatory_rebalance_threshold", 0.08) or 0.08)
    max_abs_deviation = max((abs(category.deviation) for category in categories), default=0.0)

    if max_abs_deviation >= mandatory_threshold:
        level = "mandatory"
        should_rebalance = True
        message = "已触发强制再平衡阈值"
    elif max_abs_deviation >= optional_threshold:
        level = "optional"
        should_rebalance = True
        message = "已触发可选再平衡阈值"
    else:
        level = "none"
        should_rebalance = False
        message = "当前未触发再平衡阈值"

    return {
        "should_rebalance": should_rebalance,
        "level": level,
        "message": message,
        "max_abs_deviation": max_abs_deviation,
        "optional_threshold": optional_threshold,
        "mandatory_threshold": mandatory_threshold,
    }


def allocate_category_amounts(categories: list[CategorySnapshot], contribution: float) -> dict[str, float]:
    underweights = {category.name: max(category.target_weight - category.current_weight, 0.0) for category in categories}
    total_under = sum(underweights.values())

    if total_under <= 0:
        total_target = sum(category.target_weight for category in categories)
        return {
            category.name: contribution * (category.target_weight / total_target if total_target > 0 else 0.0)
            for category in categories
        }

    return {
        category.name: contribution * (underweights[category.name] / total_under)
        for category in categories
    }


def split_amount_within_category(category: CategorySnapshot, amount: float) -> dict[str, float]:
    eligible_holdings = [holding for holding in category.holdings if holding.price > 0]
    amounts = {holding.ticker: 0.0 for holding in category.holdings}
    if not eligible_holdings or amount <= 0:
        return amounts

    if len(eligible_holdings) == 1:
        amounts[eligible_holdings[0].ticker] = amount
        return amounts

    held_value_total = sum(holding.value for holding in eligible_holdings if holding.value > 0)
    if held_value_total > 0:
        weights = {
            holding.ticker: (holding.value / held_value_total if holding.value > 0 else 0.0)
            for holding in eligible_holdings
        }
    else:
        equal_weight = 1.0 / len(eligible_holdings)
        weights = {holding.ticker: equal_weight for holding in eligible_holdings}

    for holding in eligible_holdings:
        amounts[holding.ticker] = amount * weights[holding.ticker]
    return amounts


def allocate_whole_shares_within_category(
    category: CategorySnapshot, desired_amounts: dict[str, float], budget: float
) -> tuple[dict[str, int], float]:
    eligible_holdings = [holding for holding in category.holdings if holding.price > 0]
    shares = {holding.ticker: 0 for holding in category.holdings}
    remaining = budget

    for holding in sorted(
        eligible_holdings,
        key=lambda item: (desired_amounts.get(item.ticker, 0.0), -item.price),
        reverse=True,
    ):
        desired_amount = desired_amounts.get(holding.ticker, 0.0)
        qty = int(min(math.floor(desired_amount / holding.price), math.floor(remaining / holding.price)))
        if qty > 0:
            shares[holding.ticker] += qty
            remaining -= qty * holding.price

    loop_guard = 0
    while remaining > 0 and loop_guard < 10000:
        loop_guard += 1
        affordable = [holding for holding in eligible_holdings if holding.price <= remaining]
        if not affordable:
            break

        remaining_gaps = {
            holding.ticker: desired_amounts.get(holding.ticker, 0.0) - shares[holding.ticker] * holding.price
            for holding in affordable
        }
        positive_gap_exists = any(gap > 0 for gap in remaining_gaps.values())
        if positive_gap_exists:
            best = max(affordable, key=lambda item: (remaining_gaps[item.ticker], -item.price))
        else:
            best = min(affordable, key=lambda item: item.price)

        shares[best.ticker] += 1
        remaining -= best.price

    return shares, remaining


def build_report(
    strategy: dict[str, Any], portfolio: dict[str, Any], prices: dict[str, float], fx_rates: dict[str, float]
) -> dict[str, Any]:
    strategy_spec = parse_strategy(strategy)
    base_currency = strategy_spec["base_currency"]
    categories, positions_value, missing_price_tickers = build_category_snapshots(strategy, portfolio, prices)
    cash = get_portfolio_cash(portfolio)
    groups = []
    usd_to_base = usd_to_currency_rate(fx_rates, base_currency)
    cash_usd = convert_currency_to_usd(cash, base_currency, fx_rates)
    total_value_usd = positions_value + cash_usd

    for category in categories:
        groups.append(
            {
                "name": category.name,
                "target_weight": category.target_weight,
                "current_value_usd": category.current_value,
                "current_value": category.current_value * usd_to_base,
                "current_weight": category.current_weight,
                "deviation": category.deviation,
                "holdings": [
                    {
                        "ticker": holding.ticker,
                        "shares": holding.shares,
                        "price_usd": holding.price,
                        "price": holding.price * usd_to_base,
                        "value_usd": holding.value,
                        "value": holding.value * usd_to_base,
                    }
                    for holding in category.holdings
                ],
            }
        )

    rebalance_decision = build_rebalance_decision(strategy, categories)
    return {
        "as_of": portfolio.get("as_of", ""),
        "base_currency": base_currency,
        "fx_rates": fx_rates,
        "positions_value_usd": positions_value,
        "positions_value": positions_value * usd_to_base,
        "cash": cash,
        "cash_currency": base_currency,
        "cash_usd": cash_usd,
        "total_value_usd": total_value_usd,
        "total_value": positions_value * usd_to_base + cash,
        "missing_price_tickers": missing_price_tickers,
        "rebalance_decision": rebalance_decision,
        "groups": groups,
    }


def build_plan(
    strategy: dict[str, Any],
    portfolio: dict[str, Any],
    prices: dict[str, float],
    fx_rates: dict[str, float],
    contribution: float,
    contribution_currency: str,
) -> dict[str, Any]:
    strategy_spec = parse_strategy(strategy)
    base_currency = strategy_spec["base_currency"]
    usd_to_base = usd_to_currency_rate(fx_rates, base_currency)
    categories, positions_value, missing_price_tickers = build_category_snapshots(strategy, portfolio, prices)
    cash = get_portfolio_cash(portfolio)
    contribution_usd = convert_currency_to_usd(contribution, contribution_currency, fx_rates)
    category_buy_amounts = {category.name: 0.0 for category in categories}
    if categories:
        category_buy_amounts.update(allocate_category_amounts(categories, contribution_usd))

    groups = []
    whole_remaining_cash_usd = contribution_usd
    after_positions_value = positions_value + contribution_usd

    for category in categories:
        category_fractional_amount = category_buy_amounts.get(category.name, 0.0)
        holding_fractional_amounts = split_amount_within_category(category, category_fractional_amount)
        whole_shares, category_remaining_cash = allocate_whole_shares_within_category(
            category,
            holding_fractional_amounts,
            category_fractional_amount,
        )
        whole_remaining_cash_usd -= category_fractional_amount - category_remaining_cash

        whole_current_value = category.current_value
        fractional_current_value = category.current_value
        holdings = []
        for holding in category.holdings:
            buy_amount_whole = whole_shares.get(holding.ticker, 0) * holding.price
            buy_amount_fractional = holding_fractional_amounts.get(holding.ticker, 0.0)
            whole_current_value += buy_amount_whole
            fractional_current_value += buy_amount_fractional
            holdings.append(
                {
                    "ticker": holding.ticker,
                    "shares": holding.shares,
                    "price_usd": holding.price,
                    "price": holding.price * usd_to_base,
                    "value_usd": holding.value,
                    "value": holding.value * usd_to_base,
                    "buy_amount_whole_usd": buy_amount_whole,
                    "buy_amount_whole": buy_amount_whole * usd_to_base,
                    "buy_shares_whole": whole_shares.get(holding.ticker, 0),
                    "buy_amount_fractional_usd": buy_amount_fractional,
                    "buy_amount_fractional": buy_amount_fractional * usd_to_base,
                    "buy_shares_fractional": (buy_amount_fractional / holding.price if holding.price > 0 else 0.0),
                }
            )

        groups.append(
            {
                "name": category.name,
                "target_weight": category.target_weight,
                "current_value_usd": category.current_value,
                "current_value": category.current_value * usd_to_base,
                "current_weight": category.current_weight,
                "deviation": category.deviation,
                "buy_amount_whole_usd": sum(item["buy_amount_whole_usd"] for item in holdings),
                "buy_amount_whole": sum(item["buy_amount_whole"] for item in holdings),
                "buy_amount_fractional_usd": sum(item["buy_amount_fractional_usd"] for item in holdings),
                "buy_amount_fractional": sum(item["buy_amount_fractional"] for item in holdings),
                "post_weight_whole": (whole_current_value / after_positions_value if after_positions_value > 0 else 0.0),
                "post_weight_fractional": (
                    fractional_current_value / after_positions_value if after_positions_value > 0 else 0.0
                ),
                "holdings": holdings,
            }
        )

    rebalance_decision = build_rebalance_decision(strategy, categories)
    return {
        "as_of": portfolio.get("as_of", ""),
        "base_currency": base_currency,
        "fx_rates": fx_rates,
        "positions_value_usd": positions_value,
        "positions_value": positions_value * usd_to_base,
        "cash": cash,
        "cash_currency": base_currency,
        "cash_usd": convert_currency_to_usd(cash, base_currency, fx_rates),
        "total_value_before_usd": positions_value + convert_currency_to_usd(cash, base_currency, fx_rates),
        "total_value_before": positions_value * usd_to_base + cash,
        "contribution_input": contribution,
        "contribution_currency": canonicalize_currency(contribution_currency, default=base_currency),
        "contribution_usd": contribution_usd,
        "contribution": convert_usd_to_currency(contribution_usd, base_currency, fx_rates),
        "after_positions_value_usd": after_positions_value,
        "after_positions_value": after_positions_value * usd_to_base,
        "total_value_after_usd": positions_value + convert_currency_to_usd(cash, base_currency, fx_rates) + contribution_usd,
        "total_value_after": positions_value * usd_to_base + cash + convert_usd_to_currency(contribution_usd, base_currency, fx_rates),
        "whole_remaining_cash_usd": whole_remaining_cash_usd,
        "whole_remaining_cash": whole_remaining_cash_usd * usd_to_base,
        "missing_price_tickers": missing_price_tickers,
        "rebalance_decision": rebalance_decision,
        "groups": groups,
    }


def print_report(report: dict[str, Any]) -> None:
    base_currency = report.get("base_currency", "CNY")
    print("=" * 110)
    print("投资组合报告")
    print("=" * 110)
    print(f"日期: {report.get('as_of', 'N/A')}")
    print(f"结算货币: {base_currency}")
    print(f"持仓合计: {report['positions_value']:.2f} {base_currency}")
    print(f"现金:     {report['cash']:.2f} {base_currency}")
    print(f"总资产:   {report['total_value']:.2f} {base_currency}\n")
    decision = report.get("rebalance_decision") or {}
    if decision:
        print(
            "再平衡判断: "
            f"{decision.get('message', '')} | "
            f"当前最大偏差 {float(decision.get('max_abs_deviation', 0.0))*100:.2f}% | "
            f"可选阈值 {float(decision.get('optional_threshold', 0.0))*100:.2f}% | "
            f"强制阈值 {float(decision.get('mandatory_threshold', 0.0))*100:.2f}%"
        )
        print("")
    if report.get("missing_price_tickers"):
        print(f"缺少价格: {', '.join(report['missing_price_tickers'])}\n")

    print(f"类别 | Ticker | 股数 | 现价({base_currency}) | 市值({base_currency}) | 当前占比 | 目标占比 | 偏差")
    print("-" * 110)
    for group in report["groups"]:
        for holding in group["holdings"]:
            print(
                f"{group['name']:12s} | "
                f"{holding['ticker']:8s} | "
                f"{holding['shares']:8.4f} | "
                f"{holding['price']:12.2f} | "
                f"{holding['value']:12.2f} | "
                f"{'':8s} | "
                f"{'':8s} | "
                f"{'':8s}"
            )
        print(
            f"{(group['name'] + ' 小计'):12s} | "
            f"{'-':8s} | "
            f"{'-':8s} | "
            f"{'-':8s} | "
            f"{group['current_value']:12.2f} | "
            f"{group['current_weight']*100:7.2f}% | "
            f"{group['target_weight']*100:7.2f}% | "
            f"{group['deviation']*100:+7.2f}%"
        )
        print("-" * 110)


def print_plan(plan: dict[str, Any]) -> None:
    base_currency = plan.get("base_currency", "CNY")
    print("=" * 120)
    print("本月补仓计划（分组规则型，不择时）")
    print("=" * 120)
    print(f"结算货币:     {base_currency}")
    print(f"买前持仓合计: {plan['positions_value']:.2f} {base_currency}")
    print(f"现金:         {plan['cash']:.2f} {base_currency}")
    print(f"买前总资产:   {plan['total_value_before']:.2f} {base_currency}")
    print(
        f"本月投入:     {plan['contribution_input']:.2f} {plan['contribution_currency']} "
        f"(折合 {plan['contribution']:.2f} {base_currency})"
    )
    print(f"买后总资产:   {plan['total_value_after']:.2f} {base_currency}\n")
    decision = plan.get("rebalance_decision") or {}
    if decision:
        print(
            "再平衡判断: "
            f"{decision.get('message', '')} | "
            f"当前最大偏差 {float(decision.get('max_abs_deviation', 0.0))*100:.2f}% | "
            f"可选阈值 {float(decision.get('optional_threshold', 0.0))*100:.2f}% | "
            f"强制阈值 {float(decision.get('mandatory_threshold', 0.0))*100:.2f}%"
        )
        print("")
    if plan.get("missing_price_tickers"):
        print(f"缺少价格，以下资产未纳入完整建议: {', '.join(plan['missing_price_tickers'])}\n")

    print(f"类别 | 当前占比 | 目标占比 | 偏差 | 整股买入({base_currency}) | 碎股买入({base_currency}) | 整股买后占比 | 碎股买后占比")
    print("-" * 120)
    for group in plan["groups"]:
        print(
            f"{group['name']:12s} | "
            f"{group['current_weight']*100:7.2f}% | "
            f"{group['target_weight']*100:7.2f}% | "
            f"{group['deviation']*100:+7.2f}% | "
            f"{group['buy_amount_whole']:14.2f} | "
            f"{group['buy_amount_fractional']:14.2f} | "
            f"{group['post_weight_whole']*100:9.2f}% | "
            f"{group['post_weight_fractional']*100:9.2f}%"
        )
        for holding in group["holdings"]:
            print(
                f"{'':12s} | "
                f"{holding['ticker']:8s} | "
                f"shares {holding['shares']:8.4f} | "
                f"price {holding['price']:8.2f} | "
                f"整股 {holding['buy_amount_whole']:8.2f} ({holding['buy_shares_whole']:4d}) | "
                f"碎股 {holding['buy_amount_fractional']:8.2f} ({holding['buy_shares_fractional']:8.4f})"
            )
        print("-" * 120)

    print(f"整股方案剩余现金: {plan['whole_remaining_cash']:.2f} {base_currency}")


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


def fetch_fx_rates() -> dict[str, float]:
    try:
        import yfinance as yf
    except ImportError as exc:  # noqa: BLE001
        raise RuntimeError("未安装 yfinance，无法刷新汇率") from exc

    rates = {"USD": 1.0}
    pair_specs = {
        "CNY": ("CNY=X", "direct"),
        "JPY": ("JPY=X", "direct"),
        "GBP": ("GBPUSD=X", "inverse"),
    }

    for currency, (ticker, mode) in pair_specs.items():
        try:
            ticker_obj = yf.Ticker(ticker)
            fast_price = getattr(ticker_obj, "fast_info", {}).get("lastPrice")
            if fast_price:
                raw_rate = float(fast_price)
            else:
                history = ticker_obj.history(period="1d")
                if history.empty:
                    raise ValueError("history empty")
                raw_rate = float(history["Close"].iloc[-1])
            rates[currency] = raw_rate if mode == "direct" else (1.0 / raw_rate if raw_rate > 0 else 0.0)
        except Exception as exc:  # noqa: BLE001
            print(f"[警告] 获取 {currency} 汇率失败: {exc}")
    return rates


def command_init(args: argparse.Namespace) -> dict[str, Any]:
    workspace = resolve_workspace(args.workspace)
    paths = ensure_workspace_files(workspace)
    current_strategy = load_yaml(paths["strategy"])
    strategy, strategy_mode = build_strategy_from_init_args(args, current_strategy)
    write_yaml(paths["strategy"], strategy)
    strategy_spec = parse_strategy(strategy)
    positions = build_positions(strategy, args.holding or [])
    base_currency = strategy_spec["base_currency"]
    cash_currency = canonicalize_currency(args.cash_currency or base_currency, default=base_currency)
    cached_fx_rates = load_fx_rates(paths["prices"])
    fx_rates = cached_fx_rates
    if cash_currency != base_currency:
        try:
            fx_rates = merge_fx_rates(fetch_fx_rates(), cached_fx_rates)
        except Exception as exc:  # noqa: BLE001
            if cash_currency not in cached_fx_rates or base_currency not in cached_fx_rates:
                raise RuntimeError("初始化需要汇率，但当前无法刷新汇率") from exc
        ensure_fx_rates_available(fx_rates, [base_currency, cash_currency])
    cash = float(args.cash or 0.0)
    cash_in_base = convert_amount(cash, cash_currency, base_currency, fx_rates)

    portfolio = build_portfolio_payload(args.as_of or str(date.today()), cash_in_base, base_currency, positions)
    write_yaml(paths["portfolio"], portfolio)

    return {
        "workspace": str(workspace),
        "strategy_path": str(paths["strategy"]),
        "portfolio_path": str(paths["portfolio"]),
        "strategy_mode": strategy_mode,
        "base_currency": base_currency,
        "input_cash": cash,
        "input_cash_currency": cash_currency,
        "cash": portfolio["cash"],
        "cash_currency": portfolio["cash_currency"],
        "optional_rebalance_threshold": float((strategy.get("rules") or {}).get("optional_rebalance_threshold", 0.05) or 0.05),
        "mandatory_rebalance_threshold": float((strategy.get("rules") or {}).get("mandatory_rebalance_threshold", 0.08) or 0.08),
        "positions_count": len(positions),
    }


def command_sync_holdings(args: argparse.Namespace) -> dict[str, Any]:
    return command_init(args)


def command_update_rules(args: argparse.Namespace) -> dict[str, Any]:
    workspace = resolve_workspace(args.workspace)
    paths = ensure_workspace_files(workspace)
    strategy = load_yaml(paths["strategy"]) or load_yaml(DEFAULT_STRATEGY_TEMPLATE)

    if args.optional_rebalance_threshold is None and args.mandatory_rebalance_threshold is None:
        raise ValueError("至少提供一个再平衡阈值参数")

    strategy = apply_rebalance_rule_overrides(
        strategy,
        args.optional_rebalance_threshold,
        args.mandatory_rebalance_threshold,
    )
    write_yaml(paths["strategy"], strategy)

    rules = strategy.get("rules") or {}
    return {
        "workspace": str(workspace),
        "strategy_path": str(paths["strategy"]),
        "optional_rebalance_threshold": float(rules.get("optional_rebalance_threshold", 0.05) or 0.05),
        "mandatory_rebalance_threshold": float(rules.get("mandatory_rebalance_threshold", 0.08) or 0.08),
    }


def command_refresh_prices(args: argparse.Namespace) -> dict[str, Any]:
    workspace = resolve_workspace(args.workspace)
    paths = ensure_workspace_files(workspace)
    strategy = load_yaml(paths["strategy"])
    portfolio = load_yaml(paths["portfolio"])
    existing_cache = load_price_cache(paths["prices"])
    existing_fx_rates = load_fx_rates(paths["prices"])

    tracked_tickers = tracked_tickers_for_runtime(strategy, portfolio)
    portfolio_positions = normalize_positions(portfolio)
    now = datetime.now(timezone.utc).isoformat()
    updated: dict[str, dict[str, Any]] = {}
    refreshed: list[str] = []
    fallback: list[str] = []
    missing: list[str] = []

    for ticker in tracked_tickers:
        price = fetch_price_for_ticker(ticker)
        if price is not None:
            updated[ticker] = {"price": price, "timestamp": now, "source": "yfinance"}
            refreshed.append(ticker)
            continue

        cached_price = existing_cache.get(ticker, {}).get("price")
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

    try:
        refreshed_fx_rates = fetch_fx_rates()
        fx_source = "yfinance"
    except Exception as exc:  # noqa: BLE001
        print(f"[警告] 获取汇率失败: {exc}")
        refreshed_fx_rates = {}
        fx_source = "cache_fallback"

    fx_rates = merge_fx_rates(refreshed_fx_rates, existing_fx_rates)
    write_price_cache(paths["prices"], updated, fx_rates, now)
    return {
        "workspace": str(workspace),
        "price_cache_path": str(paths["prices"]),
        "refreshed": refreshed,
        "fallback": fallback,
        "missing": missing,
        "prices": updated,
        "fx_rates": fx_rates,
        "fx_source": fx_source,
    }


def maybe_refresh_prices(workspace: Path, skip_refresh: bool) -> dict[str, Any] | None:
    if skip_refresh:
        return None
    refresh_args = argparse.Namespace(workspace=str(workspace), json=False)
    return command_refresh_prices(refresh_args)


def command_report(args: argparse.Namespace) -> dict[str, Any]:
    workspace = resolve_workspace(args.workspace)
    paths = ensure_workspace_files(workspace)
    refresh_result = maybe_refresh_prices(workspace, args.skip_refresh)
    strategy = load_yaml(paths["strategy"])
    portfolio = load_yaml(paths["portfolio"])
    prices = load_prices(paths["prices"])
    fx_rates = load_fx_rates(paths["prices"])
    report = build_report(strategy, portfolio, prices, fx_rates)
    report["price_refresh"] = refresh_result
    return report


def command_rebalance(args: argparse.Namespace) -> dict[str, Any]:
    if args.contribution < 0:
        raise ValueError("contribution 必须 >= 0")
    workspace = resolve_workspace(args.workspace)
    paths = ensure_workspace_files(workspace)
    refresh_result = maybe_refresh_prices(workspace, args.skip_refresh)
    strategy = load_yaml(paths["strategy"])
    portfolio = load_yaml(paths["portfolio"])
    prices = load_prices(paths["prices"])
    fx_rates = load_fx_rates(paths["prices"])
    strategy_spec = parse_strategy(strategy)
    contribution_currency = canonicalize_currency(
        args.contribution_currency or strategy_spec["base_currency"],
        default=strategy_spec["base_currency"],
    )
    plan = build_plan(strategy, portfolio, prices, fx_rates, args.contribution, contribution_currency)
    plan["price_refresh"] = refresh_result
    return plan


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
    init_parser.add_argument("--cash-currency", type=str, default=None)
    init_parser.add_argument("--base-currency", type=str, default=None)
    init_parser.add_argument("--optional-rebalance-threshold", type=float, default=None)
    init_parser.add_argument("--mandatory-rebalance-threshold", type=float, default=None)
    init_parser.add_argument("--as-of", type=str, default=None)
    init_parser.add_argument("--group", action="append", default=[])
    init_parser.add_argument("--target", action="append", default=[])
    init_parser.add_argument("--holding", action="append", default=[])
    init_parser.add_argument("--json", action="store_true")

    sync_parser = subparsers.add_parser("sync-holdings", help="覆盖同步当前持仓")
    sync_parser.add_argument("--workspace", type=str, default=None)
    sync_parser.add_argument("--cash", type=float, default=0.0)
    sync_parser.add_argument("--cash-currency", type=str, default=None)
    sync_parser.add_argument("--base-currency", type=str, default=None)
    sync_parser.add_argument("--optional-rebalance-threshold", type=float, default=None)
    sync_parser.add_argument("--mandatory-rebalance-threshold", type=float, default=None)
    sync_parser.add_argument("--as-of", type=str, default=None)
    sync_parser.add_argument("--group", action="append", default=[])
    sync_parser.add_argument("--target", action="append", default=[])
    sync_parser.add_argument("--holding", action="append", default=[])
    sync_parser.add_argument("--json", action="store_true")

    refresh_parser = subparsers.add_parser("refresh-prices", help="刷新目标资产价格")
    refresh_parser.add_argument("--workspace", type=str, default=None)
    refresh_parser.add_argument("--json", action="store_true")

    update_rules_parser = subparsers.add_parser("update-rules", help="更新再平衡阈值")
    update_rules_parser.add_argument("--workspace", type=str, default=None)
    update_rules_parser.add_argument("--optional-rebalance-threshold", type=float, default=None)
    update_rules_parser.add_argument("--mandatory-rebalance-threshold", type=float, default=None)
    update_rules_parser.add_argument("--json", action="store_true")

    report_parser = subparsers.add_parser("report", help="查看当前组合")
    report_parser.add_argument("--workspace", type=str, default=None)
    report_parser.add_argument("--skip-refresh", action="store_true")
    report_parser.add_argument("--json", action="store_true")

    rebalance_parser = subparsers.add_parser("rebalance", help="生成补仓建议")
    rebalance_parser.add_argument("--workspace", type=str, default=None)
    rebalance_parser.add_argument("--contribution", type=float, required=True)
    rebalance_parser.add_argument("--contribution-currency", type=str, default=None)
    rebalance_parser.add_argument("--skip-refresh", action="store_true")
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

    if args.command == "update-rules":
        payload = command_update_rules(args)
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
