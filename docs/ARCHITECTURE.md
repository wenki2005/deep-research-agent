# Deep Research Agent · 架构设计文档

> 本文档说明系统的整体设计、各阶段职责、关键工程决策与权衡，
> 供接手者深入理解"为什么这么设计"。

## 1. 系统总览

输入一个研究问题 → 输出一份带引用来源的结构化 Markdown 报告（可选 PDF）。

流水线（流水线式编排，各 Agent 单一职责）：

```
问题 → [Router 研究模式路由] → [Clarifier 追问澄清] → [Memory 检索历史] → Planner 规划
     → Researcher × N（并行，联网检索+读原文）→ Writer 撰写
     → [证据覆盖率质量闸门] → 保存报告（.md / .pdf）→ [Memory 入库]
```

## 2. 各阶段设计

### 2.1 Clarifier（追问澄清，human-in-the-loop）
- 问题：`likely_vague()` 启发式闸门先过滤——只有"可能模糊"的问题才调用 LLM 澄清器
- 理由：本地小模型对"是否需要澄清"判断过于保守（清晰问题也追问）；
  用确定性规则先挡掉明确问题，既省一次模型调用，也避免打扰用户
- 交互：CLI 用 rich Prompt（可回车跳过）；Web 用两步式 session_state + 逃生按钮

### 2.2 Memory（RAG 向量记忆）
- 存储：ChromaDB（本地持久化，余弦相似度）
- 嵌入：Ollama `/api/embeddings`（nomic-embed-text），完全离线
- 设计要点：
  - `embed_fn` 可注入 → 测试用假嵌入函数，无需连模型
  - 检索/入库全程 try/except 降级——**记忆是增强项，绝不允许阻塞主流程**
  - 历史内容注入 **Planner 输入**（让规划知道"已覆盖什么"），而非塞给 Writer

### 2.3 Planner / Researcher / Writer
- Planner：拆解为 3-6 个查询（含最新年份），结构化输出 `ResearchPlan`
- Researcher：每个查询做深度调研——`web_search`（可带 recency）+ `research_sources`
  （搜索+读原文）+ `news_search`（新闻）；空结果自动换措辞重试
- Writer：合成 `ResearchReport`（4-6 条核心发现，每条 2-3 句带数字/日期）
- **关键指令：注入当前日期**。模型不知道"今天是几号"，不注入就会搜 2024/2025 的旧数据
- **证据质量闸门**：搜索/抓取结果进入本次运行的 provenance registry，并分配 `SRC-xxx` 编号；写作者只能引用编号。编排层将编号映射回真实 URL，剔除搜索结果页和未观察到的 URL；引文必须在捕获的正文或摘要中逐字出现，否则发现强制标为 `unknown`。

### 2.4 模型提供方抽象（`build_model`）
- `local`：Ollama `/v1` OpenAI 兼容端点（OpenAIChatCompletionsModel）
- `openai`：默认 SDK 端点；若配置 `OPENAI_BASE_URL` 则走任意 OpenAI 兼容端点（DeepSeek/GLM）
- 全部通过统一接口返回 `Model | None`，上层无感知

## 3. 搜索策略（重点）

| 优先级 | 后端 | 说明 |
| --- | --- | --- |
| 1 | **Tavily API**（`TAVILY_API_KEY`） | 质量高、自带正文内容、支持 days 时间过滤、news 主题；gpt-researcher 等主流方案 |
| 2 | Bing 抓取 | 国内网络可用的兜底；语言自适应（中文查中文） |
| 3 | DuckDuckGo | 兜底 |
| 4 | Baidu | 仅中文查询的最后手段（英文查询直接跳过） |

- `recency=day|week|month`：Tavily 映射为 `days` 参数；抓取端不强加过滤器
  （实测 Bing `qft` 过滤器会清空结果，已弃用）
- `research_sources`：搜索后读取 Top 页正文——模型拿到的不是摘要而是**真实内容**，
  这是"调研深度"的关键（open-deep-research 同款思路）

## 4. 评估体系

- 自动指标：结构完整、来源有效（格式）、语言一致、来源可访问性（真实请求）
- 进阶：`--judge` LLM-as-judge 四维评分；`--verify-sources` 实际校验 URL
- 通过 = 结构 + 来源 + 语言 + 无异常

### 4.1 来源真实性边界

来源白名单解决的是“模型是否凭空生成链接”，不是“链接内容是否证明结论”。系统分两层判断：

1. 来源存在性：URL 必须由搜索或抓取工具在当前运行中观察到，且不能是百度、必应、搜狗等搜索结果页。
2. 证据支持性：发现中的 `evidence_quote` 必须逐字匹配已捕获的正文或搜索摘要；匹配失败的发现会降级为 `unknown`，摘要会提示用户不要把细节当作已确认事实。

## 5. 主要工程决策与权衡

| 决策 | 原因 | 代价/权衡 |
| --- | --- | --- |
| 流水线编排而非全动态 handoff | 本地小模型稳定可控、可单测 | 灵活性略低 |
| 确定性闸门 + LLM 判断结合 | "能确定的事交给代码" | 规则需要维护 |
| 记忆/搜索异常一律降级 | 增强功能不能拖垮主流程 | 极端情况静默丢失增强 |
| 中文 bat 用纯 ASCII | Windows cmd 对 UTF-8/GBK 批处理解析不可靠 | 菜单为英文 |
| Streamlit 不热重载已导入包 | Python import 缓存 | 升级代码后必须重启服务 |

## 6. 借鉴的开源项目

- [langchain-ai/open-deep-research](https://github.com/langchain-ai/open-deep-research)：
  规划 → 多查询研究 → learnings 累积 → 成文的分层思想
- [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher)：
  搜索 API（Tavily）+ 并行子任务 + 报告聚合
- [OpenAI Cookbook deep-research](https://cookbook.openai.com/)：
  追问澄清（human-in-the-loop）+ breadth/depth 规划


## 2026-09-08 当前证据协议

每次 run_research 使用独立 registry，工具闭包显式绑定该 registry，并在线程中执行同步网络请求。退出/异常/取消均恢复任务上下文，无进程全局回退。

报告经过保守的摘录投影：所有引文逐来源匹配；自由结论、模型标题和官方分类不保留。support_level 区分 snippet_quote/page_quote/unverified；verification_state 区分 unchecked/insufficient/partial/quoted。二者均不代表语义事实确认。

质量不足时补搜原始问题并尝试一次重写，仅采纳更好的候选。任何语义分析扩展都需要独立评估，不能用逐字引文匹配替代。完整变更和验证边界见 [本轮反馈](UPGRADE-2026-09-08.md)。
