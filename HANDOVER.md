# 项目记录与交接文档（HANDOVER）

> **2026-09-08 更新**：默认报告采用可追溯原文摘录。每个来源分别匹配引文，模型草稿与模型声明的官方来源信息不直接交付；匹配率不等于事实准确率。新闻登记、空结果兜底、时间筛选及任务隔离已修复。108 个测试通过，旧诊断 0/13 仍可复现；真实 Tavily 烟雾测试成功，真实模型回归因 Ollama 不可用未完成。详见 [改善反馈与学习指引](docs/UPGRADE-2026-09-08.md)。


> 项目：Deep Research Agent · 多智能体深度研究助手
> 本文档用途：让接手者（或未来的自己）在 15 分钟内了解项目现状、跑起来、并知道下一步做什么。
> 最后更新：2026-09-05

---

## 1. 项目概览

**一句话**：输入一个研究问题，系统自动完成「规划 → 并行联网调研 → 汇总撰写」，产出一份带引用来源的结构化 Markdown 研究报告。

**架构**：Planner（带输入护栏）→ Researcher × N（`asyncio.gather` 并行 + 多后端联网搜索）→ Writer（结构化报告）

**技术栈**：
| 组件 | 版本 | 说明 |
|---|---|---|
| Python | 3.12.13（>=3.10） | 由 uv 管理安装 |
| uv | 0.12.2 | 依赖/虚拟环境管理 |
| openai-agents | 0.19.4 | 多智能体框架 |
| Pydantic | v2 | 结构化输出 schema |
| 搜索 | Tavily API + Bing/DDG/Baidu 抓取 | Tavily 优先，抓取兜底 |
| Trafilatura | 2.2.0 | 网页正文抽取 |
| Rich | 15.x | CLI 美化 |
| Ollama | 0.32.6 | 本地模型推理（qwen3:4b） |
| pytest / ruff | - | 108 个单测 / 代码规范 |

**当前状态**：✅ 端到端可跑；✅ 证据链/热点路由已加入；✅ 来源编号与引文校验已加入；✅ FastAPI/Docker/Skill 入口已加入；✅ 108 个测试通过。

---

## 2. 交接清单（接手者第一步）

按顺序执行，全部通过即表示环境正常：

1. **确认 Ollama 在运行**：`curl http://127.0.0.1:11434/api/version`（有返回即可；无返回先 `ollama serve`）
2. **确认模型存在**：`ollama list` 应看到 `qwen3:4b`
3. **确认环境变量**：查看 `.env`（已 gitignore，不在仓库里；参考 `.env.example`）
4. **跑通单测**：`uv run pytest` → 应 108 passed
5. **跑一次真实研究**：`uv run research "ai岗位现状" --max-queries 2` → 生成报告到 `reports/`
6. **跑一次评估**：`uv run python evals/run_evals.py --limit 3 --max-queries 2` → 报告到 `evals/results/<时间戳>/`
7. **读文档**：`README.md`（用法）、`PROJECT_SUMMARY.md`（项目总结）、`evals/README.md`（评估体系）

---

## 3. 环境与依赖

### 3.1 软件清单（本机已装）

| 软件 | 位置/版本 | 备注 |
|---|---|---|
| uv | `C:\Users\haiju\.local\bin\uv.exe` v0.12.2 | PATH 可能未持久化，PowerShell 用 `$env:Path = "C:\Users\haiju\.local\bin;$env:Path"` |
| Python 3.12.13 | `uv python list` 可见 | 项目 .venv 已建好 |
| Ollama | `%LOCALAPPDATA%\Programs\Ollama\ollama.exe` v0.32.6 | 后台 `ollama serve` 运行中 |
| qwen3:4b | 默认模型目录 `C:\Users\haiju\.ollama` | 2.5GB，GPU 推理（RTX 3060） |

> 注意：Ollama 未注册为开机自启服务。电脑重启后需手动 `ollama serve`（或打开 Ollama 应用）。

### 3.2 `.env` 配置（复制 `.env.example` 修改）

```ini
RESEARCH_PROVIDER=local        # local=Ollama 本地 / openai=云端
OPENAI_API_KEY=                # 云端模式必填
LOCAL_MODEL=qwen3:4b           # 本地模型名（不加 ollama/ 前缀）
LOCAL_BASE_URL=http://127.0.0.1:11434/v1
SEARCH_BACKEND=auto            # auto|bing|ddg|baidu
```

provider 自动判断：有 `OPENAI_API_KEY` 用 openai，否则用 local。

---

## 4. 常用命令

```powershell
# 运行研究（本地模型）
uv run research "研究问题"
uv run research "问题" --max-queries 4          # 控制并行查询数
uv run research "问题" --provider openai        # 云端模式（需 key）
uv run research "问题" --no-save                # 只打印不保存
uv run research "问题" --no-clarify           # 跳过追问澄清
uv run research "问题" --use-memory --pdf    # RAG 记忆 + PDF 导出

# Web 界面（可选）
uv run --extra web streamlit run app.py

# API 服务
uv run research-api                             # FastAPI，默认 8000 端口

# 测试与规范
uv run pytest                                   # 108 个单元测试
uv run ruff check src tests evals               # 代码规范

# 评估
uv run python evals/run_evals.py --limit 3 --max-queries 2   # 快速
uv run python evals/run_evals.py --tags tech                  # 按标签
uv run python evals/run_evals.py --provider openai            # 云端
uv run python evals/run_evals.py --limit 3 --judge --verify-sources  # 进阶：judge+来源校验
uv run research "热点事件" --research-mode hot_topic --max-queries 4 --pdf

# 报告位置
# 研究报告 -> reports/<时间戳>-<标题>.md
# 评估报告 -> evals/results/<时间戳>/eval-report.md
```

---

## 5. 项目结构

```
deep-research-agent/
├── pyproject.toml            # 依赖与配置（用 uv 管理，锁定在 uv.lock）
├── .env.example / .env       # 环境变量（.env 不入库）
├── README.md                 # 使用文档
├── PROJECT_SUMMARY.md        # 项目总结（内容/基础/学习路径/改进方向）
├── HANDOVER.md               # 本文档
├── src/research_agent/
│   ├── agents.py             # Agent 定义 + build_agents(question)（动态语言指令）
│   ├── runner.py             # 编排：规划→并行研究（含空结果重试）→撰写→保存
│   ├── tools.py              # 自定义工具：多后端搜索 + 网页正文抽取
│   ├── guardrails.py         # 输入护栏（最小长度 4 字符，适配中文）
│   ├── models.py             # Pydantic schema：ResearchPlan/Notes/Report
│   ├── evals.py              # 评估评分逻辑（纯函数，可单测）
│   ├── formatting.py         # Markdown 渲染
│   ├── config.py             # 配置与 provider 选择
│   └── cli.py                # 命令行入口
├── evals/
│   ├── cases.jsonl           # 8 个评估用例（JSONL）
│   ├── run_evals.py          # 评估运行器
│   ├── README.md             # 评估说明
│   └── results/              # 历次评估报告（入库？默认 gitignore）
├── tests/                    # 42 个 pytest 用例
└── reports/                  # 生成的研究报告（gitignore）
```

---

## 6. 关键设计决策与踩坑记录（重要，别重复踩）

### 6.1 本地模型接入：不要用 LiteLLM
- **现象**：LiteLLM 走 Ollama 时，带 `response_format`（结构化输出）或 `tools` 的请求返回**空内容**，导致 Planner 反复校验失败 → Max turns exceeded。
- **结论**：Ollama 原生 `/api/chat` 和 OpenAI 兼容 `/v1/chat/completions` 都正常支持 tools + json_schema。
- **当前方案**：`runner._local_model()` 用 `OpenAIChatCompletionsModel` + `AsyncOpenAI(base_url=http://127.0.0.1:11434/v1)` 直连 Ollama。**不要改回 LiteLLM**。

### 6.2 `.ollama` 目录权限（Windows）
- **现象**：旧版 Ollama（管理员权限安装）创建的 `C:\Users\haiju\.ollama` 目录只有 Admin 可写，非提权进程 pull 模型报 Access denied。
- **解决**：`icacls "C:\Users\haiju\.ollama" /grant "haiju:(OI)(CI)F" /T`（需管理员）；模型已迁回默认目录。

### 6.3 Windows PowerShell 写文件 BOM 坑
- `Set-Content -Encoding UTF8` 在 PowerShell 5.1 会写 BOM，tomllib 解析 pyproject.toml 会报错。
- 写 Python/TOML 文件一律用 `[System.IO.File]::WriteAllText(path, content, [System.Text.UTF8Encoding]::new($false))`（无 BOM）。

### 6.4 终端编码 GBK 坑
- 中文 Windows 默认 GBK，输出非 GBK 字符（emoji、↻ 等）会崩溃（`UnicodeEncodeError`）。
- 处理：CLI 与 eval 脚本顶部 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`；关键日志避免特殊符号。

### 6.5 输入护栏阈值
- 最初要求 ≥10 字符，中文短问题（如"ai岗位现状"6 字符）被误拦截。
- 已改为 ≥4 字符（`guardrails.py` 的 `_MIN_LENGTH`），并让 CLI 显示具体拦截原因。

### 6.6 本地小模型的语言漂移
- qwen3:4b 对中文问题偶尔输出英文报告。
- 解决：`agents.language_instruction(question)` 按问题语言动态追加强约束，所有 Agent 经 `build_agents()` 构建。

### 6.7 搜索空结果不放弃
- 之前 Researcher 搜不到数据就产出"No data found"废报告。
- 解决：提示词强制重试 + 编排层 `notes_are_empty()` 判定后的确定性重试（`RETRY_PROMPT`）。

---

## 7. 测试与评估现状

### 7.1 单元测试（108 个）
覆盖：Pydantic 模型、输入护栏、搜索多后端兜底、网页抓取异常、评估评分（含语言/来源校验）、LLM-as-judge 解析、多模型接入、语言指令、空结果判定。

### 7.2 评估指标
| 指标 | 判定 |
|---|---|
| 结构完整 | title/summary/key_findings≥3/sources/limitations/recommendations 齐全 |
| 来源有效 | ≥1 个合法 http(s) URL（去重） |
| 语言一致 | 中文问题必须产出中文报告 |
| 关键词命中 | 信息性，不判失败 |
| 运行出错 | 直接 FAIL |

**通过 = 结构完整 + 来源有效 + 语言一致 + 未报错**

### 7.3 最近评估记录（本地 qwen3:4b，3 用例）
| 轮次 | 通过率 | 说明 |
|---|---|---|
| 修复前（2026-08-07 15:58） | 66.7% | 开源大模型用例 No data found；强化学习用例英文报告 |
| 修复后（2026-08-07 16:54） | 100% | 三项全过，关键词命中率 100% |

---

## 8. 已知问题与限制

1. **本地模型可能编造事实**：qwen3:4b 偶发幻觉；当前代码会过滤未观察到的 URL、搜索结果页和无法逐字匹配引文的发现，但仍需人工核验来源独立性与事实含义。
2. **搜索后端不稳**：Bing 抓取偶尔返回空或相关度差 → 强烈建议配置 TAVILY_API_KEY（免费），
esearch_sources/
ews_search 已接入 Tavily。
3. **本地模型随机性**：同一问题多次运行结果不同 → 评估看趋势，建议多轮取平均。
4. **OpenAI 云端模式未端到端验证**：代码路径已实现，但本机无 API key，未实测。
5. **Ollama 非开机自启**：重启后需手动启动。
6. ✅ 已解决：新增 --verify-sources 实际请求每个 URL 校验可访问性（仍建议人工核对内容真实性）。
7. **Streamlit 不会热重载已导入的 Python 包**：升级代码后必须重启 Web 服务（关闭旧实例再启动），否则会报 unexpected keyword argument 之类的过期代码错误。
8. **证据链不是事实保证**：来源白名单会过滤模型虚构 URL，但“内容是否支持结论”仍需使用来源校验、证据摘录和人工复核；热点事件不可把单一媒体/社交来源标为已确认。

9. **来源编号协议**：运行内来源会显示为 `SRC-001`、`SRC-002`。模型输出可填写这些编号，编排层会在最终报告中还原为真实 URL；任何不在当前 registry 的编号或 URL 都会被删除。

---

## 9. 待办事项与路线图

### 短期（已排优先级）
- [ ] 扩大评估集（8 → 20-30 用例）
- [x] 评估增加"来源 URL 可访问性"真实校验
- [ ] 同一用例多轮运行，报告通过率稳定性
- [x] LLM-as-judge：用强模型给报告事实准确性打分

### 中期
- [x] Streamlit Web 界面
- [x] 追问澄清（human-in-the-loop，问题模糊时先问澄清问题）
- [x] RAG 知识库（ChromaDB + Ollama 嵌入，历史报告自动入库与检索）
- [x] 搜索质量优化：Tavily API + research_sources/news_search + 日期注入
- [x] PDF 导出（reportlab + 中文字体）
- [x] 证据链与热点事件核验模式
- [x] FastAPI + Docker Compose 服务化配置
- [x] Codex Skill 包装
- [ ] 更多模型提供方（DeepSeek/GLM 等 OpenAI 兼容端点）

### 长期
- [x] Docker 部署 + API 服务化配置
- [ ] OpenAI Tracing / LangSmith 可观测性
- [ ] 主动型 Agent（定时监控 + 自动简报）

---

## 10. Git 历史

```
1780e2a fix: researcher empty-search retry, enforce output language, eval language check + GBK-safe logging
5866a8d feat: add evals module (cases, scoring, runner, report) + tests
73f9a7c docs: add project summary (content, prerequisites, learning path, improvements)
648fbd7 fix: lower input-guardrail min length for Chinese topics (10->4 chars) and surface guardrail reason in CLI
baec642 refactor: connect local Ollama via OpenAI-compatible /v1 endpoint; polish README
722857d feat: multi-agent deep research assistant (Planner/Researcher/Writer) with multi-backend search, guardrails, structured outputs, and dual OpenAI/Ollama providers
```

---

## 11. 联系方式 / 备注

- 项目由 Codex 协助开发，可在本地直接继续对话迭代。
- 生成报告默认保存在 `reports/`，评估报告在 `evals/results/`，均不入 git（见 `.gitignore`）。
- 若要把项目推到 GitHub 作为简历项目：建议新建公开仓库，把 `reports/`、`evals/results/`、`.env` 保持忽略，README 已在说明使用方式。
