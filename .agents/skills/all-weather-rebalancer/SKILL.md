# all-weather-rebalancer

## 什么时候使用
当用户希望根据既定策略自动生成补仓/再平衡建议时使用本 skill，典型请求如：
- “这个月我要投 5000 美金，给我投资计划”
- “帮我看当前仓位和目标偏差”

## 使用步骤
1. 读取 `data/strategy.yaml` 获取目标配置与规则。
2. 读取 `data/portfolio.yaml` 获取当前持仓与现金。
3. 获取最新价格（优先运行 `python scripts/fetch_prices.py`）。
4. 运行补仓脚本：
   - `python scripts/rebalance.py --contribution <金额>`
5. 输出结果必须包含：
   - 当前占比
   - 目标占比
   - 偏差
   - 买入计划（金额 + 股数）
   - 买后占比（整股方案与碎股方案）

## 明确禁止
- 禁止主观择时或预测行情。
- 禁止臆造价格或手工编造计算结果。
- 未经用户确认，禁止直接修改 `data/portfolio.yaml`。
