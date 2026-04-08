---
name: portfolio-assistant
description: Use this skill when the user wants rule-based portfolio contribution or rebalance suggestions. On first use, if the skill directory has no local data/portfolio.yaml, ask the user for default settlement currency, current holdings, and cash, initialize data/portfolio.yaml, then later answer requests like "这个月我要投入5000美元，各个资产应该怎么投" by reading the saved holdings, refreshing current prices and FX rates, and running the bundled scripts for all numeric conclusions.
---

# Portfolio Assistant

这是一个可安装到任意项目的规则型投资仓位计算 skill，不是择时系统。

## 什么时候使用

当用户提出以下类型的请求时使用本 skill：

- “这个月我要投入 5000 美元，各个资产应该怎么投”
- “看看我当前仓位和目标仓位差多少”
- “按我现在的持仓，给我本月补仓建议”
- “第一次用，帮我把当前持仓录进去”
- “刷新价格后重新算一遍”

## 存储位置

这个 skill 默认把状态直接存到 skill 自己目录下：

- `data/strategy.yaml`
- `data/portfolio.yaml`
- `data/price_cache.json`

这样脚本和生成的数据就在同一个 skill 文件夹里，不再分成两个地方。

如确有需要，也可以显式传 `--workspace <path>` 覆盖默认位置。

## 首次使用流程

当 `data/portfolio.yaml` 不存在，或用户明确说“第一次用”时：

1. 先询问用户这次要：
   - 使用默认投资组合方案
   - 还是提供自己的组合方案
2. 询问用户默认结算货币，默认用人民币 `CNY`。
   - 人民币 / 元 / RMB / CNY => `CNY`
   - 美元 / 美金 / 刀 / USD / $ => `USD`
   - 英镑 / GBP => `GBP`
   - 日元 / JPY / YEN => `JPY`
3. 如果用户选择自定义组合方案，先收集：
   - 组定义 `groups`
   - 目标权重 `targets`
4. 然后再收集持仓和现金，最少包括：
   - 现金金额
   - 现金币种；如果用户没说，默认按结算货币处理
   - 每个资产的 `ticker`
   - 持有股数 `shares`
   - 可选：`avg_cost`
   - 可选：最近价格 `last_price`
5. 再询问再平衡阈值；如果用户没说，默认：
   - 可选再平衡阈值 `0.05`
   - 强制再平衡阈值 `0.08`
6. 不要自己猜持仓，不要从截图默认识别，除非用户明确要求。
7. 收集完成后，运行：

```bash
python scripts/portfolio_assistant.py init \
  --base-currency CNY \
  --cash <现金> \
  --cash-currency CNY \
  --optional-rebalance-threshold 0.05 \
  --mandatory-rebalance-threshold 0.08 \
  --holding 'VOO,10,500,520' \
  --holding 'QQQM,8,180,190'
```

说明：

- `holding` 格式是 `ticker,shares[,avg_cost[,last_price]]`
- 自定义 group 格式是 `组名=TICKER1,TICKER2`
- 自定义 target 格式是 `目标名=0.20`
- 结算货币用 `--base-currency`
- 现金币种用 `--cash-currency`
- 再平衡阈值用 `--optional-rebalance-threshold` 和 `--mandatory-rebalance-threshold`
- 如果用户没提供 `avg_cost` 或 `last_price`，可以省略后两项
- 如果没传 `--group` / `--target`，`init` 会自动写入默认策略模板
- 如果传了 `--group` / `--target`，`init` 会在默认模板基础上改成用户给出的组合方案
- 默认模板策略支持 `groups`，可以把多个 ticker 归到同一资产类别

如果需要字段口径，读取 `references/data-contract.md`。

## 后续默认工作流

### 1. 读取已保存持仓

优先读取：

- `data/strategy.yaml`
- `data/portfolio.yaml`

### 2. 价格处理

如果请求涉及当前占比、偏差、补仓金额、买入股数：

- 默认先刷新价格和汇率，再基于最新结果计算
- 脚本会优先尝试在线拉取；失败时回退到已有缓存或 `last_price`
- 如确实不想刷新，才显式传 `--skip-refresh`

```bash
python scripts/portfolio_assistant.py refresh-prices
```

### 3. 生成补仓建议

当用户给出本次投入金额时，运行：

```bash
python scripts/portfolio_assistant.py rebalance --contribution 5000 --contribution-currency USD
```

需要机器可读结果时，加 `--json`。

如果 `strategy.yaml` 定义了 `groups`：

- 报告和偏差先按组级别计算
- 现金不参与占比
- 组内 ticker 再按脚本规则拆分建议金额
- 脚本还会根据最大组偏差判断是否触发再平衡，并区分“可选 / 强制”

### 4. 查看当前组合

```bash
python scripts/portfolio_assistant.py report
```

### 5. 覆盖同步当前持仓

如果用户之后明确要重录当前持仓，使用：

```bash
python scripts/portfolio_assistant.py sync-holdings \
  --cash <现金> \
  --cash-currency CNY \
  --holding 'VOO,12,505,530'
```

### 6. 修改再平衡阈值

如果用户后续说“把可选再平衡改成 4%，强制改成 7%”，运行：

```bash
python scripts/portfolio_assistant.py update-rules \
  --optional-rebalance-threshold 0.04 \
  --mandatory-rebalance-threshold 0.07
```

## 强约束

- 不做主观择时，不预测涨跌。
- 所有数字结论必须来自脚本计算，不允许手算。
- 首次缺少持仓时，必须先问用户，不能臆造仓位。
- 若价格刷新失败且无缓存，要明确说明价格不足，不能编造当前价。
- 用户没要求时，不要改策略；默认使用模板策略或现有 `strategy.yaml`。

## 输出要求

- 默认用中文。
- 先给结论，再给关键依据。
- 明确说明数据来源：
  - skill 目录下保存的持仓文件
  - 当前价格缓存 / 汇率缓存或刷新结果
  - 脚本计算结果
- 当首次初始化完成时，要告诉用户后续他只需直接说：
  - “这个月我要投入 5000 美元，各个资产应该怎么投”
