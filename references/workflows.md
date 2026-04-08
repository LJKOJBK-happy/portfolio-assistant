# Workflows

## 首次初始化

当 skill 目录里没有 `data/portfolio.yaml` 时：

1. 先问用户要使用默认组合方案，还是自定义组合方案。
2. 再问用户默认结算货币；若用户没说，默认 `CNY`。
3. 如果用户选择自定义，先收集 `groups` 和 `targets`。
4. 再询问用户当前持仓、现金和现金币种。
5. 再问用户再平衡阈值；若用户没说，默认可选 `0.05`、强制 `0.08`。
6. 运行 `init` 写入本地 `data/` 文件。
7. 告诉用户以后可以直接问自然语言问题。

示例：

```bash
python scripts/portfolio_assistant.py init \
  --base-currency CNY \
  --cash 3000 \
  --cash-currency CNY \
  --optional-rebalance-threshold 0.05 \
  --mandatory-rebalance-threshold 0.08 \
  --holding 'VOO,10,500,520' \
  --holding 'CSPX,1,700,706.3' \
  --holding 'QQQM,8,180,190'
```

如果用户给自定义组合方案，示例：

```bash
python scripts/portfolio_assistant.py init \
  --base-currency CNY \
  --optional-rebalance-threshold 0.05 \
  --mandatory-rebalance-threshold 0.08 \
  --group 'S&P 500=VOO,CSPX' \
  --group '纳斯达克 100=QQQM,CSNDX' \
  --target 'S&P 500=0.20' \
  --target '纳斯达克 100=0.20' \
  --target 'TLT=0.10' \
  --cash 3000 \
  --holding 'VOO,10,500,520'
```

## 后续给出补仓建议

如果用户说：“这个月我要投入 5000 美元，各个资产应该怎么投”

推荐流程：

1. 检查 `data/portfolio.yaml` 是否存在。
2. 识别用户投入金额对应的币种；若用户说“美元 / 美金 / 刀”，按 `USD` 处理；若没说，默认按策略结算货币处理。
3. 默认先刷新价格和汇率；如果刷新失败，再回退缓存或 `last_price` / 旧汇率缓存。
4. 运行：

```bash
python scripts/portfolio_assistant.py rebalance \
  --contribution 5000 \
  --contribution-currency USD \
  --json
```

5. 读取返回里的 `rebalance_decision`，告诉用户是否触发再平衡。
6. 若策略使用 `groups`，先看组级别偏差和建议金额，再看组内 ticker 拆分。
7. 只根据脚本结果总结建议。

## 查看当前仓位

```bash
python scripts/portfolio_assistant.py report --json
```

`--json` 输出会返回：

- `positions_value`
- `cash`
- `total_value`
- `base_currency`
- `fx_rates`
- `groups`
- `rebalance_decision`

其中每个 group 下会附带组内 `holdings` 明细。

## 刷新价格

```bash
python scripts/portfolio_assistant.py refresh-prices --json
```

## 重录当前持仓

当用户说“我现在的持仓变了，重新按当前仓位记一下”时：

```bash
python scripts/portfolio_assistant.py sync-holdings \
  --cash 1200 \
  --cash-currency CNY \
  --holding 'VOO,12,505,530'
```

## 修改再平衡阈值

当用户说“把可选再平衡改成 4%，强制改成 7%”时：

```bash
python scripts/portfolio_assistant.py update-rules \
  --optional-rebalance-threshold 0.04 \
  --mandatory-rebalance-threshold 0.07
```

## 覆盖默认路径

如果调用方确实想把数据写到 skill 目录以外，才显式传 `--workspace`。

## 不该做的事

- 不要在首次使用时跳过持仓询问。
- 不要直接口算补仓金额。
- 不要在价格获取失败时编造“当前价”。
