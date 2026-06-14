---
title: "Personal Knowledge Agent Harness 代码地图"
last_updated: "2026-06-15"
---

# Personal Knowledge Agent Harness 代码地图

> 本文档用于快速了解代码目录和代码文件职责。
> 它只描述当前代码结构，不定义 Agent 能力边界，不替代 Agent 开发上下文文档。

## 目录说明

| 目录 | 作用 |
|---|---|
| `src/personal_knowledge_agent/` | 项目主 Python 包，包含 CLI、Agent 装配、LLM、Prompt、权限、事件和公共数据结构。 |
| `src/personal_knowledge_agent/agent_loop/` | Agent 单轮执行流程，包括上下文加载、LLM 调用、工具调用、来源处理和消息记录。 |
| `src/personal_knowledge_agent/tools/` | LLM 可调用工具和工具分发。 |
| `src/personal_knowledge_agent/qa_store/` | SQLite Q&A 知识卡片事实库。 |
| `src/personal_knowledge_agent/agent_memory/` | `.memory/` Agent 长期工作记忆读取和候选提取。 |
| `src/personal_knowledge_agent/session_memory/` | `.sessions/` 会话恢复、transcript、metadata、summary 和 artifact 管理。 |
| `src/personal_knowledge_agent/web/` | 本地 Web Runtime、HTTP API 和静态资源入口。 |
| `src/personal_knowledge_agent/web/static/` | 浏览器端 Chat + Cards 页面。 |
| `docs/` | 项目文档目录。 |
| `docs/agents/` | 具体 Agent 开发上下文文档。 |
| `docs/architecture/` | 代码结构导航文档。 |
| `docs/guidelines/` | 本地协作和 AI Coding 行为规约。 |
| `docs/templates/` | 可复用文档模板。 |
| `scripts/` | 本地维护和文档格式检查脚本。 |
| `tests/` | 自动化测试。 |

## 文件说明

### 根模块

模块目录：`src/personal_knowledge_agent/`

模块作用：提供项目入口、配置、装配、LLM、Prompt、权限、事件、日志和公共数据结构。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 标记 Python 包。 |
| `__main__.py` | CLI 入口，负责启动交互式命令行或分发到 Web Runtime。 |
| `agent_factory.py` | 装配 AgentLoop、工具、SQLite、LLM、session memory、agent memory 和语义索引。 |
| `cli_renderer.py` | 将 Agent 事件渲染为 CLI 用户可见输出。 |
| `config.py` | 从 `.env` 和环境变量读取运行配置。 |
| `events.py` | 定义 Agent 运行事件和 run_id 生成。 |
| `jsonl_logger.py` | 异步写入 Agent 运行 JSONL 开发日志。 |
| `llm_client.py` | DeepSeek streaming chat 薄客户端和响应转换。 |
| `permissions.py` | 定义工具权限判断、审批请求和拒绝结果。 |
| `prompt_builder.py` | 构建运行时 system prompt。 |
| `qa_semantic_index.py` | 封装 DashScope embedding 和 Qdrant local mode 语义索引。 |
| `schemas.py` | 定义轻量数据结构，包括 Q&A 卡片、工具调用、LLM 响应、session 和 memory 数据。 |

### Agent Loop 模块

模块目录：`src/personal_knowledge_agent/agent_loop/`

模块作用：负责单轮 Agent 执行流程，包括 LLM 调用、工具调用、消息记录、来源校验和 memory candidate 提取。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出 AgentLoop。 |
| `call_llm.py` | 封装单次 LLM 调用、文本增量回调和 LLM 阶段事件。 |
| `emit_agent_events.py` | 封装 Agent 事件发射。 |
| `finalize_turn_memory.py` | 在 turn 结束时生成 memory candidates 事件。 |
| `finish_answer.py` | 收尾最终回答，执行来源处理并追加 assistant message。 |
| `format_llm_messages.py` | 将 assistant tool call 和 tool result 格式化为 LLM messages。 |
| `load_turn_context.py` | 加载 memory index 并选择本轮相关 Agent memory。 |
| `loop.py` | Agent 主循环，维护 messages、调用 LLM、执行工具并生成最终回答。 |
| `record_runtime_messages.py` | 记录 runtime messages、追加 transcript 并更新 metadata 计数。 |
| `run_tool_call.py` | 执行单个工具调用、权限确认、tool result compact 和事件发射。 |
| `source_evidence.py` | 从本轮真实工具结果提取来源，并重写最终回答来源区块。 |

### Tools 模块

模块目录：`src/personal_knowledge_agent/tools/`

模块作用：提供 LLM 可调用工具的实现和分发入口。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出 KnowledgeTools 和 ToolDispatcher。 |
| `dispatch_tool_call.py` | 将 ToolCall 分发到具体工具 handler，并筛选可展示输入输出字段。 |
| `knowledge_tools.py` | 实现 Q&A 保存、检索、读取、更新、删除、最近列表、语义索引维护和 Agent memory 读取工具。 |

### Q&A Store 模块

模块目录：`src/personal_knowledge_agent/qa_store/`

模块作用：管理 SQLite Q&A 卡片事实库。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出 SQLiteStore。 |
| `sqlite_store.py` | 初始化和读写 `qa_cards`，支持保存、读取、更新、删除、LIKE 检索、最近列表、category 和向量化标记。 |

### Agent Memory 模块

模块目录：`src/personal_knowledge_agent/agent_memory/`

模块作用：读取 `.memory/` Agent 工作记忆，并从 turn 结果中生成候选记忆。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出 memory index、memory document 和 extractor 相关类。 |
| `document_store.py` | 读取和校验 `.memory/*.md` memory 文档。 |
| `extract_memory_candidates.py` | 从用户输入、最终回答和上下文中提取 memory candidates。 |
| `index_store.py` | 读取和校验 `.memory/MEMORY.md` memory 索引。 |

### Session Memory 模块

模块目录：`src/personal_knowledge_agent/session_memory/`

模块作用：管理 `.sessions/` 中的 transcript、metadata、summary 和 compact artifact。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出 session memory 相关类和校验函数。 |
| `compact_tool_result.py` | 将过大的 tool result 写入 artifact，并生成 compact record。 |
| `metadata.py` | 读写 session metadata，支持 session 列表和重命名。 |
| `restore_session.py` | 从 transcript 或 summary 恢复 runtime messages。 |
| `summarize_session.py` | 调用 LLM 生成长 transcript 的 session summary。 |
| `transcript.py` | 追加和读取 transcript，并派生 Web 可展示历史消息。 |

### Web Runtime 模块

模块目录：`src/personal_knowledge_agent/web/`

模块作用：提供本地浏览器入口、Web API 和 session 隔离的聊天运行时。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 标记 Web Runtime 包。 |
| `__main__.py` | Web Runtime 启动入口。 |
| `app.py` | 创建 FastAPI app，提供流式聊天、session 管理和 Q&A 卡片浏览 API。 |

### Web Static 模块

模块目录：`src/personal_knowledge_agent/web/static/`

模块作用：提供浏览器端 Chat + Cards 页面。

| 文件 | 作用 |
|---|---|
| `app.js` | 浏览器端聊天、SSE 事件处理、session 切换和卡片浏览逻辑。 |
| `index.html` | Web UI 页面结构。 |
| `styles.css` | Web UI 样式。 |

### Scripts 模块

模块目录：`scripts/`

模块作用：提供本地维护、格式检查和辅助脚本。

| 文件 | 作用 |
|---|---|
| `backfill-qa-categories.py` | 为历史 Q&A 卡片生成 category 并重建 category 约束。 |
| `check-agent-doc-format.py` | 检查 Agent 开发上下文模板和具体 Agent 文档格式。 |
| `check-codebase-map-format.py` | 检查代码地图模板和实际代码地图格式。 |
| `clean-merged-branches.sh` | 清理已合并的本地分支。 |

### Docs 模块

模块目录：`docs/`

模块作用：保存 Agent 设计、代码地图、协作规约和文档模板。

| 文件 | 作用 |
|---|---|
| `agents/local-qa-knowledge-agent.md` | 本地个人 Q&A 知识库 Agent 开发上下文文档。 |
| `architecture/codebase-map.md` | 当前项目代码目录和文件职责地图。 |
| `guidelines/ai-coding-behavior.md` | AI Coding 行为规约。 |
| `guidelines/collaboration-preferences.md` | 用户协作偏好和变更控制规则。 |
| `templates/agent-development-context.template.md` | Agent 开发上下文模板。 |
| `templates/codebase-map.template.md` | 代码地图模板。 |

### Tests 模块

模块目录：`tests/`

模块作用：验证各模块的单元行为、集成流程和回归约束。

| 文件 | 作用 |
|---|---|
| `test_agent_factory.py` | 覆盖 Agent 组件装配。 |
| `test_agent_loop.py` | 覆盖 AgentLoop 的工具调用、权限、消息和最终回答流程。 |
| `test_backfill_qa_categories.py` | 覆盖历史 category 回填脚本。 |
| `test_cli.py` | 覆盖 CLI 输入循环、退出、错误处理和审批交互。 |
| `test_cli_renderer.py` | 覆盖 CLI 事件渲染和长文本截断。 |
| `test_config.py` | 覆盖 `.env` 和环境变量配置读取。 |
| `test_context_compactor.py` | 覆盖 tool result compact 和 artifact 写入。 |
| `test_jsonl_logger.py` | 覆盖异步 JSONL 日志写入和降级行为。 |
| `test_llm_client.py` | 覆盖 DeepSeek 客户端请求、流式解析、tool call 聚合和重试。 |
| `test_memory_extractor.py` | 覆盖 memory candidate 提取规则。 |
| `test_memory_index.py` | 覆盖 memory index 读取和格式校验。 |
| `test_memory_store.py` | 覆盖 memory 文档读取和 frontmatter 校验。 |
| `test_permissions.py` | 覆盖工具权限判断和拒绝结果。 |
| `test_prompt_builder.py` | 覆盖 system prompt 的关键规则。 |
| `test_qa_semantic_index.py` | 覆盖 Q&A 语义索引启用判断和向量操作。 |
| `test_session_metadata.py` | 覆盖 session metadata 创建、更新、列表和重命名。 |
| `test_session_restore.py` | 覆盖 session messages 恢复策略。 |
| `test_session_summarizer.py` | 覆盖长 transcript summary 生成和失败降级。 |
| `test_session_transcript.py` | 覆盖 transcript 追加、读取和 Web 历史消息派生。 |
| `test_source_evidence.py` | 覆盖最终回答来源提取、去重和无证据声明清理。 |
| `test_sqlite_store.py` | 覆盖 SQLiteStore 的 Q&A 卡片读写、检索、category 和向量化标记。 |
| `test_tools.py` | 覆盖 KnowledgeTools 的输入校验、工具结果和 hybrid 检索。 |
| `test_web_app.py` | 覆盖 Web API、SSE 聊天、session 隔离和卡片接口。 |
