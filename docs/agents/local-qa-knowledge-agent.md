---
module: "local-qa-knowledge-agent"
title: "本地个人 Q&A 知识库"
language: "Python"
agent_type: "Tool-Using Agent / RAG Agent"
last_updated: "2026-06-07"
---

# 本地个人 Q&A 知识库 Agent 开发上下文

> **文档定位**  
> 本文档是面向人类开发者和 AI Coding 工具的 Agent 开发上下文文档。  
> 它用于约束本地个人 Q&A 知识库 Agent 的角色定位、能力边界、Harness 架构、可调用工具、上下文来源、核心业务流、数据模型和测试要求。  
> 本文档不是终端用户说明，也不是运行时 Prompt。

> **AI 阅读契约**  
> AI Coding 工具在生成、修改或重构代码时，必须遵守本文档定义的角色边界、工具边界、数据边界和业务流程。  
> 不得擅自扩大 Agent 权限，不得绕过声明的 Tool / Store 直接操作数据库、文件系统、外部接口或其他底层资源。  
> 不得新增未声明的核心流程、外部依赖、高风险操作或数据写入行为。  
> 涉及本 Agent 的新增、修改或重构时，AI Coding 工具必须先读取本文档，并以本文档作为实现边界和验收依据。  
> 如果实现前发现本文档与目标需求不一致，或需要调整 Agent 的角色边界、工具契约、数据模型、核心流程、外部依赖、权限规则等设计内容，必须先修改本文档，并将文档变更提交到本地 Git；在文档版本被锁定后，才能开始修改代码。  
> 禁止在同一次提交中混合 Agent 设计文档变更和对应代码实现变更，除非只是修正文档中的错别字、路径或示例。

---

## 1. Agent 定位与能力边界

- **背景**:  
  用户希望把零散 Q&A 转换为可检索、可追溯、可复用的本地知识资产。第一版只验证 Q&A 场景下的最小知识闭环。

- **核心价值**:  
  通过工具把用户提供的 Q&A 保存到本地 SQLite，并在后续提问时基于本地检索结果生成可追溯回答；同时通过用户可见的本地 Agent memory 和 session memory 维持长期协作连续性。

- **Agent 角色**:  
  本 Agent 是本地个人 Q&A 知识库 Agent，负责判断用户是在录入知识还是提问，并通过工具完成保存、检索、读取和列出最近卡片。

- **核心目标**:
  1. 能保存用户提供的一组 Q&A。
  2. 能从本地 SQLite 检索相关 Q&A 卡片。
  3. 能基于检索结果回答问题并引用来源。
  4. 在依据不足时明确拒答，不编造来源或事实。
  5. 能读取用户可见的 Agent memory，用于理解用户偏好、项目约束、长期反馈和引用入口。
  6. 能维护当前 CLI 进程内的 runtime `messages[]`，作为聊天上下文本体。
  7. 能将可恢复 messages 追加写入 `.sessions/<session_id>/transcript.jsonl`。
  8. 能在 transcript 过长时生成 `summary.md`，并用 summary + recent messages 恢复上下文。
  9. 能对过大的上下文材料做 compact，保留摘要、相关性说明和可回读 artifact。
  10. 能通过本地 Web Runtime 提供浏览器聊天入口和基础 Q&A 卡片浏览能力。

- **包含能力**:
  1. 录入用户提供的 Q&A。
  2. 由模型生成 summary 和 keywords。
  3. 通过工具保存 Q&A 卡片到 SQLite。
  4. 通过工具检索、读取和列出 Q&A 卡片。
  5. 基于检索结果组织回答。
  6. 回答时展示 card_id、原始问题、source_type 和 created_at。
  7. 读取 `.memory/MEMORY.md` 中的 Agent memory index。
  8. 按需读取少量相关 `.memory/*.md`，用于指导 Agent 协作行为。
  9. 从 `.sessions/<session_id>/transcript.jsonl` 恢复 runtime `messages[]`。
  10. 在长 transcript 场景下使用 `summary.md` + recent messages 恢复。
  11. 将过大的 tool result 写入 `.sessions/<session_id>/artifacts/`，并在上下文中保留 compact record。
  12. 在 turn 结束后提取 memory candidates，并通过事件暴露候选；当前不自动写入长期 memory 或维护待确认队列。
  13. 提供本地 HTML 聊天入口，作为 CLI Runtime 的浏览器替代输入输出层。
  14. 在 Web UI 中查看最近 Q&A 卡片、搜索 Q&A 卡片和查看卡片详情。

- **不包含能力**:
  1. 不做 Markdown Wiki。
  2. 不做文件监听或自动索引。
  3. 不做周报、日报或自动总结。
  4. 不做多 Agent。
  5. 不做向量数据库。
  6. 不做去重合并。
  7. 不做后台任务。
  8. 不做复杂权限系统。
  9. 不把 Agent memory 混入 Q&A 知识库来源。
  10. 不默认把完整历史对话作为长期记忆。
  11. 不默认把所有 `.memory/*.md` 全文注入每轮上下文。
  12. 不在本阶段实现向量检索、后台自动整理任务或复杂双向同步。
  13. Web 第一版不做卡片编辑、删除、合并、自动知识图谱、Wiki、文件监听、多 Agent 或后台任务。

- **最终版功能清单完成状态**:

| 模块 | 状态 | 当前实现边界 |
|---|---|---|
| Q&A 知识管理 | 部分完成 | 已实现保存 Q&A 卡片、读取卡片、LIKE 检索和最近卡片列表；尚未实现标题、分类、标签、编辑、删除、导入和导出。 |
| Markdown Wiki 管理 | 未完成 | 当前 Agent 明确不包含 Wiki、文件监听和自动索引；不得声称支持 Wiki 绑定、Markdown chunk、hash 或增量同步。 |
| 统一知识检索 | 部分完成 | 当前只有 `search_qa_cards`，检索范围仅限 SQLite `qa_cards`；尚未实现语义向量检索、混合检索、过滤器、检索调试或统一 `search_knowledge`。 |
| 来源追踪 | 部分完成 | Q&A 来源可追溯到 card_id、question、source_type 和 created_at；尚未支持 Markdown chunk、代码经验、手动笔记等来源类型，也没有程序级最终回答来源校验。 |
| 分类与标签体系 | 未完成 | 当前只保存 keywords，不存在分类/标签模型、列表、重命名、合并或相似标签建议。 |
| 知识去重与合并 | 未完成 | 当前明确不做去重合并；没有重复检测、相似知识检测、合并建议、差异展示、用户确认合并或原始来源保留流程。 |
| 代码经验管理 | 未完成 | 当前没有报错记录、解决方案、代码片段、项目复盘、错误信息检索或面试复盘素材生成能力。 |
| 复习系统 | 未完成 | 当前没有复习卡、今日待复习、复习结果、间隔重复、按标签/分类复习或自动小测题。 |
| 内容输出 | 未完成 | 当前明确不做周报、日报或自动总结；没有学习总结、周报、博客大纲、面试提纲、简历项目描述或项目复盘总结能力。 |
| Agent Harness | 部分完成 | 已实现 Agent Loop、Tool Dispatcher、Prompt Builder、运行时上下文拼接和工具调用结果回填；工具注册仍是静态映射，尚未形成完整可扩展注册机制。 |
| 后台任务 | 未完成 | 当前明确不做后台任务；没有后台 Wiki 同步、索引构建、批量摘要、任务状态、完成通知或失败重试。 |
| 权限与审计 | 部分完成 | 已实现运行事件和 JSONL 开发日志；删除、合并、覆盖、重建索引等高风险操作尚未实现，也没有对应确认流程或变更历史记录。 |
| 长期偏好记忆 | 部分完成 | 已支持读取 Agent memory index 和相关 memory，并能生成 memory candidates 事件；尚未实现偏好写入确认闭环，以及偏好查看、修改、删除。 |
| Web Chat + Cards | 部分完成 | 已实现本地 HTML 聊天入口、`POST /api/chat`、最近卡片、卡片搜索和卡片详情；不包含编辑、删除、合并或复杂知识图谱。 |

以上状态仅描述当前代码已实现能力，不代表最终版设计已被纳入当前 Agent 边界。若要实现未完成模块，必须先更新本文档中的角色边界、工具契约、数据模型、核心流程、失败模式和测试要求，并单独提交文档变更后再进入代码实现。

- **行为约束**:
  1. 凡是涉及长期记忆的动作，必须通过工具完成。
  2. Agent 不得声称已经保存、查询或更新实际未通过工具完成的数据。
  3. 回答问题前必须先检索本地知识库。
  4. 没有足够依据时必须明确说明本地知识库中没有找到足够依据。
  5. 回答不得引入无来源外部知识。
  6. Q&A 知识库和 Agent memory 必须分开。
  7. `.memory/*.md` 用于 Agent 长期工作记忆，不得作为 Q&A 回答的知识卡片来源。
  8. `.sessions/<session_id>/summary.md` 只表示当前会话 compact summary，不得当作长期事实来源。
  9. compact 只能缩减当前上下文窗口，不得替代长期记忆写入。
  10. memory candidate 只表示候选，不表示已写入长期 memory；当前实现不得声称候选已经保存。
  11. Web UI 只能展示和发起用户意图，不得绕过 AgentLoop、Tools 或 Store 执行业务动作。

---

## 2. Harness 架构与代码边界

> 本节说明 Agent Harness 的组成，以及各层职责边界。

- **Agent Loop 职责**:
  - 接收用户输入并维护本轮 messages。
  - 调用 Prompt Builder 获取 system prompt。
  - 调用 LLM Client。
  - 判断 LLM 是否返回 tool calls。
  - 调用 Tool Dispatcher 执行工具。
  - 将 tool result 回填 messages。
  - 在没有 tool calls 时返回最终回答。
  - 在关键阶段产生结构化运行事件，包括 `user_input_received`、`llm_call_started`、`llm_call_finished`、`tool_call_started`、`tool_call_finished`、`evidence_checked`、`final_answer_generated` 和 `error`。
  - 运行事件用于 CLI 实时展示和本地开发日志，不作为长期知识来源。
  - 运行事件只描述可审计过程，不暴露模型完整思考链。

- **Agent Factory 职责**:
  - `agent_factory.py` 负责创建 AgentLoop 及其依赖，包括 SQLiteStore、KnowledgeTools、ToolDispatcher、DeepSeekClient、session memory、Agent memory 和 context compactor。
  - 供 CLI Runtime 和 Web Runtime 复用同一套 Agent 装配逻辑。
  - 不负责 CLI 输入、Web HTTP 请求、HTML 渲染、浏览器打开或进程启动。

- **Prompt Builder 职责**:
  - 运行时拼接短 system prompt。
  - 包含身份、行为规则、工具使用规则、回答格式和拒答规则。
  - 在 turn-start 阶段接收 memory index、selected memories 和 session summary，并将其压缩注入本轮上下文。
  - 不保存业务数据。
  - 不承担数据库读写职责。

- **Memory Manager 职责**:
  - 读取 `.memory/MEMORY.md` memory index。
  - 按需读取少量相关 `.memory/*.md`。
  - 校验 memory frontmatter 和索引字段。
  - 当前仅提供 Agent memory 读取能力；尚未实现 memory candidate 写入入口、确认队列或索引更新流程。
  - 不直接回答用户知识问题。
  - 不把 Agent memory 写入 SQLite `qa_cards` 表。

- **Session Transcript 职责**:
  - 将 user message、assistant message、assistant tool call message 和 tool result message 追加写入 `.sessions/<session_id>/transcript.jsonl`。
  - CLI 重启时从 transcript 恢复 runtime `messages[]`。
  - transcript 只服务当前聊天上下文恢复，不作为 Q&A 知识来源。

- **Session Metadata 职责**:
  - 读写 `.sessions/<session_id>/metadata.json`。
  - 记录 session_id、cwd、model、created_at、updated_at、message_count、event_count、summary_status、summary_attempts 和 last_restore_mode。
  - 不保存 API key、secret、完整 headers 或非恢复必需 payload。

- **Session Restore / Summarizer 职责**:
  - 当 transcript 未超过预算时原样恢复 `messages[]`。
  - 当 transcript 超过预算时，调用 summarizer 生成 `.sessions/<session_id>/summary.md`。
  - summarizer 最多重试 3 次。
  - summarizer 失败时使用 first N messages + recovery notice + recent N messages 降级恢复。

- **Context Compactor 职责**:
  - 识别过大的 tool result 或旧上下文。
  - 将原始大输出写入 `.sessions/<session_id>/artifacts/`。
  - 在上下文中保留 compact record，包括 `artifact_path`、`summary`、`relevance` 和 `must_keep`。
  - compact 失败时保留原始上下文或降级为不压缩。
  - 不删除可回读 artifact，除非用户明确要求清理。

- **Memory Extractor 职责**:
  - 在 turn 结束后从 user input、final answer、recent messages、tool result summaries 和 memory index 中提取 memory candidates。
  - 输出结构化候选，不直接绕过写入规则。
  - 只提取稳定偏好、明确约束、项目事实、长期反馈和可复用引用。
  - 不提取临时闲聊、敏感信息、模型猜测或已经过期的任务状态作为长期 memory。

- **LLM Client 职责**:
  - 作为 DeepSeek API 的薄适配层。
  - 接收 messages、tools 和 system_prompt。
  - 发起 DeepSeek chat 请求。
  - 对 DeepSeek 临时故障执行有上限的有限重试，不得无限阻塞 CLI。
  - 可重试错误包括网络连接类错误、timeout、SSL EOF，以及 HTTP 429、500、503。
  - 不可重试错误包括 HTTP 400、401、402、422，以及响应解析错误和 tool call 参数解析错误。
  - 重试耗尽后抛出明确错误，错误信息不得包含 API key、完整 headers、完整 payload 或完整 system prompt。
  - 将 DeepSeek 响应转换为统一的 LLMResponse。
  - 不包含 Agent 业务判断逻辑。

- **CLI Runtime 职责**:
  - 作为 `python -m personal_knowledge_agent` 和安装后 `pka` 命令的启动入口。
  - 启动时加载 `.env` 和环境变量配置。
  - 初始化 SQLite Store、KnowledgeTools、ToolDispatcher、DeepSeekClient 和 AgentLoop。
  - 进入持续交互循环，读取用户输入并打印 Agent 回复。
  - 使用 `prompt-toolkit` 提供交互式输入，不使用裸 `input()` 作为主要输入方式。
  - 输入层只负责采集用户输入，不做知识保存、检索或业务判断。
  - 支持 `/exit` 和 `/quit` 退出。
  - 实时接收 Agent Loop 事件。
  - 将事件交给 CLI Renderer 渲染。
  - 将事件投递给 Async JSONL Logger。
  - CLI 展示长文本时必须做确定性截断。
  - 单轮 AgentLoop 执行失败时，应展示本轮失败提示并继续等待下一轮输入。
  - 单轮模型或工具运行失败不得导致 CLI 进程退出；启动阶段不可恢复错误、用户输入 `/exit` 或 `/quit` 除外。
  - 不直接操作 SQLite。
  - 不绕过 AgentLoop 调用工具。

- **Web Runtime 职责**:
  - 作为 `pka web` 和 `python -m personal_knowledge_agent.web` 的本地浏览器入口。
  - 启动时加载 `.env` 和环境变量配置。
  - 通过 `agent_factory.py` 创建 AgentLoop 及其依赖。
  - 启动绑定在 `127.0.0.1` 的本地 HTTP 服务。
  - 提供静态 HTML/CSS/JS 页面。
  - 接收用户聊天输入并调用 AgentLoop。
  - 提供最近卡片、搜索卡片和卡片详情 API。
  - Web 输入层只负责采集用户输入，不判断知识录入或问答意图。
  - Web API 不直接操作 SQLite，不绕过 Tools 或 Store 边界。
  - Web 第一版只覆盖 Chat + Cards，不提供编辑、删除、合并或复杂知识管理能力。
  - Web Runtime 的单轮 AgentLoop 执行失败时，应返回结构化错误，不得声称保存、查询或回答成功。

- **CLI Renderer 职责**:
  - 根据事件类型渲染用户可见输出。
  - LLM 阶段展示阶段名、开始、结束和失败状态。
  - Tool call 展示工具名和可展示输入字段。
  - Tool result 展示工具名、状态、耗时和可展示输出字段。
  - Final answer 展示最终回答和来源。
  - 不展示原始 LLM messages、system prompt、API key、secret、完整内部 payload 或模型完整思考链。

- **Tools 职责**:
  - 作为 Agent 可执行动作的唯一入口。
  - 校验工具输入。
  - 调用 SQLite Store 完成保存、检索、读取和列出最近卡片。
  - 调用 Agent memory store 完成 memory index 和 memory 全文读取。
  - 不负责上下文压缩；当前上下文压缩由 AgentLoop 内部的 Context Compactor 自动完成。
  - 将成功、失败和未找到结果统一转换为结构化 tool result。

- **Services / Repositories 职责**:
  - 第一版 Q&A 知识库不单独拆分 Service / Repository。
  - `SQLiteStore` 负责数据库初始化、保存、读取、LIKE 检索和最近列表。
  - `SQLiteStore` 不调用 LLM，不组织最终自然语言回答。
  - `MemoryStore` 负责 `.memory/*.md` 的读写、frontmatter 解析和内容校验。
  - `MemoryIndex` 负责 `.memory/MEMORY.md` 的读取、校验和更新。
  - `SessionTranscript` 负责 `.sessions/<session_id>/transcript.jsonl` 的追加和读取。
  - `SessionMetadata` 负责 `.sessions/<session_id>/metadata.json` 的读写。
  - `SessionRestore` 负责从 transcript / summary 恢复 runtime `messages[]`。
  - `SessionSummarizer` 负责长 transcript 的 summary 生成和失败降级。

- **Storage / External API 职责**:
  - SQLite `qa_cards` 是第一版 Q&A 知识库的唯一长期记忆来源。
  - `.memory/*.md` 是 Agent 长期工作记忆来源。
  - `.memory/MEMORY.md` 是 Agent memory index，只保存 name、type、description 和 path。
  - `.sessions/<session_id>/transcript.jsonl` 是 runtime `messages[]` 的可恢复持久化记录。
  - `.sessions/<session_id>/summary.md` 是长 transcript compact 后的恢复摘要，不是长期事实来源。
  - `.sessions/<session_id>/metadata.json` 是 session 管理索引，不参与 Q&A 回答。
  - `.sessions/<session_id>/artifacts/` 保存 compact 后可回读的大输出，不是长期事实来源。
  - DeepSeek 是第一版 LLM 服务。
  - 第一版不引入向量库、外部知识库或后台任务。

- **Logging 职责**:
  - Async JSONL Logger 是 Agent run 过程的唯一结构化开发日志。
  - 使用本地 JSONL 日志记录开发排查事件，默认写入 `.logs/agent.log`。
  - 与 CLI Runtime 共用 Agent Loop 的结构化事件流。
  - 日志完整记录用户原始输入，不截断。
  - 工具 input/output 默认只记录工具契约中声明为可展示的字段。
  - 日志中的工具可展示长文本不截断；CLI 展示时截断。
  - 使用后台线程和 bounded queue 异步写入日志，Agent Loop 主流程只负责投递日志事件。
  - 队列满时不得阻塞 Agent Loop，应丢弃日志事件并向 stderr 最多提示一次。
  - 正常 `/exit` 或 `/quit` 时最多等待 2 秒 flush 日志队列。
  - 日志写入失败不得影响 Agent 回答，应向 stderr 最多提示一次并停止继续写日志。
  - Python 标准库 `logging` 仅保留底层库级异常和不可恢复错误，不承担 Agent loop trace 职责。
  - 不记录 API key、完整 headers、完整 system prompt、完整 LLM messages、secret 或未声明为可展示的内部 payload。

- **Web UI 职责**:
  - 展示聊天消息、基础运行状态、Agent 最终回答和错误信息。
  - 展示最近 Q&A 卡片、搜索结果和卡片详情。
  - 展示的 Q&A 来源信息必须来自后端 API 返回的结构化字段。
  - 不在浏览器端保存长期记忆，不直接读写 SQLite，不自行判断证据是否足够。

- **腐败代码清理原则**:
  - 实现结构化事件流后，应删除与事件流重复的旧 logging 埋点。
  - `agent_loop.py` 不再使用 `logger.info` 记录 start、tool_calls.detected、final_answer 等 Agent run trace。
  - `tool_dispatcher.py` 不再使用 `logger.info` 记录 dispatch start/success 这类可由 tool_call_started/tool_call_finished 表达的事件。
  - `tools.py` 不再使用 `logger.info` 记录 save/search/read/list success 这类可由 tool result 表达的事件。
  - `sqlite_store.py` 不再使用 `logger.info` 记录 schema/search/recent/insert success 这类默认成功路径。
  - 可以保留 `logger.exception` 或 `logger.error` 作为未预期底层异常兜底，但不得替代 Async JSONL Logger。

- **禁止绕过的边界**:
  1. Agent Loop 不得直接操作 SQLite。
  2. LLM 输出不得被视为已持久化事实。
  3. Tools 不得绕过 SQLite Store 直接拼接外部副作用。
  4. SQLite Store 不得调用 LLM。
  5. Agent Loop 不得直接操作 SQLite。
  6. `.memory/*.md` 不得作为 Q&A 知识库来源。
  7. `.sessions/<session_id>/summary.md` 不得作为长期事实来源。
  8. 未在本文档声明的核心依赖不得擅自引入。
  9. Web UI 不得直接操作 SQLite 或把浏览器本地状态当作长期记忆。

- **核心文件 / 目录**:

| 路径 | 职责 |
|---|---|
| `pyproject.toml` | 声明项目依赖和 `pka` CLI script |
| `src/personal_knowledge_agent/agent_loop/` | Agent 主循环和 turn 编排 |
| `src/personal_knowledge_agent/agent_loop/loop.py` | Agent Loop 核心调用链 |
| `src/personal_knowledge_agent/agent_loop/call_llm.py` | 单次 LLM 调用和对应事件 |
| `src/personal_knowledge_agent/agent_loop/run_tool_call.py` | 单次 tool call、耗时、compact 和对应事件 |
| `src/personal_knowledge_agent/agent_loop/finish_answer.py` | 最终回答收尾和最大轮次停止 |
| `src/personal_knowledge_agent/agent_loop/format_llm_messages.py` | assistant/tool result 的 LLM API message 格式化 |
| `src/personal_knowledge_agent/agent_loop/load_turn_context.py` | turn-start memory index 和相关 memory 加载 |
| `src/personal_knowledge_agent/agent_loop/finalize_turn_memory.py` | turn-end memory candidate 提取 |
| `src/personal_knowledge_agent/agent_loop/emit_agent_events.py` | Agent run 事件发射适配 |
| `src/personal_knowledge_agent/agent_loop/record_runtime_messages.py` | runtime messages、transcript 和 metadata count 记录 |
| `src/personal_knowledge_agent/events.py` | Agent run 结构化事件契约 |
| `src/personal_knowledge_agent/agent_factory.py` | 创建 AgentLoop 及其依赖，供 CLI Runtime 和 Web Runtime 复用 |
| `src/personal_knowledge_agent/cli_renderer.py` | CLI 实时事件渲染 |
| `src/personal_knowledge_agent/jsonl_logger.py` | 异步 JSONL 开发日志 |
| `src/personal_knowledge_agent/prompt_builder.py` | 构建运行时 system prompt |
| `src/personal_knowledge_agent/llm_client.py` | DeepSeek 薄客户端 |
| `src/personal_knowledge_agent/config.py` | 读取 `.env` 和环境变量，返回运行配置 |
| `src/personal_knowledge_agent/__main__.py` | CLI 持续交互入口和 `pka web` 子命令分发，供 `python -m personal_knowledge_agent` 和 `pka` 复用 |
| `src/personal_knowledge_agent/web/` | 本地 Web Runtime、Web API 和静态 HTML 页面 |
| `src/personal_knowledge_agent/web/app.py` | 创建本地 Web app，定义聊天和卡片浏览 API |
| `src/personal_knowledge_agent/web/__main__.py` | Web Runtime 启动入口，供 `python -m personal_knowledge_agent.web` 复用 |
| `src/personal_knowledge_agent/web/static/` | Chat + Cards 的原生 HTML/CSS/JS 页面 |
| `src/personal_knowledge_agent/tools/` | LLM 可调用工具和工具分发 |
| `src/personal_knowledge_agent/tools/knowledge_tools.py` | 知识库工具实现 |
| `src/personal_knowledge_agent/tools/dispatch_tool_call.py` | 工具分发和错误包装 |
| `src/personal_knowledge_agent/agent_memory/` | `.memory/` 长期 Agent 工作记忆 |
| `src/personal_knowledge_agent/agent_memory/document_store.py` | 读写 `.memory/*.md` 长期 Agent memory |
| `src/personal_knowledge_agent/agent_memory/index_store.py` | 读写 `.memory/MEMORY.md` 记忆索引 |
| `src/personal_knowledge_agent/agent_memory/extract_memory_candidates.py` | 生成 memory candidates |
| `src/personal_knowledge_agent/session_memory/` | `.sessions/` 会话恢复、摘要、transcript 和 artifact |
| `src/personal_knowledge_agent/session_memory/transcript.py` | 追加和读取 `.sessions/<session_id>/transcript.jsonl` |
| `src/personal_knowledge_agent/session_memory/metadata.py` | 读写 `.sessions/<session_id>/metadata.json` |
| `src/personal_knowledge_agent/session_memory/restore_session.py` | 从 transcript 或 summary 恢复 runtime `messages[]` |
| `src/personal_knowledge_agent/session_memory/summarize_session.py` | 长 transcript 自动总结和失败降级 |
| `src/personal_knowledge_agent/session_memory/compact_tool_result.py` | 大工具结果落盘和 compact record 生成 |
| `src/personal_knowledge_agent/schemas.py` | 轻量数据契约 |
| `src/personal_knowledge_agent/qa_store/` | Q&A 知识库持久化 |
| `src/personal_knowledge_agent/qa_store/sqlite_store.py` | SQLite 初始化、写入、读取、检索 |
| `.knowledge/knowledge.db` | 本地知识库数据库文件 |
| `.memory/MEMORY.md` | 用户可见 Agent memory 索引 |
| `.memory/*.md` | 用户可见 Agent 长期记忆文档 |
| `.sessions/<session_id>/transcript.jsonl` | runtime `messages[]` 的可恢复持久化记录 |
| `.sessions/<session_id>/summary.md` | 长 transcript compact 后的恢复摘要 |
| `.sessions/<session_id>/metadata.json` | session 管理索引 |
| `.sessions/<session_id>/artifacts/` | compact 后可回读的大输出 artifact |

---

## 3. 可调用工具与工具契约

### 3.1 工具列表

| 工具名 | 工具职责 | 调用时机 | 是否有副作用 | 是否需要确认 |
|---|---|---|---|---|
| `save_qa_card` | 保存 Q&A 卡片 | 用户明确提供 Q&A 并要求记录时 | 是 | 否 |
| `search_qa_cards` | 检索相关 Q&A 卡片 | 用户提出问题时 | 否 | 否 |
| `read_qa_card` | 读取完整 Q&A 卡片 | 需要核对完整来源时 | 否 | 否 |
| `list_recent_cards` | 列出最近保存卡片 | 用户要求查看最近记录或保存后确认时 | 否 | 否 |
| `list_memory_index` | 列出 Agent memory 索引 | turn-start 或模型需要了解可用记忆时 | 否 | 否 |
| `read_memory` | 读取指定 Agent memory 全文 | 当前请求需要某条长期记忆时 | 否 | 否 |

### 3.2 工具契约

#### `save_qa_card`

- **职责**:  
  保存一条用户提供的 Q&A 卡片。模型负责生成 summary 和 keywords，工具负责写入 SQLite。

- **输入**:

```json
{
  "question": "原始问题，非空字符串",
  "answer": "原始答案，非空字符串",
  "summary": "简明摘要，非空字符串",
  "keywords": ["关键词列表，至少 1 个"]
}
```

- **输出**:

```json
{
  "ok": true,
  "card_id": "本地唯一卡片 ID",
  "source_type": "manual_qa",
  "created_at": "ISO 8601 时间"
}
```

- **可展示输入字段**:
  - `question`
  - `answer`
  - `summary`
  - `keywords`

- **可展示输出字段**:
  - `ok`
  - `card_id`
  - `source_type`
  - `created_at`
  - `error_code`
  - `message`

- **副作用**:  
  写入 SQLite `qa_cards` 表。

- **失败处理**:  
  输入缺少必填字段、字段为空或数据库写入失败时，返回 `ok: false`、`error_code` 和 `message`。工具失败时 Agent 不得声称保存成功。

#### `search_qa_cards`

- **职责**:  
  根据用户问题检索本地 Q&A 卡片，返回候选结果供 Agent 判断依据是否足够。

- **输入**:

```json
{
  "query": "用户问题或检索词，非空字符串",
  "limit": 5
}
```

- **输出**:

```json
{
  "ok": true,
  "cards": [
    {
      "card_id": "卡片 ID",
      "question": "原始问题",
      "summary": "摘要",
      "answer_snippet": "答案片段",
      "score": 3,
      "source_type": "manual_qa",
      "created_at": "ISO 8601 时间"
    }
  ]
}
```

- **可展示输入字段**:
  - `query`
  - `limit`

- **可展示输出字段**:
  - `ok`
  - `cards.card_id`
  - `cards.question`
  - `cards.summary`
  - `cards.answer_snippet`
  - `cards.score`
  - `cards.source_type`
  - `cards.created_at`
  - `error_code`
  - `message`

- **副作用**:  
  无。

- **失败处理**:  
  输入为空时返回结构化错误。没有检索结果时返回 `ok: true` 和空 `cards`，不得生成虚假结果。

#### `read_qa_card`

- **职责**:  
  根据 card_id 读取完整 Q&A 卡片，用于核对来源和组织回答。

- **输入**:

```json
{
  "card_id": "卡片 ID，非空字符串"
}
```

- **输出**:

```json
{
  "ok": true,
  "card": {
    "card_id": "卡片 ID",
    "question": "原始问题",
    "answer": "原始答案",
    "summary": "摘要",
    "keywords": ["关键词"],
    "source_type": "manual_qa",
    "created_at": "ISO 8601 时间",
    "updated_at": "ISO 8601 时间"
  }
}
```

- **可展示输入字段**:
  - `card_id`

- **可展示输出字段**:
  - `ok`
  - `card.card_id`
  - `card.question`
  - `card.answer`
  - `card.summary`
  - `card.keywords`
  - `card.source_type`
  - `card.created_at`
  - `card.updated_at`
  - `error_code`
  - `message`

- **副作用**:  
  无。

- **失败处理**:  
  card_id 为空时返回结构化错误。找不到卡片时返回 `ok: false`、`error_code: "not_found"` 和 `message`，Agent 不得引用该卡片作为来源。

#### `list_recent_cards`

- **职责**:  
  列出最近保存的 Q&A 卡片，方便用户确认本地知识库内容。

- **输入**:

```json
{
  "limit": 10
}
```

- **输出**:

```json
{
  "ok": true,
  "cards": [
    {
      "card_id": "卡片 ID",
      "question": "原始问题",
      "summary": "摘要",
      "keywords": ["关键词"],
      "source_type": "manual_qa",
      "created_at": "ISO 8601 时间"
    }
  ]
}
```

- **可展示输入字段**:
  - `limit`

- **可展示输出字段**:
  - `ok`
  - `cards.card_id`
  - `cards.question`
  - `cards.summary`
  - `cards.keywords`
  - `cards.source_type`
  - `cards.created_at`
  - `error_code`
  - `message`

- **副作用**:  
  无。

- **失败处理**:  
  limit 非法时使用安全默认值。数据库读取失败时返回 `ok: false`、`error_code` 和 `message`。

#### `list_memory_index`

- **职责**:
  读取 `.memory/MEMORY.md`，返回 Agent memory 索引。索引只用于判断哪些长期 Agent memory 可能相关，不默认加载全文。

- **输入**:

```json
{
  "limit": 50
}
```

- **输出**:

```json
{
  "ok": true,
  "entries": [
    {
      "name": "memory 名称",
      "type": "user / feedback / project / reference",
      "description": "简短描述",
      "path": ".memory/project-example.md"
    }
  ]
}
```

- **可展示输入字段**:
  - `limit`

- **可展示输出字段**:
  - `ok`
  - `entries.name`
  - `entries.type`
  - `entries.description`
  - `entries.path`
  - `error_code`
  - `message`

- **副作用**:
  无。

- **失败处理**:
  `.memory/MEMORY.md` 不存在时返回 `ok: true` 和空 `entries`。索引格式非法时返回 `ok: false`、`error_code: "invalid_memory_index"` 和 `message`。

#### `read_memory`

- **职责**:
  读取指定 `.memory/*.md` 的完整 Agent memory 内容，用于指导当前 turn 的行为或项目理解。该工具不得读取 `.knowledge/knowledge.db`，也不得把 memory 内容包装成 Q&A 来源。

- **输入**:

```json
{
  "name": "memory 名称，非空字符串"
}
```

- **输出**:

```json
{
  "ok": true,
  "memory": {
    "name": "memory 名称",
    "type": "user / feedback / project / reference",
    "description": "简短描述",
    "path": ".memory/project-example.md",
    "updated_at": "ISO 8601 日期或时间",
    "source_type": "user_decision / project_doc / agent_extracted / reference",
    "content": "memory 正文"
  }
}
```

- **可展示输入字段**:
  - `name`

- **可展示输出字段**:
  - `ok`
  - `memory.name`
  - `memory.type`
  - `memory.description`
  - `memory.path`
  - `memory.updated_at`
  - `memory.source_type`
  - `memory.content`
  - `error_code`
  - `message`

- **副作用**:
  无。

- **失败处理**:
  name 为空时返回结构化错误。找不到 memory 时返回 `ok: false`、`error_code: "not_found"`。frontmatter 缺少必填字段或 type 非法时返回 `ok: false`、`error_code: "invalid_memory"`。

### 3.3 当前非工具机制

- **上下文压缩**:
  当前上下文压缩不是 LLM 可调用工具。AgentLoop 在 tool result 超过阈值时，通过 `ContextCompactor.compact_tool_result()` 自动将原始 tool result 写入 `.sessions/<session_id>/artifacts/`，并通过 compact record 回填 tool result message 和 `context_compacted` 事件。

- **Memory candidate**:
  当前 memory candidate 不是 LLM 可调用工具，也没有写入 `.memory/*.md`、更新 `.memory/MEMORY.md` 或 pending confirmation 队列。AgentLoop 只在 turn-end 通过 `MemoryExtractor` 生成候选，并发出 `memory_candidates_generated` 事件；候选不等于已写入长期 memory。

---

## 4. 上下文来源与记忆边界

- **运行时上下文来源**:
  1. 用户当前输入。
  2. runtime `messages[]` 中的历史 user / assistant / tool messages。
  3. Prompt Builder 生成的 system prompt。
  4. `.memory/MEMORY.md` memory index。
  5. 按需读取的少量 `.memory/*.md`。
  6. 从 `.sessions/<session_id>/transcript.jsonl` 恢复的 messages。
  7. 从 `.sessions/<session_id>/summary.md` 构造的 summary message。
  8. compact record，包括 `artifact_path`、`summary`、`relevance` 和 `must_keep`。
  9. `.env` 和环境变量提供的运行配置。

- **长期记忆来源**:
  1. SQLite `qa_cards` 表，作为 Q&A 知识库来源。
  2. `.memory/*.md`，作为 Agent 长期工作记忆来源。

- **不得作为长期记忆的内容**:
  1. 未通过 `save_qa_card` 写入 SQLite 的 LLM 临时输出。
  2. 未落库的对话上下文。
  3. 日志内容。
  4. DeepSeek 响应中未保存到 SQLite 的内容。
  5. `.env` 中的运行配置。
  6. Agent run 事件和 JSONL 日志。
  7. `.sessions/<session_id>/summary.md` 中的会话 compact summary。
  8. `.sessions/<session_id>/transcript.jsonl` 中的历史 messages。
  9. `.sessions/<session_id>/artifacts/` 中未整理为长期 memory 的原始大输出。
  10. compact record 本身。

- **运行 trace 边界**:
  1. 第一版不把运行 trace 写入 SQLite。
  2. SQLite 只保存 Q&A 知识卡片。
  3. `.logs/agent.log` 只用于本地开发排查，不是长期知识来源。
  4. compact artifact 只用于当前任务可回读，不是 Q&A 来源。

- **Agent memory 边界**:
  1. `.memory/MEMORY.md` 只作为 memory index，记录 memory name、type、description 和 path。
  2. `.memory/*.md` 保存用户偏好、长期反馈、项目事实和引用入口。
  3. `.memory/*.md` 可以影响 Agent 如何协作和如何选择上下文，但不得作为 Q&A 知识卡片来源。
  4. 每轮不得默认注入所有 `.memory/*.md` 全文，只能按需读取少量相关 memory。
  5. Agent memory 写入必须保留来源类型和可追溯说明。

- **Session / transcript 边界**:
  1. runtime `messages[]` 是当前聊天上下文本体。
  2. `.sessions/<session_id>/transcript.jsonl` 是 runtime `messages[]` 的可恢复持久化记录。
  3. `.sessions/<session_id>/summary.md` 是长 transcript compact 后的恢复摘要。
  4. `.sessions/<session_id>/metadata.json` 是 session 管理索引。
  5. `.sessions/<session_id>/summary.md` 和 transcript 不得作为长期事实来源。
  6. `.sessions/<session_id>/summary.md` 和 transcript 不得作为 Q&A 回答来源。
  7. `.logs/agent.log` 只做运行 trace，不参与 messages 恢复。

- **配置边界**:
  1. `.env` 只保存运行配置，不是长期知识来源。
  2. `DEEPSEEK_API_KEY` 不得进入 messages、tool result、SQLite 或日志。
  3. `.env`、`.knowledge/`、`.sessions/` 和本地 `.memory/` 内容应通过 `.git/info/exclude` 在本地忽略，不要求提交仓库级 `.gitignore`。

- **上下文裁剪规则**:
  1. 第一版优先保留用户当前输入、最近 messages、最近一次 LLM tool call 和 tool result。
  2. 回答必须保留用于引用来源的 card_id、question、source_type 和 created_at。
  3. 不把历史对话当作可靠长期记忆。
  4. turn-start 指收到用户输入后、第一次调用主 LLM 前的上下文准备阶段。
  5. turn-start 从 `.sessions/default/transcript.jsonl` 恢复 runtime `messages[]`，短会话原样恢复，长会话用 summary + recent messages 恢复。
  6. 当单个 tool result 或本轮累计工具结果超过阈值时，应优先将原始内容写入 `.sessions/<session_id>/artifacts/`，并用 compact record 替换上下文中的大输出。
  7. compact record 必须保留 artifact_path、summary、relevance 和 must_keep。
  8. compact 不得删除回答所需证据，不得替代长期 memory 写入。
  9. summarizer 最多重试 3 次；失败后使用 first N messages + recovery notice + recent N messages 恢复，不阻断 CLI。

---

## 5. 核心业务流

### 5.1 录入 Q&A

1. 用户提供明确的 Q&A，并表达记录意图。
2. Agent 判断这是知识录入。
3. Agent 保留原始 question 和 answer。
4. Agent 生成 summary 和 keywords。
5. Agent 调用 `save_qa_card`。
6. 工具写入 SQLite。
7. Agent 向用户返回保存结果、card_id 和来源信息。

- **成功条件**:  
  SQLite 中新增一条 Q&A 卡片，工具返回 `ok: true` 和 `card_id`。

- **失败条件**:  
  用户没有提供完整 Q&A、工具输入非法或数据库写入失败。

- **用户可见反馈**:  
  成功时说明已保存并展示 card_id；失败时说明没有保存成功和失败原因。

### 5.2 回答问题

1. 用户提出问题。
2. Agent 调用 `search_qa_cards` 检索 SQLite。
3. Agent 判断候选卡片是否相关且足够。
4. 必要时调用 `read_qa_card` 读取完整卡片。
5. Agent 基于检索结果回答。
6. Agent 在回答中附带 card_id、原始问题、source_type 和 created_at。

- **成功条件**:  
  回答内容可追溯到至少一条本地知识卡片。

- **失败条件**:  
  检索为空、候选结果不相关或证据不足。

- **用户可见反馈**:  
  有依据时回答并列出来源；依据不足时明确说明无法从本地知识库回答。

### 5.3 列出最近卡片

1. 用户要求查看最近记录，或保存后需要确认。
2. Agent 调用 `list_recent_cards`。
3. 工具按创建时间倒序返回卡片摘要。
4. Agent 展示最近卡片的 card_id、原始问题、summary、keywords 和 created_at。

- **成功条件**:  
  返回最近卡片列表，可以为空。

- **失败条件**:  
  数据库读取失败或工具输入非法。

- **用户可见反馈**:  
  有记录时列出卡片；无记录时说明本地知识库暂无 Q&A 卡片。

### 5.4 CLI 持续交互

1. 用户运行安装后的 `pka` 命令，或使用 `python -m personal_knowledge_agent` 模块入口。
2. CLI Runtime 调用配置加载器读取 `.env` 和环境变量。
3. CLI Runtime 初始化 SQLite Store、KnowledgeTools、ToolDispatcher、DeepSeekClient 和 AgentLoop。
4. CLI Runtime 进入循环并等待用户输入。
5. 用户输入 Q&A 录入请求或问题。
6. CLI Runtime 将输入交给 AgentLoop。
7. AgentLoop 按 5.1 或 5.2 流程调用 LLM 和工具。
8. CLI Runtime 打印 Agent 最终回答。
9. 用户输入 `/exit` 或 `/quit` 时退出。

- **成功条件**:  
  用户无需手写初始化代码，即可在 CLI 中连续录入知识和提问。

- **失败条件**:  
  `.env` 或环境变量缺少 `DEEPSEEK_API_KEY`，或 DeepSeek / SQLite 初始化失败。运行中 LLM 调用失败且重试耗尽时，只应结束本轮，不应退出 CLI 进程。

- **用户可见反馈**:  
  启动失败时输出明确错误；运行中工具或模型失败时展示本轮失败说明。运行中 LLM 调用失败且重试耗尽时，不得声称保存、查询或回答成功，应提示模型服务暂时不可用并继续等待下一轮输入。

推荐本地使用方式：

```bash
uv venv
uv pip install -e .
. .venv/bin/activate
pka
```

`pka` 启动后进入持续交互，用户可以连续录入 Q&A 或提问。

### 5.5 Web 持续交互

1. 用户运行 `pka web`，或使用 `python -m personal_knowledge_agent.web` 模块入口。
2. Web Runtime 调用配置加载器读取 `.env` 和环境变量。
3. Web Runtime 通过 `agent_factory.py` 创建 AgentLoop 及其依赖。
4. Web Runtime 启动绑定在 `127.0.0.1` 的本地 HTTP 服务。
5. Web Runtime 提供静态 HTML 页面，并可自动打开浏览器访问本地服务。
6. 用户在 HTML 页面输入 Q&A 录入请求或问题。
7. `POST /api/chat` 将输入交给 AgentLoop。
8. AgentLoop 按 5.1 或 5.2 流程调用 LLM 和工具。
9. Web API 返回结构化结果，HTML 展示 Agent 最终回答和基础状态。

- **成功条件**:  
  用户无需使用 CLI，即可在本地浏览器中连续录入知识和提问。

- **失败条件**:  
  `.env` 或环境变量缺少 `DEEPSEEK_API_KEY`，DeepSeek / SQLite 初始化失败，本地端口不可用，静态页面加载失败，或单轮 AgentLoop 执行失败。

- **用户可见反馈**:  
  启动失败时输出明确错误；运行中模型或工具失败时，Web API 返回结构化错误，HTML 展示本轮失败说明。不得声称保存、查询或回答成功。

### 5.6 Web 知识卡片浏览

1. HTML 页面请求最近卡片、搜索卡片或卡片详情。
2. Web API 调用后端封装的卡片读取能力。
3. 最近卡片 API 返回 card_id、原始问题、summary、keywords、source_type 和 created_at。
4. 搜索卡片 API 返回 card_id、原始问题、summary、answer_snippet、score、source_type 和 created_at。
5. 卡片详情 API 返回 card_id、原始问题、原始答案、summary、keywords、source_type、created_at 和 updated_at。
6. HTML 页面展示结构化卡片信息。

- **成功条件**:  
  用户能在 Web UI 中查看最近 Q&A 卡片、搜索 Q&A 卡片并打开卡片详情。

- **失败条件**:  
  数据库读取失败、查询参数非法、card_id 不存在或 Web API 返回结构化错误。

- **用户可见反馈**:  
  有记录时展示卡片；无记录时展示空状态；读取失败时展示错误原因。Web UI 不得生成虚假卡片或虚假来源。

### 5.7 CLI 实时运行过程展示

1. CLI Runtime 收到用户输入后生成本轮 `run_id`。
2. Agent Loop 在收到输入、调用 LLM、收到 LLM 响应、调用工具、收到工具结果、判断证据和生成最终回答时产生结构化事件。
3. CLI Renderer 在主线程实时渲染事件。
4. Async JSONL Logger 在后台线程异步写入本地 `.logs/agent.log`。
5. 最终回答仍必须符合来源要求；依据不足时仍必须明确拒答。

- **成功条件**:  
  用户能在 CLI 中实时看到 LLM 阶段、tool call、tool result、证据判断和最终回答；本地 JSONL 日志能记录同一批事件。

- **失败条件**:  
  CLI Renderer 渲染失败、日志队列满、日志写入失败或日志 flush 超时。

- **用户可见反馈**:  
  CLI Renderer 或 Logger 失败时向 stderr 输出简短提示，但不得影响 Agent 工具执行和最终回答。

### 5.8 Turn-start 上下文准备

1. CLI Runtime 选择或创建默认 session：`.sessions/default/`。
2. Session Restore 读取 `metadata.json` 和 `transcript.jsonl`。
3. 如果 transcript 未超过预算，原样恢复 runtime `messages[]`。
4. 如果 transcript 超过预算，优先使用 summarizer 生成或更新 `summary.md`，并用 summary message + recent messages 恢复。
5. 如果 summarizer 在最多 3 次重试后仍失败，使用 first N messages + recovery notice + recent N messages 降级恢复。
6. Memory Manager 读取 `.memory/MEMORY.md`，得到 memory index。
7. Memory Manager 根据用户当前输入、recent messages 和 memory index 选择最多 N 条相关 memory。
8. Prompt Builder 将 base system prompt、memory index 摘要和 selected memories 组合成本轮 system prompt。
9. Agent Loop 接收 runtime `messages[]` 并继续执行 LLM + tool loop。

- **成功条件**:
  本轮上下文包含从 transcript / summary 恢复的 messages、用户当前输入、基础规则、可用 memory index 和相关 memory，且未默认注入全部 memory 全文。

- **失败条件**:
  metadata / transcript 读取失败、summary 生成失败、memory index 格式非法或 memory 文件读取失败。

- **用户可见反馈**:
  session 恢复失败时使用空 messages 或 first+recent 降级恢复，并向 stderr 或 CLI 事件提示一次；不得影响 Q&A 主流程的工具检索和回答。

### 5.9 上下文压缩

1. AgentLoop 执行工具调用并获得 tool result。
2. ToolCallStep 将 tool result 序列化后交给 ContextCompactor 检查长度。
3. 当 tool result 超过阈值时，ContextCompactor 将原始结果写入 `.sessions/<session_id>/artifacts/`。
4. ContextCompactor 返回 compact record，包含 artifact_path、summary、relevance 和 must_keep。
5. AgentLoop 将 compact record 写入 tool result message，并发出 `context_compacted` 事件。
6. compact 只缩减当前上下文窗口，不作为 Q&A 来源或长期 memory。

- **成功条件**:
  大输出可通过 artifact_path 回读，当前上下文保留 compact record。

- **失败条件**:
  artifact 写入失败或 compact record 生成失败。

- **用户可见反馈**:
  compact 成功时可在事件中展示 artifact_path 和 summary。compact 失败时降级为不压缩或保留原始 tool result，不得丢失回答所需证据。

### 5.10 Turn-end memory candidate 提取

1. Agent Loop 完成本轮最终回答。
2. MemoryExtractor 收集 user input、final answer、recent messages 和 memory index。
3. Memory Extractor 提取结构化 memory candidates。
4. AgentLoop 发出 `memory_candidates_generated` 事件。
5. 当前实现不自动写入 `.memory/*.md`，不更新 `.memory/MEMORY.md`，也不维护 pending confirmation 队列。

- **成功条件**:
  稳定偏好、明确项目决策等内容被整理为候选并通过事件暴露；候选不表示已经写入长期 memory。

- **失败条件**:
  MemoryExtractor 执行失败或候选生成异常。

- **用户可见反馈**:
  当前可通过事件展示候选；不得声称候选已经写入长期 memory。

---

## 6. 数据模型

### 6.1 `qa_cards`

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `id` | `TEXT` | 是 | 本地唯一卡片 ID |
| `question` | `TEXT` | 是 | 用户提供的原始问题 |
| `answer` | `TEXT` | 是 | 用户提供的原始答案 |
| `summary` | `TEXT` | 是 | 模型整理出的简明摘要 |
| `keywords` | `TEXT` | 是 | JSON 字符串，保存关键词数组 |
| `source_type` | `TEXT` | 是 | 第一版固定为 `manual_qa` |
| `created_at` | `TEXT` | 是 | 系统生成的 ISO 8601 创建时间 |
| `updated_at` | `TEXT` | 是 | 系统生成的 ISO 8601 更新时间 |

建表 SQL：

```sql
CREATE TABLE IF NOT EXISTS qa_cards (
  id TEXT PRIMARY KEY,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  summary TEXT NOT NULL,
  keywords TEXT NOT NULL,
  source_type TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### 6.2 数据约束

1. `id` 必须由工具或 Store 生成，模型不得自称某个未落库 ID 已存在。
2. `question`、`answer`、`summary` 不得为空。
3. `keywords` 在工具输入中是字符串数组，入库时序列化为 JSON 字符串。
4. `source_type` 第一版固定为 `manual_qa`。
5. `created_at` 和 `updated_at` 必须由系统生成。
6. DeepSeek API key 不得写入数据库、代码、文档或日志。

### 6.3 `.memory/MEMORY.md`

`MEMORY.md` 是 Agent memory index，只保存索引信息，不保存完整 memory 正文。它可以在 turn-start 阶段优先读取，用于判断哪些 memory 可能相关。

格式：

```markdown
# Memory Index

| name | type | description | path |
|---|---|---|---|
| separate-qa-and-agent-memory | project | Q&A knowledge base and Agent memory must remain separate | .memory/project-separate-qa-and-agent-memory.md |
```

字段约束：

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `name` | `TEXT` | 是 | memory 稳定名称 |
| `type` | `TEXT` | 是 | `user`、`feedback`、`project` 或 `reference` |
| `description` | `TEXT` | 是 | 用于相关性选择的短描述 |
| `path` | `TEXT` | 是 | 指向 `.memory/*.md` 的相对路径 |

### 6.4 `.memory/*.md`

`.memory/*.md` 是用户可见的 Agent 长期工作记忆文档。每个文件必须包含 frontmatter 和正文。

格式：

```markdown
---
name: "separate-qa-and-agent-memory"
type: "project"
description: "Q&A knowledge base and Agent memory must remain separate"
updated_at: "2026-05-31"
source_type: "user_decision"
source_ref: "conversation:2026-05-31"
---

本项目 memory 设计中，Q&A 知识库用于回答用户知识问题，Agent memory 用于指导 Agent 行为，两者必须分开。
```

字段约束：

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `name` | `TEXT` | 是 | memory 稳定名称，必须与索引一致 |
| `type` | `TEXT` | 是 | `user`、`feedback`、`project` 或 `reference` |
| `description` | `TEXT` | 是 | 短描述，必须可用于相关性判断 |
| `updated_at` | `TEXT` | 是 | ISO 8601 日期或时间 |
| `source_type` | `TEXT` | 是 | `user_explicit`、`user_decision`、`project_doc`、`agent_extracted` 或 `reference` |
| `source_ref` | `TEXT` | 否 | 来源引用，例如文档路径、会话日期或外部入口 |
| 正文 | `TEXT` | 是 | memory 的可读内容 |

### 6.5 `.sessions/<session_id>/transcript.jsonl`

`transcript.jsonl` 是 runtime `messages[]` 的可恢复持久化记录，采用 append-only JSONL。

格式：

```json
{"event_id":1,"type":"message","created_at":"2026-05-31T10:00:00Z","message":{"role":"user","content":"你是谁"}}
```

字段约束：

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `event_id` | `INTEGER` | 是 | session 内递增事件 ID |
| `type` | `TEXT` | 是 | 第一版固定支持 `message` |
| `created_at` | `TEXT` | 是 | ISO 8601 时间 |
| `message` | `OBJECT` | 是 | 可恢复到 LLM `messages[]` 的消息 |

### 6.6 `.sessions/<session_id>/metadata.json`

`metadata.json` 是 session 管理索引，不是上下文本体。

格式：

```json
{
  "session_id": "default",
  "created_at": "2026-05-31T10:00:00Z",
  "updated_at": "2026-05-31T10:30:00Z",
  "cwd": "/path/to/project",
  "model": "deepseek-v4-flash",
  "transcript_path": ".sessions/default/transcript.jsonl",
  "summary_path": ".sessions/default/summary.md",
  "artifacts_dir": ".sessions/default/artifacts",
  "event_count": 12,
  "message_count": 12,
  "compacted_until_event_id": 0,
  "summary_status": "none / valid / failed",
  "summary_attempts": 0,
  "last_restore_mode": "full / summary_plus_recent / first_and_recent"
}
```

### 6.7 `.sessions/<session_id>/summary.md`

`summary.md` 是长 transcript compact 后的恢复摘要，不是长期事实来源。

格式：

```markdown
# Session Summary

## Current Objective
当前会话正在围绕本地个人 Q&A Agent 的 session transcript 和 compact 恢复设计进行。

## User Constraints
- transcript 和 `.logs/agent.log` 必须分离。
- summarizer 失败不能阻断 CLI。

## Important Context
- runtime `messages[]` 是当前聊天上下文本体。
- transcript 用于重启恢复 messages。

## Completed Work
- 已确认废弃 `.session/current.md` 任务看板设计。

## Open Threads
- 实现 transcript 恢复和 summary 降级。

## Next Best Step
实现 SessionTranscript 和 SessionMetadata。
```

### 6.8 Compact Record

compact record 是上下文压缩后的结构化摘要，必须能指回原始 artifact。

格式：

```json
{
  "artifact_path": ".sessions/<session_id>/artifacts/run-123-tool-2.txt",
  "summary": "读取了 Agent 设计文档，确认长期知识不能来自未落库对话。",
  "relevance": "当前正在设计 memory 管理，因此该约束必须保留。",
  "must_keep": ["Q&A 知识库和 Agent memory 分开"]
}
```

字段约束：

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `artifact_path` | `TEXT` | 是 | 原始大输出落盘路径 |
| `summary` | `TEXT` | 是 | 简短摘要 |
| `relevance` | `TEXT` | 是 | 与当前任务的关系 |
| `must_keep` | `LIST` | 是 | 必须保留的关键信息 |

### 6.9 Memory Candidate

memory candidate 是 turn-end 提取出的长期 Agent memory 候选。当前实现只生成候选事件，不写入长期记忆；候选不是已写入记忆。

格式：

```json
{
  "name": "separate-qa-and-agent-memory",
  "type": "project",
  "description": "Q&A knowledge base and Agent memory must remain separate",
  "content": "本项目 memory 设计中，Q&A 知识库用于回答用户知识问题，Agent memory 用于指导 Agent 行为，两者必须分开。",
  "source_type": "user_decision",
  "source_ref": "conversation:2026-05-31",
  "confidence": "high",
  "write_policy": "auto_write"
}
```

字段约束：

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `name` | `TEXT` | 是 | 候选 memory 名称 |
| `type` | `TEXT` | 是 | `user`、`feedback`、`project` 或 `reference` |
| `description` | `TEXT` | 是 | 短描述 |
| `content` | `TEXT` | 是 | 候选正文 |
| `source_type` | `TEXT` | 是 | 来源类型 |
| `source_ref` | `TEXT` | 否 | 来源引用 |
| `confidence` | `TEXT` | 是 | `high`、`medium` 或 `low` |
| `write_policy` | `TEXT` | 是 | `auto_write`、`needs_confirmation` 或 `reject` |

---

## 7. 失败模式与降级策略

| 失败模式 | 触发条件 | Agent 行为 | 用户反馈 |
|---|---|---|---|
| Q&A 不完整 | 用户只提供问题或只提供答案 | 不调用保存工具，要求用户补充 | 说明需要完整问题和答案 |
| 保存失败 | SQLite 写入失败或工具返回错误 | 不声称已保存 | 说明保存失败和错误原因 |
| 检索为空 | `search_qa_cards` 返回空 cards | 不编造答案 | 说明本地知识库中没有找到足够依据 |
| 检索结果不相关 | 候选卡片与用户问题无明显关系 | 不基于弱证据回答 | 说明没有足够可靠依据 |
| 读取卡片失败 | `read_qa_card` 找不到 card_id 或数据库错误 | 不引用该卡片作为来源 | 说明来源读取失败 |
| DeepSeek key 缺失 | 真实 LLM 调用时未设置 `DEEPSEEK_API_KEY` | 不调用真实 LLM | 说明缺少环境变量 |
| 配置缺失 | `.env` 和环境变量中均没有 `DEEPSEEK_API_KEY` | CLI Runtime 或 Web Runtime 不启动 Agent | 提示用户设置 `DEEPSEEK_API_KEY` |
| LLM 临时故障 | DeepSeek 网络错误、timeout、SSL EOF、HTTP 429、HTTP 500 或 HTTP 503 | 执行有上限的有限重试；重试耗尽后不编造工具结果或最终回答，结束本轮但不退出 CLI / Web 服务 | 说明模型调用失败，可稍后重试 |
| LLM 不可重试错误 | DeepSeek 返回 HTTP 400、401、402、422，或响应解析 / tool call 参数解析失败 | 不重试，不进入工具流程，不声称动作成功 | 展示明确失败原因 |
| 工具执行失败 | 工具抛错或返回 `ok: false` | 不声称动作成功 | 展示失败原因 |
| CLI 输入为空 | 用户直接回车 | 不调用 AgentLoop | 继续等待输入 |
| CLI 退出 | 用户输入 `/exit` 或 `/quit` | 正常结束循环 | 输出退出提示 |
| CLI Renderer 失败 | 渲染事件时发生异常 | 不影响工具执行和 Agent 最终回答 | 向 stderr 输出简短错误 |
| Web 服务启动失败 | 端口不可用、配置缺失或 Web app 初始化失败 | 不启动 Web Runtime，不创建虚假会话 | 输出明确启动失败原因 |
| Web chat 执行失败 | `POST /api/chat` 调用 AgentLoop 失败 | 返回结构化错误，不声称本轮完成 | HTML 展示本轮失败说明 |
| Web 卡片读取失败 | 最近卡片、搜索或详情 API 读取失败 | 返回结构化错误，不生成虚假卡片 | HTML 展示错误原因 |
| Web 静态页面加载失败 | 静态文件缺失或服务异常 | 不影响数据库内容，不声称 Agent 已启动完成 | 浏览器或终端展示加载失败 |
| 日志队列满 | Async JSONL Logger 队列达到上限 | 不阻塞 Agent Loop，丢弃日志事件 | stderr 最多提示一次 |
| 日志写入失败 | `.logs/agent.log` 无法写入 | 停止继续写日志，不影响 Agent | stderr 最多提示一次 |
| 日志 flush 超时 | 正常退出时 2 秒内未 flush 完成 | 继续退出 | 不保证所有日志写入完成 |
| Memory index 缺失 | `.memory/MEMORY.md` 不存在 | 使用空 memory index 继续运行 | 可提示尚未初始化 Agent memory |
| Memory index 非法 | `MEMORY.md` 表格缺少必填字段或字段非法 | 不注入 memory index，继续 Q&A 主流程 | 说明 memory index 格式非法 |
| Memory frontmatter 非法 | `.memory/*.md` 缺少 name、type、description 或 type 非法 | 跳过该 memory，不注入本轮上下文 | 说明 memory 文件格式非法 |
| Memory 读取失败 | memory 文件不存在或无法读取 | 不注入该 memory，继续 Q&A 主流程 | 说明 memory 读取失败 |
| Transcript 读取失败 | `.sessions/<session_id>/transcript.jsonl` 无法读取或格式非法 | 使用空 messages 继续运行 | 说明 session transcript 未加载 |
| Metadata 写入失败 | `.sessions/<session_id>/metadata.json` 无法写入 | 不影响最终回答，不声称 metadata 已更新 | 说明 session metadata 未更新 |
| Summary 生成失败 | summarizer 最多重试后仍失败 | 使用 first N + recovery notice + recent N 恢复 | 说明 summary 降级恢复 |
| Artifact 落盘失败 | `.sessions/<session_id>/artifacts/` 无法写入 | 降级为不 compact 或保留原始 tool result | 说明 compact artifact 未保存 |
| Compact record 非法 | 缺少 artifact_path、summary、relevance 或 must_keep | 不使用该 compact record | 说明 compact 失败 |
| Memory candidate 生成失败 | MemoryExtractor 执行失败或候选字段生成异常 | 不写入长期 memory，不声称已记住 | 可通过事件或日志说明候选生成失败 |

- **通用降级原则**:
  1. 工具失败时不得假装已完成。
  2. 依据不足时必须明确说明。
  3. 未落库内容不得作为长期记忆引用。
  4. 不得为了回答完整而引入无来源外部知识。
  5. Agent memory 失败不得阻断 Q&A 保存、检索和回答主流程。
  6. Session transcript / summary 失败不得被解释为长期事实缺失。
  7. Compact 失败不得丢失回答所需证据。
  8. Memory candidate 只是候选事件；当前实现不得声称 Agent 已经记住。
  9. Web API 失败时必须返回结构化错误，HTML 不得伪造成功状态。

- **日志降级原则**:
  1. Async JSONL Logger 记录 Agent run 事件，是 Agent run 过程的唯一结构化开发日志。
  2. 日志完整记录用户原始输入，不截断。
  3. 工具 input/output 只记录工具契约声明的可展示字段。
  4. 日志中的工具可展示长文本不截断；CLI 展示时截断。
  5. 日志写入失败、队列满和 flush 超时不得影响 Agent 工具执行和最终回答。
  6. Python 标准库 `logging` 仅保留底层库级异常和不可恢复错误，不承担 Agent loop trace 职责。
  7. 不记录 API key、完整 prompt、完整 messages、secret 或未声明为可展示的内部 payload。

- **配置安全规则**:
  1. `.env` 必须通过 `.git/info/exclude` 在本地忽略，不要求提交仓库级 `.gitignore`。
  2. 不得把 `.env` 内容打印到日志。
  3. 不得把 DeepSeek key 写入文档、测试快照或数据库。

- **Session 恢复降级原则**:
  1. 短 transcript 原样恢复为 runtime `messages[]`。
  2. 长 transcript 优先生成 `summary.md`，再用 summary message + recent messages 恢复。
  3. summarizer 最多重试 3 次。
  4. summarizer 失败后使用 first N messages + recovery notice + recent N messages 恢复。
  5. summary 失败不得阻断 CLI 启动或 Q&A 主流程。

- **Memory candidate 降级原则**:
  1. 当前实现只生成 memory candidate 事件，不自动写入长期 memory。
  2. 候选生成失败不得阻断 Q&A 保存、检索和回答主流程。
  3. 模型推测、临时讨论、敏感信息和过期任务状态不得被声称为已写入长期 memory。

---

## 8. 测试要求

- **单元测试**:
  1. `SQLiteStore.save_card` 能写入并读回 Q&A 卡片。
  2. `SQLiteStore.search_cards` 能按 question、answer、summary、keywords 的 LIKE 命中返回结果。
  3. `SQLiteStore.list_recent_cards` 能按 created_at 倒序返回。
  4. `KnowledgeTools.save_qa_card` 能校验必填字段。
  5. `KnowledgeTools.read_qa_card` 对不存在 ID 返回结构化 not_found。
  6. `DeepSeekClient` 请求构造和响应解析使用 mock 测试。
  7. `DeepSeekClient` 能对可重试网络错误和 HTTP 429、500、503 执行有限重试。
  8. `DeepSeekClient` 对 HTTP 400、401、402、422 不重试。
  9. `DeepSeekClient` 重试耗尽时返回明确错误且不泄露 API key、headers、完整 payload 或 system prompt。
  10. `load_config` 能从 `.env` / 环境变量读取 `DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL` 和 `KNOWLEDGE_DB_PATH`。
  11. 缺少 `DEEPSEEK_API_KEY` 时返回明确错误。
  12. `MemoryIndex` 能读取 `.memory/MEMORY.md` 索引。
  13. `MemoryIndex` 对缺少必填列或非法 type 返回结构化错误。
  14. `MemoryStore` 能读取合法 `.memory/*.md`。
  15. `MemoryStore` 对 frontmatter 缺失或非法 type 返回结构化错误。
  16. `SessionTranscript` 能追加和读取 `.sessions/<session_id>/transcript.jsonl`。
  17. `SessionMetadata` 能创建、读取和更新 `.sessions/<session_id>/metadata.json`。
  18. `SessionRestore` 能短 transcript 原样恢复 messages。
  19. `SessionRestore` 能长 transcript 使用 summary + recent messages 恢复。
  20. summarizer 失败时能使用 first N + recovery notice + recent N 降级恢复。
  21. `ContextCompactor` 对超过阈值的大输出生成 compact record。
  22. compact record 必须包含 artifact_path、summary、relevance 和 must_keep。
  23. `MemoryExtractor` 只生成候选，不直接写入长期 memory。
  24. user / feedback candidate 默认不自动写入长期 memory。
  25. `agent_factory.py` 能创建 AgentLoop 及其依赖，并可被 CLI Runtime 和 Web Runtime 复用。

- **集成测试**:
  1. Agent Loop 能接收 fake LLM 的 tool call，执行工具并回填 tool result。
  2. Agent Loop 在 fake LLM 返回 final answer 时能直接结束。
  3. 保存后再搜索能召回同一张卡片。
  4. CLI Runtime 能用 fake input / fake AgentLoop 跑一次输入和退出流程。
  5. CLI Runtime 在单轮 AgentLoop 失败后不退出，并能继续处理后续输入或 `/exit`。
  6. `pyproject.toml` 必须声明 `pka = "personal_knowledge_agent.__main__:main"` 或等价 script 入口。
  7. Agent Loop 关键阶段会产生结构化事件。
  8. CLI Renderer 对长文本进行截断。
  9. Async JSONL Logger 完整记录 `user_input`。
  10. Async JSONL Logger 使用后台线程异步写入，不阻塞主流程。
  11. Async JSONL Logger 在队列满和写入失败时按降级策略处理。
  12. CLI Runtime 启动时能创建或恢复 `.sessions/default`。
  13. Agent Loop 能基于 runtime `messages[]` 连续运行多轮用户输入。
  14. turn-start 能读取 memory index 并按 user_input / recent messages 选择相关 memory。
  15. Prompt Builder 能注入 memory index 和 selected memories。
  16. 大 tool result 能落盘到 session artifacts 并在 trace / transcript 中保留 compact record。
  17. turn-end 能把可恢复 message 追加到 transcript。
  18. turn-end 能生成 memory candidates 并通过 `memory_candidates_generated` 事件暴露候选。
  19. CLI 入口能在默认模式启动 CLI，并能通过 `pka web` 分发到 Web Runtime。
  20. Web Runtime 能用 fake AgentLoop 处理一次 `POST /api/chat`。
  21. Web Runtime 能返回最近卡片、搜索卡片和卡片详情的结构化结果。
  22. Web Runtime 在 AgentLoop 或卡片读取失败时返回结构化错误。

- **回归测试**:
  1. 检索为空时不会生成虚假来源。
  2. 工具失败时不会返回保存成功。
  3. 回答来源至少包含 card_id、question、source_type、created_at。
  4. 日志不输出 API key。
  5. 日志不输出完整 system prompt 或完整 LLM messages。
  6. Tool event 只包含工具契约声明的可展示字段。
  7. 与新事件流重复的旧 logging 成功路径埋点应删除或收缩。
  8. Q&A 检索只使用 `qa_cards`，不得混入 `.memory/*.md`。
  9. `.sessions/<session_id>/summary.md` 和 `transcript.jsonl` 不得作为长期事实来源。
  10. compact artifact 不得作为 Q&A 回答来源。
  11. Memory candidate 未写入时不得声称已经记住。
  12. memory candidate 事件不得被解释为已写入 `.memory/*.md`。
  13. Web API 不得绕过 AgentLoop 直接完成聊天回答。
  14. Web UI 不得提供未声明的编辑、删除、合并或自动知识图谱能力。

- **可选 Live Smoke Test**:
  1. 仅在存在 `DEEPSEEK_API_KEY` 时运行。
  2. 使用 `deepseek-v4-flash` 做真实 DeepSeek 调用。
  3. 完成一次保存 Q&A。
  4. 再完成一次检索回答。
  5. 启动 `pka web` 并在浏览器完成一次聊天、最近卡片刷新、搜索和详情查看。
  6. 不把 API key 写入仓库或日志。

- **验收清单**:
  1. 符合本文档定义的能力边界。
  2. SQLite `qa_cards` 是 Q&A 知识库唯一长期记忆来源。
  3. 四个工具契约稳定可测。
  4. DeepSeek 只出现在薄 LLM Client 中。
  5. Q&A 知识库和 Agent memory 保持分离。
  6. `.memory/*.md` 是用户可见的 Agent 长期工作记忆来源。
  7. `.sessions/<session_id>/transcript.jsonl` 能恢复 runtime `messages[]`。
  8. `.sessions/<session_id>/summary.md` 只保存长 transcript 的 compact summary。
  9. compact 只缩减上下文窗口，不替代长期 memory。
  10. Web Runtime 只作为本地 Chat + Cards 入口，不改变 Agent 的工具和记忆边界。
  11. 第一版不包含 Wiki、文件监听、周报、多 Agent、向量库和后台任务。

---

## 9. 变更记录

| 日期 | 变更内容 | 变更原因 | 提交 |
|---|---|---|---|
| `2026-05-30` | 新增本地个人 Q&A 知识库 Agent 开发上下文 | 锁定第一版 Agent 设计边界和实现验收依据 | `TBD` |
| `2026-05-31` | 补充 Agent memory、session memory、context compact 和 memory candidate 设计边界 | 为后续实现 Claude Code 风格记忆管理先锁定文档契约 | `TBD` |
| `2026-05-31` | 将 session 设计从 `.session/current.md` 调整为 `.sessions/<session_id>/transcript.jsonl`、`summary.md` 和 `metadata.json` | 对齐 messages[] + transcript + compact summary 的聊天上下文设计 | `TBD` |
| `2026-06-02` | 标记最终版功能清单相对当前实现的完成状态 | 帮助区分当前第一版闭环、部分 Harness 能力和最终版未实现模块 | `TBD` |
| `2026-06-02` | 补充 Web Runtime、Chat + Cards UI 和 agent_factory 设计边界 | 支持本地浏览器聊天入口和基础 Q&A 卡片浏览 | `TBD` |
| `2026-06-07` | 将工具列表、上下文压缩、memory candidate 和 Web 状态调整为当前代码实现边界 | 修正文档中把内部机制和未完成写入闭环描述为当前 LLM 可调用工具的问题 | `TBD` |
