# Deep Research Agent · 深度研究多智能体助手

> **2026-09-08 更新**：默认报告采用可追溯原文摘录。每个来源分别匹配引文，模型草稿与模型声明的官方来源信息不直接交付；匹配率不等于事实准确率。新闻登记、空结果兜底、时间筛选及任务隔离已修复。108 个测试通过，旧诊断 0/13 仍可复现；真实 Tavily 烟雾测试成功，真实模型回归因 Ollama 不可用未完成。详见 [改善反馈与学习指引](docs/UPGRADE-2026-09-08.md)。


一个基于 **OpenAI Agents SDK** 的多智能体深度研究系统：输入一个研究问题，系统会自动
**规划搜索策略 → 并行联网调研 → 汇总撰写**，最终产出一份带引用来源的结构化 Markdown 研究报告。

支持三种模型模式：**OpenAI 云端**（效果最佳）、**任意 OpenAI 兼容端点**（DeepSeek/GLM 等）、
**Ollama 本地模型**（无需 API Key，完全离线可跑）。附带 **Streamlit Web 界面** 与
**评估体系（含 LLM-as-judge 自动评分、来源可访问性校验）**。

## 目录

- [架构](#架构)
- [核心特性](#核心特性)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [Web 界面](#web-界面)
- [使用示例](#使用示例)
- [项目结构](#项目结构)
- [测试](#测试)
- [评估](#评估)
- [简历亮点](#简历亮点)
- [Roadmap](#roadmap)

## 架构

```
                     ┌──────────────────────────────────────┐
  研究问题 ─────────▶ │ Planner（规划者，带输入护栏）          │
                     │  输出: ResearchPlan（研究策略 + 查询） │
                     └──────────────────┬───────────────────┘
                                        │ 拆解为 3~6 个查询
                    ┌───────────────────▼────────────────────┐
                    │  Researcher × N（并行执行 asyncio.gather）│
                    │   工具: web_search（多后端联网搜索）      │
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

三个 Agent 各有明确职责（Single Responsibility），由编排层（`runner.py`）统一调度，
这也是 Agent 项目中常见的 **Plan → Act → Synthesize** 工作流模式。

## 核心特性

- **多智能体流水线**：Planner / Researcher / Writer 分工协作，职责清晰、可单独替换。
- **多后端联网搜索**：优先 **Tavily API**（免费 Key，自带正文内容与时间过滤），兜底 Bing/DuckDuckGo/Baidu（英文查询自动跳过百度）；提供 `web_search`（支持 recency）、`research_sources`（搜索+读原文）、`news_search`（近期新闻）、`fetch_page`（正文抽取）。
- **结构化输出**：全程使用 Pydantic schema（`ResearchPlan` / `ResearchNotes` / `ResearchReport`），
  结果可校验、可序列化。
- **输入安全护栏**：Input Guardrail 拦截过短 / 无效输入，节省模型调用成本。
- **并行研究**：多个 Researcher 通过 `asyncio.gather` 并行执行，显著缩短总耗时。
- **空结果自动重试**：搜索无数据时自动换措辞/换语言重试，不再产出"No data found"废报告。
- **语言一致性**：按问题语言动态注入指令，中文问题强制产出中文报告。
- **追问澄清（human-in-the-loop）**：问题模糊时先问 1-2 个澄清问题（清晰问题自动跳过），把答案并入研究问题。
- **三模型模式**：OpenAI 云端 / 任意 OpenAI 兼容端点（DeepSeek/GLM/Moonshot）/ Ollama 本地。
- **Web 可视化界面**：Streamlit 交互式研究（进度展示、报告预览、下载、来源校验）。
- **LLM-as-judge 评估**：独立 Judge 模型给报告打 1-5 分（相关性/准确性/结构/来源）。
- **来源可访问性校验**：实际请求每个引用 URL，自动揪出编造的 404/403 链接。
- **来源白名单与证据绑定**：来源由本次工具调用登记并分配 `SRC-001` 编号；最终报告只保留登记过且不是搜索结果页的 URL。每条证据还必须通过正文/摘要逐字引文校验，否则发现会被降为 `unknown`。
- **向量记忆（RAG）**：历史报告存入 ChromaDB，新研究自动检索相关过往报告作参考（Ollama 本地嵌入，可离线）。
- **PDF 报告导出**：一键生成中文字体 PDF，便于交付。
- **自动成文**：一键生成带引用来源、局限与建议的 Markdown 报告并落盘。

## 技术栈

| 组件 | 说明 |
| --- | --- |
| Python 3.12 | 开发语言（>= 3.10） |
| OpenAI Agents SDK 0.19.x | 多智能体框架（Agent / Runner / Guardrails / 结构化输出） |
| OpenAI 兼容 API | 直连 Ollama /v1 或任意兼容端点（OpenAIChatCompletionsModel） |
| ddgs / Bing / Baidu | 多后端联网搜索 |
| Trafilatura | 网页正文抽取 |
| Rich | 终端美化输出 |
| Streamlit | Web 可视化界面（可选依赖 `web` extra） |
| ChromaDB | 向量记忆存储（RAG） |
| reportlab | PDF 报告导出（中文字体） |
| Pydantic | 数据建模与校验 |
| pytest | 单元测试（108 个用例） |
| uv | 依赖与虚拟环境管理 |

## 快速开始

### 0. 准备

```powershell
# 安装 uv（Python 包管理器）：https://docs.astral.sh/uv/
# 然后在项目目录执行：
uv sync --extra dev
```

### 方式一：本地模式（无需 API Key，推荐先体验）

1. 安装并启动 [Ollama](https://ollama.com/)（启动：运行 `ollama serve`，或直接打开 Ollama 应用），然后拉取一个模型：

   ```powershell
   ollama pull qwen3:4b
   ollama pull nomic-embed-text   # RAG 向量记忆所需嵌入模型
   ```

2. 配置环境（复制示例文件并确认）：

   ```powershell
   Copy-Item .env.example .env   # 默认 RESEARCH_PROVIDER=local
   ```

3. 运行：

   ```powershell
   uv run research "人工智能在医疗诊断领域的最新进展"
   ```

### 方式二：OpenAI 云端模式（效果最佳）

1. 在 [OpenAI Platform](https://platform.openai.com/api-keys) 获取 API Key；
2. 编辑 `.env`：

   ```ini
   RESEARCH_PROVIDER=openai
   OPENAI_API_KEY=sk-xxxx
   ```

3. 运行：

   ```powershell
   uv run research "What are the latest advances in multimodal LLMs?"
   ```

### 方式三：任意 OpenAI 兼容端点（DeepSeek / GLM / Moonshot 等）

```ini
RESEARCH_PROVIDER=openai
OPENAI_API_KEY=sk-你的key
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

> 未指定 provider 时会自动判断：存在 `OPENAI_API_KEY` 则用云端，否则用本地。

### 方式四：搜索质量优化（可选，强烈推荐）

免费申请 [Tavily API Key](https://tavily.com)，在 `.env` 填写后搜索质量与时效性显著提升（自带正文内容、时间过滤、新闻主题）：

```ini
TAVILY_API_KEY=tvly-xxxx
```

## Web 界面

```powershell
uv sync --extra web          # 首次安装 Web 依赖（streamlit）
uv run --extra web streamlit run app.py
```

> 提示：**升级代码后需重启 Web 服务**（Streamlit 不会热重载已导入的 Python 包）。

浏览器会自动打开（或访问 http://localhost:8501）。支持：选择模型提供方、调整并行查询数、
实时阶段进度、报告预览、Markdown 下载、生成后来源 URL 校验。

## 使用示例

```powershell
uv run research "2026年开源大模型生态发展趋势" --max-queries 4
uv run research "开源大模型未来方向" --max-queries 3 --use-memory --pdf   # 带向量记忆 + PDF 导出
```

运行过程会打印规划出的查询、并行研究进度，并在 `reports/` 目录生成类似
`20260807-141530-2026开源大模型生态发展趋势.md` 的报告文件，包含：

- 执行摘要（Summary）
- 核心发现（Key Findings）
- 参考来源（Sources，带链接）
- 研究局限（Limitations）
- 后续建议（Recommendations）

## 项目结构

```
deep-research-agent/
├── pyproject.toml            # 项目配置与依赖
├── .env.example              # 环境变量示例
├── app.py                    # Streamlit Web 界面
├── src/research_agent/
│   ├── agents.py             # Agent 定义与提示词（Planner/Researcher/Writer）
│   ├── runner.py             # 编排：规划 → 并行研究（含重试）→ 撰写 → 保存
│   ├── tools.py              # 自定义工具（多后端搜索 + 网页抽取）
│   ├── guardrails.py         # 输入护栏
│   ├── models.py             # Pydantic 结构化输出 schema
│   ├── judge.py              # LLM-as-judge 自动评分
│   ├── evals.py              # 评估评分逻辑（含来源可访问性校验）
│   ├── memory.py             # RAG 向量记忆（ChromaDB + Ollama 嵌入）
│   ├── export.py             # PDF 报告导出
│   ├── clarify.py            # 追问澄清（human-in-the-loop）
│   ├── formatting.py         # Markdown 渲染
│   ├── config.py             # 配置与模型提供方选择
│   └── cli.py                # 命令行入口
├── evals/                    # 评估用例集与运行器
├── tests/                    # pytest 单元测试
└── reports/                  # 生成的报告（gitignore）
```

## 测试

```powershell
uv run pytest
```

108 个单元测试覆盖：结构化输出模型、输入护栏、搜索多后端兜底与失败处理、网页抓取异常处理、
评估评分（含语言检查、来源校验）、LLM-as-judge JSON 解析、多模型接入、研究模式、证据覆盖率、
FastAPI 健康接口、PDF 和 RAG 存储。

## 评估

```powershell
# 基础回归（结构/来源/语言）
uv run python evals/run_evals.py --limit 3 --max-queries 2

# 进阶：LLM-as-judge 打分 + 来源可访问性校验
uv run python evals/run_evals.py --limit 3 --max-queries 2 --judge --verify-sources
```

指标：结构完整、来源有效（格式）、语言一致、关键词命中、来源可访问性（真实请求）、
LLM-as-judge 四维评分（relevance / accuracy / structure / sources）。

> 事实核验边界：来源编号和 URL 白名单只能证明来源被工具观察到；只有引文能在抓取正文或摘要中逐字匹配，才会计入证据覆盖率。即使匹配，也不等于事件已经被官方确认。

## API 与 Docker

```powershell
uv run research-api
# GET  http://localhost:8000/health
# GET  http://localhost:8000/config
# POST http://localhost:8000/research
```

Docker Desktop 启动后：

```powershell
docker compose build
docker compose up
```

容器内 API 通过 `host.docker.internal:11434` 访问宿主机 Ollama；报告和向量记忆分别挂载到
`reports/`、`memory/`。

## 简历亮点

- 使用 **OpenAI Agents SDK** 设计并实现 **Planner → Researcher × N → Writer** 三段式多智能体
  深度研究工作流，Agent 职责单一、编排层可插拔。
- 实现**多后端联网搜索工具**（Bing / DuckDuckGo / Baidu 自动故障转移）与**网页正文抽取工具**，
  并以 `asyncio.gather` 并行调度多个研究 Agent；搜索空结果自动重试。
- 全程使用 **Pydantic 结构化输出** + **Input Guardrail** + 动态语言指令，结果可校验、可复用。
- 支持 **OpenAI 云端 / 任意 OpenAI 兼容端点 / Ollama 本地**三模式接入（OpenAI 兼容端点直连）。
- 构建 **Streamlit Web 界面** + **评估体系**：LLM-as-judge 自动评分、来源 URL 可访问性校验，
  能自动揪出模型编造的链接——体现工程化与质量意识。
- 配套 108 个 pytest 单元测试与中文文档（README / 项目总结 / 交接文档），工程规范完整。

## Roadmap

- [x] **评估体系（Evals）**：`uv run python evals/run_evals.py` 回归测试与质量评分
- [x] **Streamlit 可视化 Web 界面**
- [x] **LLM-as-judge 自动评分 + 来源可访问性校验**
- [x] **多模型接入**：任意 OpenAI 兼容端点（DeepSeek / GLM 等）
- [x] **证据链与热点核验模式**：Finding 状态、证据摘录、来源质量与覆盖率质量闸门
- [x] **FastAPI 服务化 + Docker Compose 配置**
- [x] **Codex Skill 包装**：见 `codex-skill/deep-research/`
- [x] **搜索质量优化**：Tavily API + research_sources/news_search + 日期注入
- [x] 研究报告 PDF 导出（reportlab + 中文字体）
- [x] 基于向量库的历史研究记忆（RAG，ChromaDB + Ollama 嵌入）
- [x] 追问澄清（human-in-the-loop）
- [x] Docker 部署 + API 服务化配置

## License

MIT
