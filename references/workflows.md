# Workflows

## 首次初始化

当工作目录里没有 `.portfolio-assistant/data/portfolio.yaml` 时：

1. 询问用户当前持仓和现金。
2. 运行 `init` 写入持久化文件。
3. 告诉用户以后可以直接问自然语言问题。

示例：

```bash
python scripts/portfolio_assistant.py init \
  --workspace .portfolio-assistant \
  --cash 3000 \
  --holding 'VOO,10,500,520' \
  --holding 'QQQM,8,180,190' \
  --holding 'TLT,5,92,90'
```

## 后续给出补仓建议

如果用户说：“这个月我要投入 5000 美元，各个资产应该怎么投”

推荐流程：

1. 检查 `.portfolio-assistant/data/portfolio.yaml` 是否存在。
2. 检查 `price_cache.json` 是否存在；必要时刷新价格。
3. 运行：

```bash
python scripts/portfolio_assistant.py rebalance \
  --workspace .portfolio-assistant \
  --contribution 5000 \
  --json
```

4. 只根据脚本结果总结建议。

## 查看当前仓位

```bash
python scripts/portfolio_assistant.py report --workspace .portfolio-assistant --json
```

## 刷新价格

```bash
python scripts/portfolio_assistant.py refresh-prices --workspace .portfolio-assistant --json
```

## 重录当前持仓

当用户说“我现在的持仓变了，重新按当前仓位记一下”时：

```bash
python scripts/portfolio_assistant.py sync-holdings \
  --workspace .portfolio-assistant \
  --cash 1200 \
  --holding 'VOO,12,505,530'
```

## 不该做的事

- 不要在首次使用时跳过持仓询问。
- 不要直接口算补仓金额。
- 不要把宿主项目自己的任意 `portfolio.yaml` 当成默认输入。
- 不要在价格获取失败时编造“当前价”。
