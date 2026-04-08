# Data Contract

这个 skill 在任意项目中都把数据放在当前工作目录下的 `.portfolio-assistant/`。

## 持久化文件

### `.portfolio-assistant/data/strategy.yaml`

默认由 skill 模板生成，也可以由用户后续手工调整。

主要字段：

- `base_currency`
- `targets`
- `rules`
- `notes`

其中：

- `targets` 是 `ticker -> 目标权重` 的映射
- `rules` 描述补仓偏好，如优先买低配、偏好整股、是否支持碎股

### `.portfolio-assistant/data/portfolio.yaml`

首次使用时由用户提供持仓，skill 写入。

主要字段：

- `as_of`
- `cash_usd`
- `positions`

`positions` 中每项通常包含：

- `ticker`
- `shares`
- `avg_cost`
- `last_price`
- `market_value`

### `.portfolio-assistant/data/price_cache.json`

由 `refresh-prices` 子命令生成。

示例：

```json
{
  "VOO": {
    "price": 520.12,
    "timestamp": "2026-04-08T12:00:00+00:00",
    "source": "yfinance"
  }
}
```

## 初始化口径

首次收集持仓时，优先让用户提供：

- `ticker`
- `shares`
- `cash`

以下字段可选：

- `avg_cost`
- `last_price`

如果用户没有提供 `last_price`，后续再通过价格刷新获取。

## 计算口径

- 占比、偏差、买入金额、买入股数、买后占比必须来自脚本。
- 价格优先使用 `price_cache.json`；缺失时回退到 `portfolio.yaml` 中的 `last_price`。
- 若某资产既无缓存价也无 `last_price`，脚本会把该资产价格视为不可用，agent 需要明确告知用户。
- 展示层允许格式化或四舍五入，但不能篡改脚本结果。
