# Deep Research Agent 项目总结

> 多智能体深度研究助手 · Multi-Agent Deep Research Assistant
> 基于 OpenAI Agents SDK 构建，支持 OpenAI 云端 / Ollama 本地双模型模式

---

## 一、项目内容

### 1.1 项目是什么

输入一个研究问题，系统会自动完成 **「规划 → 并行联网调研 → 汇总撰写」** 全流程，最终产出一份带引用来源的结构化 Markdown 研究报告。

一句话概括：**一个能替你做桌面调研的多智能体系统**——你把问题交给它，它自己拆解问题、联网查资料、整理成报告。

### 1.2 架构设计

```
                     ┌──────────────────────────────────────┐
  研究问题 ─────────▶ │ Planner（规划者，带输入护栏）          │
                     │  输出: ResearchPlan（研究策略 + 查询） │
                     └──────────────────┬───────────────────┘
                                        │ 拆解为 3~6 个查询
                    ┌───────────────────▼────────────────────┐
                    │  Researcher × N（并行执行 asyncio.gather）│
                    │   工具: web_search（Bing/DDG/Baidu 多后端）│
                    │         fetch_page（网页正文抽取）        │
                    │  输出: ResearchNotes（发现 + 来源）       │
                    └───────────────────┬────────────────────┘
                                        │ 汇总所有研究笔记
                    ┌───────────────────▼────────────────────┐
                    │  Writer（撰写者）                        │
                    │  输出: ResearchReport（结构化报告）       │
                    └───────────────────┬────────────────────┘
                                        ▼
                          Markdown 报告（保存至 reports/）
```

这是 Agent 开发中经典的 **Plan → Act → Synthesize** 工作流模式：三个 Agent 各司其职（单一职责），由编排层统一调度。

### 1.3 核心特性

| 特性 | 说明 |
|---|---|
| 多智能体流水线 | Planner / Researcher / Writer 分工协作，职责清晰、可单独替换 |
| 自定义函数工具 | `web_search` 多后端联网搜索（Bing→DuckDuckGo→Baidu 自动故障转移）、`fetch_page` 网页正文抽取 |
| 结构化输出 | 全程 Pydantic schema（ResearchPlan / ResearchNotes / ResearchReport），结果可校验、可序列化 |
| 输入安全护栏 | Input Guardrail 拦截过短/无效输入，节省模型调用成本 |
| 并行研究 | 多个 Researcher 通过 `asyncio.gather` 并行执行，显著缩短总耗时 |
| 双模型模式 | `openai`（云端，效果最佳）与 `local`（Ollama + OpenAI 兼容端点，无 API Key 可跑） |
| 自动成文 | 一键生成带引用来源、局限与建议的 Markdown 报告并落盘 |

### 1.4 技术栈

| 组件 | 版本/说明 |
|---|---|
| Python | 3.12（>= 3.10） |
| OpenAI Agents SDK | 0.19.x（Agent / Runner / Guardrails / 结构化输出 / 工具调用） |
| Pydantic | v2 数据建模与校验 |
| 搜索 | ddgs + 自研 Bing/Baidu 解析（多后端兜底） |
| 网页抽取 | Trafilatura |
| CLI | argparse + Rich 终端美化 |
| 本地推理 | Ollama 0.32.6 + qwen3:4b（RTX 3060） |
| 工程化 | uv（依赖管理）、pytest（67 个单元测试）、ruff（代码规范）、Git、Streamlit、FastAPI、Docker |

### 1.5 实际运行效果

用本地模型（qwen3:4b）实测 `人工智能在医疗诊断领域的最新进展有哪些`：
- Planner 自动规划 3 个查询：最新进展概述、深度学习影像诊断案例、全球市场规模报告
- 3 个 Researcher 并行联网搜索并提取网页内容
- Writer 汇总成报告：《AI医疗诊断关键进展：2023-2024全球技术突破与市场动态》
- 报告包含摘要、核心发现、6 个带链接来源、局限、建议，保存到 `reports/`

### 1.6 项目结构

```
deep-research-agent/
├── pyproject.toml            # 项目配置与依赖
├── .env.example              # 环境变量示例
├── src/research_agent/
│   ├── agents.py             # Agent 定义与提示词（Planner/Researcher/Writer）
│   ├── runner.py             # 编排：规划 → 并行研究 → 撰写 → 保存
│   ├── tools.py              # 自定义工具（多后端搜索 + 网页抽取）
│   ├── guardrails.py         # 输入护栏
│   ├── models.py             # Pydantic 结构化输出 schema
│   ├── formatting.py         # Markdown 渲染
│   ├── config.py             # 配置与模型提供方选择
│   └── cli.py                # 命令行入口
├── tests/                    # pytest 单元测试（67 个）
└── reports/                  # 生成的报告（gitignore）
```

---

## 二、所需基础知识

### 2.1 必须掌握（跑通项目需要）

1. **Python 基础**
   - 语法、类型注解（type hints）、模块/包结构
   - 虚拟环境与依赖管理：`venv` / `pip` / `uv`
   - 异步编程：`async/await`、`asyncio.gather`（并行调度的核心）

2. **LLM 与大模型基础**
   - 什么是大语言模型、提示词（prompt）、token
   - Chat Completion / 对话接口的基本概念
   - **函数调用（Function/Tool Calling）**：模型如何调用外部工具
   - **结构化输出（Structured Output / JSON Schema）**：如何让模型返回可校验的 JSON

3. **Agent 框架概念**（OpenAI Agents SDK）
   - Agent（指令 + 工具 + 结构化输出 + 护栏）
   - Runner（运行循环：模型调用 → 工具调用 → 循环直到最终输出）
   - Guardrails（输入/输出护栏）
   - 多 Agent 协作（handoff / 工作流编排）

4. **工程基础**
   - Git 基本操作
   - 命令行工具设计（argparse）
   - 单元测试（pytest）
   - HTTP 请求与网页解析（requests + Trafilatura）

### 2.2 了解即可（进阶可深挖）

- Docker 容器化部署
- 向量数据库与 RAG（检索增强生成）
- 模型评估（Evals）
- 可观测性/追踪（Tracing）
- 前端（Streamlit / FastAPI）——做 Web 界面用

---

## 三、建议学习理解的内容

按重要性排序，建议配合 [OpenAI Agents SDK 官方文档](https://openai.github.io/openai-agents-python/) 学习：

### 3.1 核心必读

1. **Agent 运行循环（Run Loop）**
   - 理解 `Runner.run()` 的内部机制：模型输出 → 是否调用工具 → 执行工具 → 把结果喂回模型 → 循环，直到产出最终输出或超时（max_turns）
   - 这是所有 Agent 框架的共同底层逻辑，理解了它，其他框架（LangGraph、CrewAI）一通百通

2. **工具调用（Tools）**
   - 为什么需要 `function_tool` 装饰器
   - 工具描述（description）写得好不好，直接决定模型会不会正确调用
   - JSON Schema 形式的工具参数定义

3. **结构化输出（Structured Outputs）**
   - Pydantic model 如何变成 JSON Schema
   - 原生 structured outputs vs 提示词式 JSON 的区别
   - 本项目踩过的坑：Ollama 本地模型对 response_format 支持不完整 → 改用 OpenAI 兼容端点直连

4. **护栏（Guardrails）**
   - 输入护栏如何拦截无效输入、节省成本
   - tripwire 机制与异常处理

5. **多 Agent 协作模式**
   - 本项目用的是「工作流编排」（workflow）：规划→并行→撰写
   - 另一种是「交接」（handoff）：Agent 之间动态转移任务
   - 理解两者的适用场景（确定性 vs 开放性任务）

### 3.2 建议动手实践

1. **改提示词**：调整 Planner 的指令，观察生成的查询质量变化
2. **加一个工具**：比如加一个「计算器」工具或「读本地文件」工具，看模型如何调用
3. **换模型**：把 `LOCAL_MODEL` 换成 `qwen2.5:7b` 或接 DeepSeek 的 OpenAI 兼容端点，对比效果
4. **手写一个单 Agent 版本**：不用框架，直接用 `openai` SDK 写一个工具调用循环，再对比 Agents SDK 帮你做了什么

### 3.3 值得阅读的资料

- [OpenAI Agents SDK 文档（Python）](https://openai.github.io/openai-agents-python/)
- [OpenAI 官方 Cookbook：Deep Research 示例](https://cookbook.openai.com/)
- [Anthropic 的 "Building Effective Agents" 博客](https://www.anthropic.com/research/building-effective-agents)（讲 workflow vs agent 的经典文章）
- [Pydantic v2 文档](https://docs.pydantic.dev/)
- [Ollama 文档](https://github.com/ollama/ollama)

---

## 四、改进方向

### 4.1 近期（1-2 周，性价比最高）

1. ~~**Web 可视化界面**~~（✅ 已实现：Streamlit，uv run --extra web streamlit run app.py）
   - Streamlit 或 FastAPI + 简单前端，让用户输入问题、流式查看研究过程
   - 简历上「有 UI 可演示」比纯 CLI 更有说服力

2. **防幻觉 / 引用验证**
   - 让 Researcher 必须从 `fetch_page` 抓到的正文里摘录原文（带引号引用）
   - Writer 只能引用 Researcher 实际抓取过的 URL，禁止凭空编造来源
   - 当前本地小模型偶尔会编造来源，这是重点改进项

3. ~~**追问澄清（Human-in-the-loop）**~~（✅ 已实现：模糊问题先问 1-2 个澄清问题，清晰问题自动跳过）
   - 问题模糊时，先反问用户 1-2 个澄清问题再开始研究（参考 OpenAI Cookbook 的 deep research 示例）

4. **更多模型提供方**
   - DeepSeek / GLM / Gemini 等都有 OpenAI 兼容端点，改 `base_url` + `model` 即可接入（当前架构已支持，只需加配置）

### 4.2 中期（1-3 个月）

5. ~~**RAG 记忆 / 知识库**~~（✅ 已实现：ChromaDB + Ollama 嵌入，报告自动入库、相似检索）
   - 用向量数据库（Chroma / Qdrant）保存历史研究报告，新研究可以引用旧报告
   - 支持上传 PDF/文档作为研究素材

6. ~~**模型评估（Evals）**~~（✅ 已实现基础版 + LLM-as-judge 自动评分 + 来源可访问性校验）
   - 建立一组标准研究问题 + 参考答案，用评分指标（引用质量、事实准确率、完整性）自动化评估每次改动
   - 这是把项目从「demo」变成「工程」的关键一步

7. ~~**报告导出 PDF**~~（✅ 已实现：reportlab + 中文字体）

8. ~~**证据链与热点核验**~~（✅ 已实现：Finding 状态、证据摘录、来源质量、热点模式、覆盖率闸门）
   - 让产出物更正式，适合直接交付给非技术人员

8. **成本与速度优化**
   - 结果缓存（相同问题不重复搜索）
   - 用更便宜的模型做 Planner/Writer、更强模型做 Researcher
   - 限制每轮搜索数量、控制 token 消耗

### 4.3 长期 / 进阶

9. **生产化部署**
   - Docker 镜像 + API 服务化，支持多人并发使用

10. **可观测性**
    - 接入 OpenAI Tracing 或 LangSmith，可视化每一步的模型调用、工具调用、耗时

11. **主动型 Agent**
    - 从「一次性回答」升级为「持续监控」：比如定时跟踪某个行业动态，每周自动生成简报（可配合 Codex 的 automations 实现）

---

## 五、一句话总结

> 这个项目用 **OpenAI Agents SDK** 实现了一个 **规划-并行研究-撰写** 的多智能体深度研究系统，
> 涵盖了 Agent 开发的五大核心能力：**工具调用、结构化输出、护栏、多智能体协作、双模型接入**，
> 并配套完整的工程化（测试、规范、文档、Git）。是简历上能体现「LLM 应用工程能力」的完整项目。
