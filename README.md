# Portfolio Assistant

一个可安装的 agent skill，用来做规则型投资仓位计算。

它的目标不是择时，也不是预测涨跌，而是基于你保存的策略和持仓，自动完成这些事：

- 初始化并保存当前持仓
- 按目标权重计算当前偏差
- 每次查询前刷新资产价格和汇率
- 判断当前是否触发再平衡
- 在你给出本月新增投入后，生成分组级别和 ticker 级别的补仓建议

所有数字结论都来自脚本计算，不靠模型口算。

## 适合什么场景

这个 skill 适合下面这类问题：

- “第一次用，先帮我记一下当前持仓”
- “看看我现在各类资产偏离目标多少”
- “这个月我要投入 5000 美元，各个资产应该怎么投”
- “先刷新最新价格和汇率，再判断要不要再平衡”
- “把可选再平衡改成 4%，强制改成 7%”

不适合的场景：

- 预测市场涨跌
- 主观择时
- 替代券商对账单

## 核心特性

- 支持 `groups` 资产分组，例如把 `VOO` 和 `CSPX` 归到同一类
- 报告占比不含现金，现金单独展示
- 支持 `CNY / USD / GBP / JPY`
- 支持货币别名归一化：
  - `人民币 / 元 / RMB / CNY -> CNY`
  - `美元 / 美金 / 刀 / USD / $ -> USD`
  - `英镑 / GBP -> GBP`
  - `日元 / JPY / YEN -> JPY`
- 每次 `report` / `rebalance` 默认先刷新价格和汇率
- 输出会明确告诉你是否触发再平衡
- 再平衡阈值支持初始化时设置，后续也可单独修改

## 安装方式

这是一个 skill 仓库，不是常规应用仓库。最简单的安装方式是把整个仓库目录复制到你的 skill 目录里，并命名为 `portfolio-assistant`。

项目级安装示例：

```bash
mkdir -p /path/to/your-project/.agents/skills
cp -R /path/to/portfolio-assistant /path/to/your-project/.agents/skills/portfolio-assistant
```

如果你想全局安装，也可以放到自己的全局 skill 目录，例如：

```bash
mkdir -p ~/.codex/skills
cp -R /path/to/portfolio-assistant ~/.codex/skills/portfolio-assistant
```

调试阶段更推荐用软链，这样改完仓库内容后不用重复复制：

```bash
ln -s /path/to/portfolio-assistant ~/.codex/skills/portfolio-assistant
```

## 依赖

```bash
pip install -r requirements.txt
```

依赖项：

- `PyYAML`
- `yfinance`

其中：

- `PyYAML` 用于读写 `yaml`
- `yfinance` 用于刷新价格和汇率

## 首次使用

首次使用时，agent 应该先问你这些信息：

1. 使用默认组合方案，还是自定义组合方案
2. 默认结算货币是什么
3. 当前现金是多少，现金是什么币种
4. 当前持有哪些资产，各自 `ticker / shares / avg_cost / last_price`
5. 再平衡阈值是多少

默认值：

- 默认结算货币：`CNY`
- 可选再平衡阈值：`0.05`
- 强制再平衡阈值：`0.08`

脚本初始化示例：

```bash
python3 scripts/portfolio_assistant.py init \
  --base-currency CNY \
  --cash 3000 \
  --cash-currency CNY \
  --optional-rebalance-threshold 0.05 \
  --mandatory-rebalance-threshold 0.08 \
  --holding 'VOO,10,500,520' \
  --holding 'CSPX,1,700,706.3' \
  --holding 'QQQM,8,180,190'
```

如果你要自定义策略分组和目标权重：

```bash
python3 scripts/portfolio_assistant.py init \
  --base-currency CNY \
  --group 'S&P 500=VOO,CSPX' \
  --group '纳斯达克 100=QQQM,CSNDX' \
  --target 'S&P 500=0.20' \
  --target '纳斯达克 100=0.20' \
  --target 'TLT=0.10' \
  --target 'GLDM=0.10' \
  --cash 3000 \
  --cash-currency CNY \
  --optional-rebalance-threshold 0.05 \
  --mandatory-rebalance-threshold 0.08 \
  --holding 'VOO,10,500,520'
```

## 日常使用

查看当前组合：

```bash
python3 scripts/portfolio_assistant.py report
```

生成补仓建议：

```bash
python3 scripts/portfolio_assistant.py rebalance \
  --contribution 5000 \
  --contribution-currency USD
```

只看机器可读结果：

```bash
python3 scripts/portfolio_assistant.py report --json
python3 scripts/portfolio_assistant.py rebalance --contribution 5000 --contribution-currency USD --json
```

覆盖同步最新持仓：

```bash
python3 scripts/portfolio_assistant.py sync-holdings \
  --cash 1200 \
  --cash-currency CNY \
  --holding 'VOO,12,505,530'
```

单独修改再平衡阈值：

```bash
python3 scripts/portfolio_assistant.py update-rules \
  --optional-rebalance-threshold 0.04 \
  --mandatory-rebalance-threshold 0.07
```

如果你在离线环境调试，不想触发在线刷新：

```bash
python3 scripts/portfolio_assistant.py report --skip-refresh
python3 scripts/portfolio_assistant.py rebalance --contribution 5000 --contribution-currency USD --skip-refresh
```

## agent 使用方式

安装完成后，首次可以直接对 agent 说：

- “第一次用，先帮我初始化持仓”

初始化完成后，后续通常只需要直接说：

- “这个月我要投入 5000 美元，各个资产应该怎么投”
- “先刷新价格和汇率，再看我现在要不要再平衡”
- “把可选再平衡改成 4%，强制改成 7%”

## 数据存储位置

这个 skill 默认把自己的状态直接写在 skill 目录下的 `data/`：

- `data/strategy.yaml`
- `data/portfolio.yaml`
- `data/price_cache.json`

也就是说，脚本和数据在同一个 skill 文件夹里，不会再拆到别的隐藏目录。

如果调用方确实想写到其他位置，可以显式传：

```bash
python3 scripts/portfolio_assistant.py report --workspace /path/to/another-dir
```

## 仓库结构

```text
portfolio-assistant/
  README.md
  SKILL.md
  agents/
  assets/
  references/
  scripts/
  requirements.txt
```

关键文件：

- `SKILL.md`：skill 主说明
- `scripts/portfolio_assistant.py`：核心计算脚本
- `assets/templates/default_strategy.yaml`：默认策略模板
- `references/data-contract.md`：数据结构和字段口径
- `references/workflows.md`：推荐工作流

## 本地自测

仓库自带最小测试脚本：

```bash
bash scripts/test-skill.sh
```

它会在临时目录里完成：

- 初始化示例持仓
- 输出组合报告
- 输出补仓建议

## 边界说明

- 这是规则型工具，不是投资建议生成器。
- 如果价格或汇率刷新失败，脚本会优先回退本地缓存；如果仍缺数据，结果里会明确返回缺失项。
- 除非你明确要求，否则 agent 不应擅自修改 `data/portfolio.yaml`。
