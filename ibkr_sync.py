#!/usr/bin/env python3
"""IBKR 持仓同步脚手架。

说明:
- 这是一个最小可运行模板，用于后续接入 ib_insync 或官方 API。
- 当前版本只演示配置加载和输出，不会真的连接 IBKR。
"""

from __future__ import annotations

import argparse
from pathlib import Path



def _load_yaml_module():
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError as exc:
        raise SystemExit("缺少依赖: PyYAML。请先执行 `pip install pyyaml`。") from exc
    return yaml


def load_portfolio(path: Path) -> dict:
    yaml = _load_yaml_module()
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="IBKR sync scaffold")
    parser.add_argument("--portfolio", type=Path, default=Path("portfolio.yaml"))
    parser.add_argument("--dry-run", action="store_true", default=True)
    args = parser.parse_args()

    data = load_portfolio(args.portfolio)
    account = data.get("account", {})
    print("[IBKR SYNC] 初始化完成")
    print(f"账户: {account.get('account_id', 'N/A')}")
    print("当前为模板模式：未发起真实连接。")
    if args.dry_run:
        print("dry-run = True")


if __name__ == "__main__":
    main()
