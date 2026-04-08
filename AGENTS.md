# AGENTS.md

## 项目目标
这是一个投资助手项目初始骨架，核心文件如下：

- `strategy.yaml`：策略参数与目标权重。
- `portfolio.yaml`：账户与持仓快照。
- `rebalance.py`：根据策略与持仓生成再平衡建议。
- `ibkr_sync.py`：IBKR 同步脚手架（模板）。

## 开发约定
- 使用 Python 3.11+。
- 优先保持脚本无外部服务依赖，默认可在离线环境运行。
- 修改 YAML 结构时同步更新脚本字段读取逻辑。
- 新增功能请保留 `--dry-run` 安全开关。

## 运行示例
```bash
python rebalance.py --strategy strategy.yaml --portfolio portfolio.yaml
python ibkr_sync.py --portfolio portfolio.yaml --dry-run
```
