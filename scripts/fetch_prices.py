#!/usr/bin/env python3
"""抓取策略中全部 ticker 的最新价格，并写入本地缓存。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_PATH = ROOT / "data" / "strategy.yaml"
CACHE_PATH = ROOT / "data" / "price_cache.json"


def load_targets() -> list[str]:
    import yaml

    with STRATEGY_PATH.open("r", encoding="utf-8") as f:
        strategy = yaml.safe_load(f) or {}
    targets = strategy.get("targets", {})
    if not targets:
        raise ValueError("strategy.yaml 中未找到 targets 配置")
    return list(targets.keys())


def fetch_price_for_ticker(ticker: str) -> float | None:
    """优先尝试 fast_info，失败后回退到 history。"""
    try:
        tk = yf.Ticker(ticker)
        fast_price = getattr(tk, "fast_info", {}).get("lastPrice")
        if fast_price:
            return float(fast_price)

        hist = tk.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception as exc:  # noqa: BLE001
        print(f"[警告] 获取 {ticker} 价格失败: {exc}")
    return None


def load_existing_cache() -> Dict[str, dict]:
    if not CACHE_PATH.exists():
        return {}
    try:
        with CACHE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def main() -> None:
    tickers = load_targets()
    existing = load_existing_cache()
    updated: Dict[str, dict] = {}

    now = datetime.now(timezone.utc).isoformat()
    print("开始获取最新价格...\n")

    for t in tickers:
        price = fetch_price_for_ticker(t)
        if price is None:
            old = existing.get(t, {}).get("price")
            if old is not None:
                updated[t] = {"price": float(old), "timestamp": now, "source": "cache_fallback"}
                print(f"{t:5s}: {old:.4f} USD  (缓存回退)")
            else:
                print(f"{t:5s}: 获取失败（且无缓存）")
            continue

        updated[t] = {"price": price, "timestamp": now, "source": "yfinance"}
        print(f"{t:5s}: {price:.4f} USD")

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_PATH.open("w", encoding="utf-8") as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)

    print(f"\n已写入价格缓存: {CACHE_PATH}")


if __name__ == "__main__":
    main()
