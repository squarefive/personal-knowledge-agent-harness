---
title: "Personal Knowledge Agent Harness 代码地图"
last_updated: "2026-06-28"
---

# Personal Knowledge Agent Harness 代码地图

> 本文档用于快速了解代码目录和代码文件职责。
> 它只描述当前代码结构，不定义 Agent 能力边界，不替代 `docs/agents/cloud-qa-knowledge-agent.md`。

## 目录说明

| 目录 | 作用 |
|---|---|
| `src/personal_knowledge_agent/` | 项目主 Python 包，只保留公共包入口和按职责划分的子目录。 |
| `src/personal_knowledge_agent/agent_bootstrap/` | Agent 运行配置和跨模块组件装配。 |
| `src/personal_knowledge_agent/agent_runtime/` | Agent loop 运行时，包括 LLM 调用、tool call、最终回答、来源证据和事件发射。 |
| `src/personal_knowledge_agent/agent_context/` | Agent 每轮上下文，包括 prompt、conversation session、Agent profile memory 和 tool result compact。 |
| `src/personal_knowledge_agent/agent_context/conversation_sessions/` | `.sessions/` transcript、metadata、summary 和 artifact 管理。 |
| `src/personal_knowledge_agent/agent_context/agent_profile_memory/` | `.memory/` Agent profile memory 读取和 memory candidate 提取。 |
| `src/personal_knowledge_agent/agent_tools/` | LLM 可调用工具 adapter。 |
| `src/personal_knowledge_agent/agent_tools/qa_knowledge_tools/` | Q&A 知识工具 handler。 |
| `src/personal_knowledge_agent/agent_tools/agent_memory_tools/` | Agent memory 读取工具 handler。 |
| `src/personal_knowledge_agent/agent_tools/todo_tools/` | Todo 待办工具 handler。 |
| `src/personal_knowledge_agent/qa_data_access/` | 旧默认路径的 Q&A card SQLite 和 Qdrant 数据访问。 |
| `src/personal_knowledge_agent/todo_data_access/` | Todo 待办项的 SQLite 数据访问。 |
| `src/personal_knowledge_agent/auth/` | 邮箱验证码登录的认证核心服务和仓储协议。 |
| `src/personal_knowledge_agent/postgres/` | PostgreSQL 连接池和基础 schema 初始化。 |
| `src/personal_knowledge_agent/tool_runtime/` | 通用 tool dispatcher。 |
| `src/personal_knowledge_agent/llm_clients/` | LLM provider client。 |
| `src/personal_knowledge_agent/mail/` | SMTP 邮件发送 adapter。 |
| `src/personal_knowledge_agent/security/` | secrets 读取、token hash 和日志敏感键脱敏工具。 |
| `src/personal_knowledge_agent/agent_observability/` | Agent 运行事件日志等可观测性适配。 |
| `src/personal_knowledge_agent/apps/cli/` | CLI app 入口和事件渲染。 |
| `src/personal_knowledge_agent/apps/web/` | 本地 Web app、Web 入口和静态资源。 |
| `docs/` | 项目文档目录。 |
| `docs/agents/` | Agent 稳定设计边界文档目录；当前边界文档为 `cloud-qa-knowledge-agent.md`。 |
| `docs/architecture/` | 代码地图等架构说明文档目录。 |
| `docs/guidelines/` | AI Coding 协作偏好和行为规约目录。 |
| `docs/templates/` | Agent 开发上下文和代码地图模板目录。 |
| `deploy/` | 单机 Docker Compose 部署底座、nginx HTTP 临时反代配置和服务器部署说明。 |
| `scripts/` | 本地维护和格式检查脚本。 |
| `tests/` | 自动化测试。 |

## 文件说明

### Root Module

模块目录：`src/personal_knowledge_agent/`

模块作用：提供 Python 包和 CLI 公共入口。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 标记 Python 包。 |
| `__main__.py` | CLI 根入口薄转发，供 `python -m personal_knowledge_agent` 和 `pka` 使用。 |

### Root Deployment

模块目录：项目根目录

模块作用：提供容器镜像构建入口。

| 文件 | 作用 |
|---|---|
| `Dockerfile` | 构建运行 Web app 的生产容器镜像，设置 `PYTHONPATH=/app/src` 并使用 `python -m personal_knowledge_agent web --host 0.0.0.0 --port 8787 --no-open` 启动。 |

### Agent Bootstrap

模块目录：`src/personal_knowledge_agent/agent_bootstrap/`

模块作用：加载运行配置并装配 Agent 的跨模块依赖。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出 Agent bootstrap 公共入口。 |
| `agent_component_factory.py` | 创建 Agent loop runner、Q&A、todo、memory tool handler 及其依赖。 |
| `agent_runtime_config.py` | 从 `.env` 和环境变量读取运行配置。 |

### Agent Runtime

模块目录：`src/personal_knowledge_agent/agent_runtime/`

模块作用：负责 Agent loop 运行链路。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出 Agent runtime 组件。 |
| `agent_loop_runner.py` | Agent loop 核心调用链。 |
| `agent_llm_call_runner.py` | 单次 Agent LLM 调用和事件。 |
| `agent_tool_call_runner.py` | 单次 tool call、权限、compact 和事件。 |
| `agent_answer_finalizer.py` | 最终回答来源校验、消息追加和 memory candidate 收尾。 |
| `agent_llm_message_formatter.py` | assistant tool call 和 tool result 的 LLM message 格式化。 |
| `agent_runtime_message_recorder.py` | runtime messages、transcript 和 metadata count 记录。 |
| `answer_source_evidence.py` | 从本轮真实 tool result 提取和渲染回答来源。 |
| `agent_event_emitter.py` | Agent run 事件发射适配。 |
| `agent_events.py` | 定义 Agent 运行事件和 run_id 生成。 |

### Agent Context

模块目录：`src/personal_knowledge_agent/agent_context/`

模块作用：负责 Agent 每轮可用上下文。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出 Agent context 组件。 |
| `agent_prompt_builder.py` | 构建运行时 system prompt。 |
| `agent_turn_context_loader.py` | turn-start memory index 和相关 memory 加载。 |

### Conversation Sessions

模块目录：`src/personal_knowledge_agent/agent_context/conversation_sessions/`

模块作用：管理 `.sessions/` 会话恢复数据。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出 conversation session 组件。 |
| `conversation_transcript_repository.py` | 追加和读取 `.sessions/<session_id>/transcript.jsonl`。 |
| `conversation_session_metadata_repository.py` | 读写 `.sessions/<session_id>/metadata.json`。 |
| `conversation_session_restorer.py` | 从 transcript 或 summary 恢复 runtime messages。 |
| `conversation_session_summarizer.py` | 长 transcript 自动总结和失败降级。 |
| `tool_result_compactor.py` | 大工具结果落盘和 compact record 生成。 |
| `conversation_session_models.py` | 定义 session metadata、restore result 和 compact record。 |

### Agent Profile Memory

模块目录：`src/personal_knowledge_agent/agent_context/agent_profile_memory/`

模块作用：读取 Agent profile memory 并生成候选记忆。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出 Agent profile memory 组件。 |
| `agent_memory_index_repository.py` | 读取和校验 `.memory/MEMORY.md`。 |
| `agent_memory_document_repository.py` | 读取和校验 `.memory/*.md`。 |
| `agent_memory_candidate_extractor.py` | 从 turn 结果中提取 memory candidates。 |
| `agent_memory_turn_finalizer.py` | turn-end memory candidate 事件收尾。 |
| `agent_memory_models.py` | 定义 memory index、document 和 candidate 数据结构。 |

### Agent Tools

模块目录：`src/personal_knowledge_agent/agent_tools/`

模块作用：提供 LLM 可调用工具 adapter。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出 Agent tool handler。 |
| `qa_knowledge_tools/qa_knowledge_tool_handlers.py` | Q&A 保存、检索、读取、更新、删除、最近列表和语义索引维护工具。 |
| `agent_memory_tools/agent_memory_tool_handlers.py` | Agent memory 读取工具 adapter。 |
| `todo_tools/todo_tool_handlers.py` | Todo 保存、查询和更新工具。 |

### QA Data Access

模块目录：`src/personal_knowledge_agent/qa_data_access/`

模块作用：管理 Q&A card 的 SQLite 事实库和 Qdrant 语义索引。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出 Q&A 数据访问组件。 |
| `qa_card_models.py` | 定义 Q&A card、关键词检索结果和语义检索命中数据结构。 |
| `qa_card_repository.py` | 初始化和读写 SQLite `qa_cards` 表。 |
| `qa_card_semantic_index.py` | 封装 DashScope embedding 和 Qdrant local mode 语义索引。 |
| `duplicate_detection.py` | 提供本地 Q&A 全库重复检测服务，负责候选召回、相似度打分和重复组构建。 |

### Todo Data Access

模块目录：`src/personal_knowledge_agent/todo_data_access/`

模块作用：管理 todo 待办项的 SQLite 事实表。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出 todo 数据访问组件。 |
| `todo_models.py` | 定义 todo 待办项数据结构。 |
| `todo_repository.py` | 初始化和读写 SQLite `todo_items` 表。 |

### Auth

模块目录：`src/personal_knowledge_agent/auth/`

模块作用：提供不依赖 Web、SMTP 或真实 PostgreSQL 的邮箱验证码登录核心服务。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出认证服务公共类型。 |
| `auth_models.py` | 定义认证用户、验证码、登录态和认证结果数据结构。 |
| `auth_service.py` | 定义认证仓储协议和验证码登录核心流程。 |

### PostgreSQL

模块目录：`src/personal_knowledge_agent/postgres/`

模块作用：提供云端化 PostgreSQL 基础设施，不接入现有 SQLite / Qdrant repository。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出 PostgreSQL 基础设施公共入口。 |
| `auth_repository.py` | 实现邮箱验证码登录 AuthRepository Protocol 的 PostgreSQL 仓储。 |
| `memory_repository.py` | 实现按 `user_id` 隔离的 PostgreSQL user-preference memory 读取仓储。 |
| `postgres_pool.py` | 从 `database_url` 创建连接池并关闭连接池。 |
| `qa_repository.py` | 实现按 `user_id` 隔离的 PostgreSQL Q&A card 数据访问。 |
| `qa_semantic_index.py` | 实现基于 PostgreSQL / pgvector 的 Q&A 语义索引适配。 |
| `schema.py` | 执行 pgvector 扩展和最小业务表的幂等 schema 初始化。 |
| `session_repository.py` | 实现按 `user_id` 隔离的 PostgreSQL conversation session 数据访问。 |
| `session_runtime_adapters.py` | 将 PostgreSQL session 仓储适配为 Agent runtime transcript、metadata、summary 和 compact 依赖。 |
| `todo_repository.py` | 实现按 `user_id` 隔离的 PostgreSQL todo 数据访问。 |

### Tool Runtime

模块目录：`src/personal_knowledge_agent/tool_runtime/`

模块作用：汇总 Q&A、todo 与 Agent memory handler，执行 LLM tool call 分发、权限判断和展示字段筛选。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出 tool runtime 公共类型和函数。 |
| `tool_dispatcher.py` | 注册两个独立 handler，将 ToolCall 分发到具体方法并筛选展示字段。 |
| `tool_models.py` | 定义 ToolCall 数据结构。 |
| `tool_permission_policy.py` | 定义工具权限判断、审批请求和拒绝结果。 |

### LLM Clients

模块目录：`src/personal_knowledge_agent/llm_clients/`

模块作用：适配外部 LLM provider。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出 LLM client。 |
| `deepseek_chat_client.py` | DeepSeek streaming chat 薄客户端和响应转换。 |
| `llm_models.py` | 定义 LLMResponse 数据结构。 |
| `qwen_embedding_client.py` | Qwen / DashScope embedding 薄客户端。 |

### Mail

模块目录：`src/personal_knowledge_agent/mail/`

模块作用：提供 QQ SMTP 等邮件发送能力，不承载认证流程或 Web 路由。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出 SMTP 邮件发送公共类型。 |
| `smtp_email_sender.py` | 构造并发送邮箱验证码邮件，支持 SSL 和 STARTTLS。 |

### Security

模块目录：`src/personal_knowledge_agent/security/`

模块作用：提供云端配置阶段需要的最小安全辅助函数，不实现登录流程或日志系统。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出 security 公共 helper。 |
| `secrets.py` | 从环境变量或优先级更高的 `*_FILE` 文件读取 secret。 |
| `token_hashing.py` | 生成随机 token、6 位验证码，并提供 token hash 与 constant-time 校验。 |
| `log_redaction.py` | 对 mapping 中常见敏感键执行最小脱敏。 |

### Agent Observability

模块目录：`src/personal_knowledge_agent/agent_observability/`

模块作用：记录 Agent 运行事件。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 导出 Agent observability 组件。 |
| `agent_event_jsonl_logger.py` | 异步写入 Agent 运行 JSONL 开发日志。 |

### Apps

模块目录：`src/personal_knowledge_agent/apps/`

模块作用：提供 CLI 和 Web app 入口。

| 文件 | 作用 |
|---|---|
| `cli/cli_main.py` | CLI 持续交互入口和 `pka web` 子命令分发。 |
| `cli/cli_event_renderer.py` | CLI 事件渲染和长文本截断。 |
| `web/web_app.py` | 创建 FastAPI app，提供流式聊天、session 管理和卡片浏览 API。 |
| `web/cloud_dependencies.py` | 装配 Web 云端依赖，包括 PostgreSQL pool、AuthService、SMTP 邮件发送、用户绑定工具 factory 和会话仓储 facade。 |
| `web/web_main.py` | Web Runtime 启动入口。 |
| `web/static/index.html` | Web UI 页面结构，包括验证码登录门和登录后的工作台壳。 |
| `web/static/styles.css` | Web UI 样式。 |
| `web/static/app.js` | 浏览器端认证门、聊天、session 和卡片浏览逻辑。 |

### Public Web Launcher

模块目录：`src/personal_knowledge_agent/web/`

模块作用：保留公开的 `python -m personal_knowledge_agent.web` 启动方式，不承载业务实现。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 标记 Web 启动包。 |
| `__main__.py` | 转发到 `apps/web/web_main.py`。 |

### Docs

模块目录：`docs/`

模块作用：保存项目协作规约、Agent 稳定设计边界、代码地图和模板。

| 文件 | 作用 |
|---|---|
| `agents/cloud-qa-knowledge-agent.md` | 云端个人 Q&A 知识库 Agent 的稳定设计边界和验收依据。 |
| `architecture/codebase-map.md` | 当前代码目录和文件职责地图。 |
| `guidelines/collaboration-preferences.md` | 用户协作偏好、计划、分支和提交规则。 |
| `guidelines/ai-coding-behavior.md` | AI Coding 调研、修改和验证行为规约。 |
| `templates/agent-development-context.template.md` | Agent 开发上下文文档模板。 |
| `templates/codebase-map.template.md` | 代码地图文档模板。 |

### Deploy

模块目录：`deploy/`

模块作用：保存单机云端 Docker Compose 部署底座和服务器侧操作说明。

| 文件 | 作用 |
|---|---|
| `.gitignore` | 忽略服务器本地 secrets、backups、override compose 和本地 env 文件。 |
| `docker-compose.yml` | 编排 Web app、PostgreSQL pgvector 和 nginx；数据库只在 Compose 内网暴露。 |
| `nginx.conf` | 提供 HTTP 临时反代和 SSE 基本代理设置。 |
| `requirements.txt` | Docker 构建使用的生产 Python 依赖锁定清单，由 `uv export --no-dev --format requirements-txt --no-hashes` 生成。 |
| `README.md` | 说明服务器 root-only secrets 文件、QQ SMTP、数据库 URL、API key、session secret 和临时 HTTP 边界。 |

### Scripts

模块目录：`scripts/`

模块作用：提供本地维护、格式检查和辅助脚本。

| 文件 | 作用 |
|---|---|
| `backfill-qa-categories.py` | 为历史 Q&A 卡片生成 category 并重建 category 约束。 |
| `check-agents-md-format.py` | 检查 `AGENTS.md` 的入口文档规约。 |
| `check-agent-doc-format.py` | 检查 Agent 开发上下文模板、具体 Agent 文档格式和文档篇幅告警。 |
| `check-codebase-map-format.py` | 检查代码地图模板和实际代码地图格式。 |
| `clean-merged-branches.sh` | 清理已合并的本地分支。 |
| `init-postgres-schema.py` | 从 `DATABASE_URL` / `DATABASE_URL_FILE` 读取连接串并初始化 PostgreSQL schema。 |
| `backup-postgres.sh` | 从 `DATABASE_URL` / `DATABASE_URL_FILE` 读取连接串，执行 `pg_dump | gzip` 并保留最近 N 份备份。 |
| `backup-postgres-compose.sh` | 在单机 Docker Compose 部署中通过 `postgres` 容器执行 `pg_dump | gzip`，避免数据库暴露到宿主机端口。 |
| `migrate-sqlite-qa-to-postgres.py` | 将旧 SQLite `qa_cards` 迁移到指定邮箱对应的 PostgreSQL 用户，不迁移 session、todo、memory 或 Qdrant。 |
| `rebuild-postgres-qa-embeddings.py` | 为指定邮箱用户的 PostgreSQL Q&A 卡片重建 pgvector embedding。 |

### Tests

模块目录：`tests/`

模块作用：验证各模块的单元行为、集成流程和回归约束。

| 文件 | 作用 |
|---|---|
| `test_agent_factory.py` | 覆盖 Agent 组件装配。 |
| `test_agent_loop.py` | 覆盖 Agent loop 的工具调用、权限、消息和最终回答流程。 |
| `test_tools.py` | 覆盖 Agent tool handler 和 tool dispatcher。 |
| `test_todo_tools.py` | 覆盖 todo tool handler 和 tool dispatcher 集成。 |
| `test_sqlite_store.py` | 覆盖 Q&A card repository。 |
| `test_todo_store.py` | 覆盖 todo repository。 |
| `test_qa_semantic_index.py` | 覆盖 Q&A semantic index。 |
| `test_config.py` | 覆盖运行配置和 secret 文件读取。 |
| `test_security.py` | 覆盖 secret 读取、token hash 和敏感键脱敏。 |
| `test_auth_service.py` | 覆盖邮箱验证码登录核心服务。 |
| `test_mailer.py` | 覆盖 SMTP 邮件发送 adapter。 |
| `test_postgres_auth_repository.py` | 覆盖 PostgreSQL 认证仓储 SQL 参数化、字段映射和 hash-only 写入。 |
| `test_postgres_qa_repository.py` | 覆盖 PostgreSQL Q&A card repository 的用户隔离、字段映射和参数化 SQL。 |
| `test_postgres_qa_semantic_index.py` | 覆盖 PostgreSQL / pgvector Q&A 语义索引适配。 |
| `test_postgres_schema.py` | 覆盖 PostgreSQL schema 初始化 SQL 和幂等执行。 |
| `test_init_postgres_schema.py` | 覆盖 PostgreSQL schema 初始化脚本的 `DATABASE_URL` / `DATABASE_URL_FILE` 读取和初始化调用。 |
| `test_postgres_session_repository.py` | 覆盖 PostgreSQL conversation session repository 的用户隔离、消息 JSONB 和状态更新。 |
| `test_postgres_todo_repository.py` | 覆盖 PostgreSQL todo repository 的用户隔离、状态校验和参数化 SQL。 |
| `test_migrate_sqlite_qa_to_postgres.py` | 覆盖 SQLite Q&A 到 PostgreSQL 迁移脚本的 CLI、用户查找、字段解析、dry-run 和 upsert SQL。 |
| `test_rebuild_postgres_qa_embeddings.py` | 覆盖 PostgreSQL Q&A embedding 重建脚本的用户定位、成功和失败续跑。 |
| `test_check_agents_md_format.py` | 覆盖 `AGENTS.md` 规约检查脚本。 |
| `test_check_agent_doc_format.py` | 覆盖 Agent 文档格式检查脚本。 |
| `test_web_app.py` | 覆盖 Web API、SSE 聊天、session 隔离和卡片接口。 |
| `test_web_cloud_dependencies.py` | 覆盖 Web 云端依赖装配和 pool 生命周期。 |
| `test_cli.py` | 覆盖 CLI 输入循环、退出、错误处理和审批交互。 |
| `test_*.py` | 其他测试覆盖配置、日志、session、memory、source evidence 和 LLM client。 |
