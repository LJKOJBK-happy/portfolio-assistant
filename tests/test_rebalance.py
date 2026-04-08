from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from rebalance import build_plan  # noqa: E402


def make_strategy():
    return {
        "targets": {
            "VOO": 0.5,
            "QQQM": 0.3,
            "TLT": 0.2,
        }
    }


def make_portfolio(positions):
    return {"cash_usd": 0.0, "positions": positions}


def test_empty_portfolio_with_contribution():
    strategy = make_strategy()
    portfolio = make_portfolio(
        [
            {"ticker": "VOO", "shares": 0, "last_price": 100},
            {"ticker": "QQQM", "shares": 0, "last_price": 50},
            {"ticker": "TLT", "shares": 0, "last_price": 80},
        ]
    )
    prices = {"VOO": 100, "QQQM": 50, "TLT": 80}

    plan = build_plan(strategy, portfolio, prices, contribution=1000)

    assert plan["before_total_value"] == 0
    rows = {r["ticker"]: r for r in plan["rows"]}
    assert rows["VOO"]["buy_amount_fractional"] == 500
    assert rows["QQQM"]["buy_amount_fractional"] == 300
    assert rows["TLT"]["buy_amount_fractional"] == 200


def test_severe_underweight_asset_gets_more_budget():
    strategy = make_strategy()
    portfolio = make_portfolio(
        [
            {"ticker": "VOO", "shares": 10, "last_price": 100},
            {"ticker": "QQQM", "shares": 1, "last_price": 50},
            {"ticker": "TLT", "shares": 1, "last_price": 80},
        ]
    )
    prices = {"VOO": 100, "QQQM": 50, "TLT": 80}

    plan = build_plan(strategy, portfolio, prices, contribution=500)
    rows = {r["ticker"]: r for r in plan["rows"]}

    assert rows["QQQM"]["buy_amount_fractional"] > rows["VOO"]["buy_amount_fractional"]
    assert rows["TLT"]["buy_amount_fractional"] > rows["VOO"]["buy_amount_fractional"]


def test_small_contribution_cannot_buy_whole_share():
    strategy = make_strategy()
    portfolio = make_portfolio(
        [
            {"ticker": "VOO", "shares": 0, "last_price": 400},
            {"ticker": "QQQM", "shares": 0, "last_price": 300},
            {"ticker": "TLT", "shares": 0, "last_price": 200},
        ]
    )
    prices = {"VOO": 400, "QQQM": 300, "TLT": 200}

    plan = build_plan(strategy, portfolio, prices, contribution=50)
    assert sum(r["buy_shares_whole"] for r in plan["rows"]) == 0


def test_fractional_plan_outputs_nonzero_shares_when_possible():
    strategy = make_strategy()
    portfolio = make_portfolio(
        [
            {"ticker": "VOO", "shares": 0, "last_price": 100},
            {"ticker": "QQQM", "shares": 0, "last_price": 100},
            {"ticker": "TLT", "shares": 0, "last_price": 100},
        ]
    )
    prices = {"VOO": 100, "QQQM": 100, "TLT": 100}

    plan = build_plan(strategy, portfolio, prices, contribution=90)
    assert any(r["buy_shares_fractional"] > 0 for r in plan["rows"])
