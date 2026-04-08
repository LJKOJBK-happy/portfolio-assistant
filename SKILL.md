---
name: portfolio-assistant
description: Use this skill when the user wants rule-based portfolio contribution or rebalance suggestions in any project workspace. On first use, if the workspace has no stored holdings, ask the user for current holdings and cash, initialize .portfolio-assistant/data/portfolio.yaml, then later answer requests like "这个月我要投入5000美元，各个资产应该怎么投" by reading the saved holdings, refreshing current prices, and running the bundled scripts for all numeric conclusions.
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

这个 skill 不依赖宿主项目本身的代码结构，统一把状态存到当前工作目录下：

- `.portfolio-assistant/data/strategy.yaml`
- `.portfolio-assistant/data/portfolio.yaml`
- `.portfolio-assistant/data/price_cache.json`

如果这些文件不存在，就视为首次使用。

## 首次使用流程

当 `.portfolio-assistant/data/portfolio.yaml` 不存在，或用户明确说“第一次用”时：

1. 先询问用户当前持仓和现金。
2. 最少收集：
   - 现金金额
   - 每个资产的 `ticker`
   - 持有股数 `shares`
   - 可选：`avg_cost`
   - 可选：最近价格 `last_price`
3. 不要自己猜持仓，不要从截图默认识别，除非用户明确要求。
4. 收集完成后，运行：

```bash
python scripts/portfolio_assistant.py init \
  --workspace .portfolio-assistant \
  --cash <现金> \
  --holding 'VOO,10,500,520' \
  --holding 'QQQM,8,180,190'
```

说明：

- `holding` 格式是 `ticker,shares[,avg_cost[,last_price]]`
- 如果用户没提供 `avg_cost` 或 `last_price`，可以省略后两项
- `init` 会自动写入默认策略模板和持仓文件

如果需要字段口径，读取 `references/data-contract.md`。

## 后续默认工作流

### 1. 读取已保存持仓

优先读取：

- `.portfolio-assistant/data/strategy.yaml`
- `.portfolio-assistant/data/portfolio.yaml`

### 2. 价格处理

如果请求涉及当前占比、偏差、补仓金额、买入股数：

- 优先使用 `.portfolio-assistant/data/price_cache.json`
- 如果缓存不存在、明显过旧，或用户明确要求“按当前价”，运行：

```bash
python scripts/portfolio_assistant.py refresh-prices --workspace .portfolio-assistant
```

### 3. 生成补仓建议

当用户给出本次投入金额时，运行：

```bash
python scripts/portfolio_assistant.py rebalance \
  --workspace .portfolio-assistant \
  --contribution 5000
```

需要机器可读结果时，加 `--json`。

### 4. 查看当前组合

```bash
python scripts/portfolio_assistant.py report --workspace .portfolio-assistant
```

### 5. 覆盖同步当前持仓

如果用户之后明确要重录当前持仓，使用：

```bash
python scripts/portfolio_assistant.py sync-holdings \
  --workspace .portfolio-assistant \
  --cash <现金> \
  --holding 'VOO,12,505,530'
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
  - 保存的持仓文件
  - 当前价格缓存或刷新结果
  - 脚本计算结果
- 当首次初始化完成时，要告诉用户后续他只需直接说：
  - “这个月我要投入 5000 美元，各个资产应该怎么投”
