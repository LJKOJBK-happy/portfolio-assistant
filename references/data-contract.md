# Data Contract

这个 skill 默认把数据放在 skill 自己目录下的 `data/`。

## 持久化文件

### `data/strategy.yaml`

默认由 skill 模板生成，也可以由用户后续手工调整。

主要字段：

- `base_currency`
- `groups`
- `targets`
- `rules`
- `notes`

其中：

- `groups` 是 `组名 -> ticker 列表` 的映射
- `targets` 是 `组名或独立 ticker -> 目标权重` 的映射
- `rules` 描述补仓偏好，如优先买低配、偏好整股、是否支持碎股
- 其中再平衡阈值主要用：
  - `rules.optional_rebalance_threshold`
  - `rules.mandatory_rebalance_threshold`

### `data/portfolio.yaml`

首次使用时由用户提供持仓，skill 写入。

主要字段：

- `as_of`
- `cash`
- `cash_currency`
- `positions`

`positions` 中每项通常包含：

- `ticker`
- `shares`
- `avg_cost`
- `last_price`
- `market_value`

### `data/price_cache.json`

由 `refresh-prices` 子命令生成。

示例：

```json
{
  "_meta": {
    "timestamp": "2026-04-08T12:00:00+00:00",
    "fx_rates": {
      "USD": 1,
      "CNY": 7.23,
      "GBP": 0.79,
      "JPY": 151.2
    }
  },
  "VOO": {
    "price": 520.12,
    "timestamp": "2026-04-08T12:00:00+00:00",
    "source": "yfinance"
  }
}
```

## 覆盖默认位置

默认写入 skill 根目录下的 `data/`。如果调用方确实想把数据存到别处，可以显式传：

```bash
python scripts/portfolio_assistant.py report --workspace /path/to/another-dir
```

此时实际文件位置会变成：

- `/path/to/another-dir/data/strategy.yaml`
- `/path/to/another-dir/data/portfolio.yaml`
- `/path/to/another-dir/data/price_cache.json`

## 初始化口径

首次初始化时，先问用户是：

- 使用默认策略模板
- 还是提供自己的组合方案
- 默认结算货币是什么；若用户没说，默认 `CNY`
- 再平衡阈值是什么；若用户没说，默认可选 `0.05`、强制 `0.08`

货币归一化口径：

- 人民币 / 元 / RMB / CNY => `CNY`
- 美元 / 美金 / 刀 / USD / $ => `USD`
- 英镑 / GBP => `GBP`
- 日元 / JPY / YEN => `JPY`

如果用户提供自己的组合方案，可传：

- `--group '组名=TICKER1,TICKER2'`
- `--target '目标名=0.20'`
- `--base-currency CNY`
- `--optional-rebalance-threshold 0.05`
- `--mandatory-rebalance-threshold 0.08`

然后再收集持仓，优先让用户提供：

- `ticker`
- `shares`
- `cash`
- `cash_currency`

以下字段可选：

- `avg_cost`
- `last_price`

如果用户没有提供 `last_price`，后续再通过价格刷新获取。

## 计算口径

- 报告与补仓建议中的占比、偏差、买入金额、买入股数、买后占比必须来自脚本。
- `report` 和 `rebalance` 默认都会先刷新价格和汇率；仅在显式传 `--skip-refresh` 时跳过。
- 占比分母是持仓市值合计，不含现金；现金只在总资产层面单独展示。
- 若某个目标类别是 group，则先按 group 级别计算当前占比和偏差，再拆分到组内 ticker。
- 组内拆分默认规则：
  - 碎股方案优先按组内现有市值比例维持内部结构
  - 若组内当前都未持有，则按有价格的 ticker 等权拆分
  - 整股方案在组内预算下按目标金额缺口贪心分配，缺口相近时优先更便宜的 ticker
- 价格优先使用 `price_cache.json`；缺失时回退到 `portfolio.yaml` 中的 `last_price`。
- 汇率优先使用 `price_cache.json` 中 `_meta.fx_rates`；默认支持 `CNY / USD / GBP / JPY`。
- 持仓现金在 `portfolio.yaml` 中按策略 `base_currency` 落盘；若用户输入的现金币种不同，脚本会先换汇再保存。
- `rebalance --contribution` 支持额外传 `--contribution-currency`，先换算到基准货币后再计算建议。
- 再平衡判断基于组级别最大绝对偏差，阈值来自 `rules.optional_rebalance_threshold` 与 `rules.mandatory_rebalance_threshold`。
- 若用户后续想单独修改再平衡阈值，可运行 `update-rules`，不需要重录持仓。
- 若某资产既无缓存价也无 `last_price`，脚本会把该资产价格视为不可用，agent 需要明确告知用户。
- 展示层允许格式化或四舍五入，但不能篡改脚本结果。
