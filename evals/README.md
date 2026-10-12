# Eval 模块：评估与回归测试

让项目「不只是 demo」的关键：**用一组标准问题持续衡量流水线质量**，
防止改代码/换模型后效果悄悄变差（回归）。

## 指标定义

| 指标 | 含义 | 是否判失败 |
| --- | --- | --- |
| 结构完整 | title/summary/key_findings(>=3)/sources/limitations/recommendations 是否齐全 | 是 |
| 来源有效 | 至少 1 个合法 URL（http(s) 且含点号、去重） | 是 |
| 语言一致 | 中文问题必须产出中文报告（防语言漂移） | 是 |
| 关键词命中 | 用例里配置的 `expected_keywords` 是否出现在报告中 | 否（信息性） |
| 来源可访问性 | 实际请求每个 URL，统计可达数量（`--verify-sources`） | 否（信息性） |
| LLM-as-judge | 独立 Judge 模型按 4 维度打 1-5 分（`--judge`） | 否（信息性） |
| 运行出错 | 流水线是否抛异常（超时、护栏等） | 是（直接 FAIL） |
| 耗时 | 每个用例的总耗时 | 否 |

**通过 = 结构完整 + 来源有效 + 语言一致 + 未报错**

## 运行

```powershell
# 快速跑 3 个用例（本地模型）
uv run python evals/run_evals.py --limit 3 --max-queries 2

# 跑某一类标签
uv run python evals/run_evals.py --tags tech

# 全量 + OpenAI 云端
uv run python evals/run_evals.py --max-queries 4 --provider openai

# 进阶：LLM-as-judge 打分 + 来源可访问性校验（较慢）
uv run python evals/run_evals.py --limit 3 --max-queries 2 --judge --verify-sources
```

结果输出到 `evals/results/<时间戳>/`：
- `eval-report.md`：总览 + 逐用例评分（含 judge 分数、来源校验失败列表）+ 人工核验清单
- 每份生成的报告也保存在同目录，便于人工抽检

## 添加用例

编辑 `cases.jsonl`，每行一个 JSON：

```json
{"question": "你的研究问题", "tags": ["tech"], "expected_keywords": ["关键词"]}
```

## 什么时候跑

- 每次改提示词 / 工具 / 护栏 / 模型之后
- 换模型（本地或云端）前后对比
- 提交代码前（配合 pytest 一起）

## 局限

- 自动化仍不检查**事实准确性**（模型可能编造数字）→ judge 分数只是信号，关键结论需人工核验
- 来源可访问性校验会受网络环境影响（对方网站反爬/地区限制可能误报）
- 关键词检查很弱（子串匹配）→ 主要用于快速回归信号
- 更高级的做法：RAGAS 式指标、多模型交叉评审、golden dataset 回归