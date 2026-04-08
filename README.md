# Portfolio Assistant（本地投资助手）

这是一个本地可运行的规则型投资助手项目。你只需要维护策略与持仓文件，就可以自动：
- 获取最新价格
- 计算当前占比与目标占比偏差
- 生成“新钱优先买低配”的本月补仓计划（整股 + 碎股）
- 在买入/卖出后更新持仓
- 预留 IBKR 导入扩展路径

> 项目定位：规则执行，不做择时，不做主观预测。

---

## 1. 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. 初始化持仓

默认持仓文件在 `data/portfolio.yaml`，初始为空仓占位。
你可以手工编辑，也可以通过命令更新：

```bash
python scripts/update_portfolio.py --ticker VOO --shares 3 --price 520 --side buy
```

## 3. 获取最新价格

```bash
python scripts/fetch_prices.py
```

会把结果写入 `data/price_cache.json`。

## 4. 生成本月补仓计划

```bash
python scripts/rebalance.py --contribution 5000
```

输出内容包括：
- 买前占比
- 目标占比
- 偏差
- 每个资产建议买入金额/股数
- 买后占比（整股方案 + 碎股方案）

## 5. 更新持仓

### 5.1 单条交易更新

```bash
python scripts/update_portfolio.py --ticker VOO --shares 3 --price 520 --side buy
```

### 5.2 从 CSV 批量更新

```bash
python scripts/update_portfolio.py --from-csv data/transactions.csv
```

CSV 至少包含列：`ticker, side, shares, price`。

## 6. 导入 IBKR 导出文件

当前支持本地 CSV/Flex 导出初版：

```bash
python scripts/import_ibkr_flex.py --input /path/to/ibkr_export.csv
```

脚本会尝试提取：
- ticker/symbol
- shares/position
- avg_cost（如有）
- cash（如有）

并写回 `data/portfolio.yaml`。

## 7. 查看当前组合报告

```bash
python scripts/report.py
```

输出总市值、现金、各资产市值、当前占比、目标占比、偏差。

## 8. 后续扩展方向（API 同步）

已在 `scripts/import_ibkr_flex.py` 中预留 importer 结构，后续可扩展到：
- IBKR Flex Web Service
- IBKR Client Portal API

建议路线：
1. 先稳定 CSV/Flex 导入映射规则
2. 加入统一 broker adapter 接口
3. 增加增量同步与冲突处理
4. 引入审计日志（每次同步前后快照）
