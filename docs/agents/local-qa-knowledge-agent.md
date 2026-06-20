---
module: "local-qa-knowledge-agent"
title: "本地个人 Q&A 知识库"
language: "Python"
agent_type: "Tool-Using Agent / RAG Agent"
last_updated: "2026-06-20"
---

# 本地个人 Q&A 知识库 Agent 开发上下文

> **文档定位**  
> 本文档是面向人类开发者和 AI Coding 工具的 Agent 开发上下文文档。  
> 它用于约束本地个人 Q&A 知识库 Agent 的角色定位、能力边界、Harness 架构、可调用工具、上下文来源、核心业务流、数据模型和测试要求。  
> 本文档不是终端用户说明，也不是运行时 Prompt。
> 本文档只记录本 Agent 可长期维护的设计边界。
> 本文档不得记录单次任务计划、临时实施步骤、Git 分支安排、工作进度或当前对话待办。
> 任务计划应按照协作规约在当前对话中单独输出。

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
  10. 能基于 LLM API 返回的真实 token usage 计算上下文占比，并在下一轮 LLM 调用前触发 runtime compact。
  11. 能在 LLM API 明确返回上下文超限错误时执行 runtime compact，并对同一次 LLM 请求最多重试一次。
  12. 能通过本地 Web Runtime 提供浏览器聊天入口和基础 Q&A 卡片浏览能力。

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
  12. 将每轮注入上下文的 `.memory/*.md` 长期记忆文档全文限制为最多 3 条；`.memory/MEMORY.md` 索引不计入该上限。
  13. 在 turn 结束后提取 memory candidates，并通过事件暴露候选；当前不自动写入长期 memory 或维护待确认队列。
  14. 提供本地 HTML 聊天入口，作为 CLI Runtime 的浏览器替代输入输出层。
  15. 在 Web UI 中查看最近 Q&A 卡片、搜索 Q&A 卡片和查看卡片详情。

- **不包含能力**:
  1. 不做 Markdown Wiki。
  2. 不做文件监听或自动索引。
  3. 不做周报、日报或自动总结。
  4. 不做多 Agent。
  5. v0.4 之前不做向量数据库；v0.4 起只把 Qdrant 作为 Q&A 语义索引，不作为事实源。
  6. 不做去重合并。
  7. 不做后台任务。
  8. 不做复杂权限系统。
  9. 不把 Agent memory 混入 Q&A 知识库来源。
  10. 不默认把完整历史对话作为长期记忆。
  11. 不默认把所有 `.memory/*.md` 全文注入每轮上下文。
  12. v0.4 之前不实现向量检索、后台自动整理任务或复杂双向同步；v0.4 的向量检索仅限 Q&A 卡片 hybrid 检索闭环。
  13. Web 第一版不做卡片编辑、删除、合并、自动知识图谱、Wiki、文件监听、多 Agent 或后台任务。

- **最终版功能清单完成状态**:

| 模块 | 状态 | 当前实现边界 |
|---|---|---|
| Q&A 知识管理 | 部分完成 | 已实现保存 Q&A 卡片、读取卡片、LIKE 检索、hybrid 检索、最近卡片列表、更新、删除和 category；尚未实现标题、标签、导入和导出。 |
| Markdown Wiki 管理 | 未完成 | 当前 Agent 明确不包含 Wiki、文件监听和自动索引；不得声称支持 Wiki 绑定、Markdown chunk、hash 或增量同步。 |
| 统一知识检索 | 部分完成 | 已实现 `search_qa_cards` SQLite LIKE 检索和 `hybrid_search_qa_cards` 混合检索；尚未实现过滤器、检索调试或统一 `search_knowledge`。 |
| 来源追踪 | 部分完成 | Q&A 来源可追溯到 card_id、question、source_type 和 created_at；程序会从本轮真实工具结果重写来源区块并清理无证据来源声明；尚未支持 Markdown chunk、代码经验、手动笔记等来源类型。 |
| 分类与标签体系 | 部分完成 | 已支持单一 category 的生成、保存、更新和过滤；当前没有 tags、标签列表、分类列表、标签重命名、标签合并或相似标签建议。 |
| 知识去重与合并 | 未完成 | 当前尚未实现 v0.6；目标是疑似重复检测和用户确认合并，不做自动合并、后台全库扫描、历史版本或复杂审计表。 |
| 代码经验管理 | 未完成 | 当前没有报错记录、解决方案、代码片段、项目复盘、错误信息检索或面试复盘素材生成能力。 |
| 复习系统 | 未完成 | 当前没有复习卡、今日待复习、复习结果、间隔重复、按标签/分类复习或自动小测题。 |
| 内容输出 | 未完成 | 当前明确不做周报、日报或自动总结；没有学习总结、周报、博客大纲、面试提纲、简历项目描述或项目复盘总结能力。 |
| Agent Harness | 部分完成 | 已实现 Agent Loop、Tool Dispatcher、Prompt Builder、运行时上下文拼接和工具调用结果回填；工具注册仍是静态映射，尚未形成完整可扩展注册机制。 |
| 后台任务 | 未完成 | 当前明确不做后台任务；没有后台 Wiki 同步、索引构建、批量摘要、任务状态、完成通知或失败重试。 |
| 权限与审计 | 部分完成 | 已实现运行事件和 JSONL 开发日志；更新和删除确认已实现；合并、覆盖和图谱确认等后续高风险操作尚未实现。v0.4 语义索引重建是系统维护工具，不作为高风险确认操作。 |
| 长期偏好记忆 | 部分完成 | 已支持读取 Agent memory index 和相关 memory，并能生成 memory candidates 事件；尚未实现偏好写入确认闭环，以及偏好查看、修改、删除。 |
| Web Chat + Cards | 部分完成 | 已实现本地 HTML 聊天入口、流式聊天接口、最近卡片、卡片搜索和卡片详情；不包含编辑、删除、合并或复杂知识图谱。 |

以上状态仅描述当前代码已实现能力，不代表最终版设计已被纳入当前 Agent 边界。若要实现未完成模块，必须先更新本文档中的角色边界、工具契约、数据模型、核心流程、失败模式和测试要求，并单独提交文档变更后再进入代码实现。

- **v0.2-v0.7 演进路线和技术选型**:

| 版本 | 阶段目标 | 技术选型 / 关键设计 | 当前状态 |
|---|---|---|---|
| `v0.2` | 可信来源闭环 | AgentLoop 只记录本轮 `turn_messages` 边界；程序从当前 turn 的真实工具结果生成来源区块；未调用检索工具时允许普通回答，但不得声称来自本地知识库或伪造 card_id | 已完成 |
| `v0.3` | Q&A 维护 | 支持更新和删除 Q&A 卡片；删除是物理删除，不使用软删除；更新不保存历史版本；高风险操作必须经过 PreToolUse permission gate，CLI 由用户确认后才执行 | 已完成 |
| `v0.4` | Hybrid 检索 | 使用 SQLite LIKE 做关键词兜底，使用 DashScope / Qwen `text-embedding-v4` + Qdrant local mode 做语义召回；通过 `is_vectorized` 标记历史卡片是否已写入语义索引，并通过 `hybrid_search_qa_cards` 合并排序 | 已完成 |
| `v0.5` | 分类 | `qa_cards` 增加必填 category 字段；category 由模型按语义主归属生成，用户可通过 update 工具手动修改；本阶段不新增 tags，keywords 继续承担检索词职责 | 已完成 |
| `v0.6` | 去重和合并 | 基于 SQLite LIKE + Qdrant 召回重复候选；候选低于阈值直接过滤，不返回 discard；合并后的新卡片内容由模型生成；`merge_qa_cards` 必须经过 PreToolUse permission gate，确认后创建新卡片并物理删除原卡片 | 规划中，未实现 |
| `v0.7` | 轻量知识图谱 | 使用 Kuzu 作为本地轻量图数据库；候选实体和关系不是事实；图谱写入必须经过 PreToolUse permission gate；图谱回答仍必须追溯到 card_id | 规划中，未实现 |

- **v0.2-v0.7 已确认设计决策**:
  1. SQLite 继续作为 Q&A 事实库；外部索引或图数据库不得替代事实源。
  2. 本阶段不引入正式数据库 migration 框架；表结构必须在本文档中记录，schema 初始化只能补齐缺失表和字段，不得破坏已有数据。
  3. 未调用检索工具时不强制拒答；但 Agent 不得声称回答来自本地知识库，不得编造来源或 card_id。
  4. 删除就是物理删除；后续实现中不得引入软删除概念。
  5. 更新只修改当前卡片，不保存历史版本或 before / after 快照。
  6. 删除、更新、合并和确认图谱关系等高风险操作必须经过 harness 的 PreToolUse permission gate；模型只能请求工具，不能自行确认或绕过权限层。v0.4 的 `rebuild_qa_semantic_index` 是系统维护工具，不需要用户确认。
  7. v0.4-v0.6 不引入 Meilisearch；SQLite LIKE 作为关键词兜底，Qdrant 作为语义召回索引。
  8. v0.4 不引入 Docker 或 Docker Compose；Qdrant 使用 qdrant-client local mode，默认索引目录为 `.knowledge/qdrant`，后续统一打包时再单独设计容器化。
  9. Kuzu 使用本地文件数据库，默认路径位于 `.knowledge/` 下，不通过 Docker 管理。
  10. DashScope / Qwen `text-embedding-v4` 是 v0.4 的默认远程 embedding 服务；DeepSeek 继续作为主 LLM，不承担 embedding 职责。
  11. 删除卡片时必须物理删除 SQLite 卡片，并尽力删除 Qdrant 向量；v0.7 引入 Kuzu 后，再同步处理 Kuzu 中只由该卡片支撑的来源链接。
  12. Web UI 不随 v0.2-v0.7 后端路线同步扩展；后续另行设计和实现。
  13. v0.5 不新增 tags；tags 与 keywords 当前职责容易重叠，等 v0.6 去重合并和 v0.7 图谱后再基于真实知识聚类与实体关系重新设计。

- **行为约束**:
  1. 凡是涉及长期记忆的动作，必须通过工具完成。
  2. Agent 不得声称已经保存、查询或更新实际未通过工具完成的数据。
  3. 声称基于本地知识库回答、引用 card_id 或展示来源区块时，必须有本轮真实工具证据。
  4. 没有足够依据时必须明确说明本地知识库中没有找到足够依据。
  5. 回答不得引入无来源外部知识。
  6. Q&A 知识库和 Agent memory 必须分开。
  7. `.memory/*.md` 用于 Agent 长期工作记忆，不得作为 Q&A 回答的知识卡片来源。
  8. `.sessions/<session_id>/summary.md` 只表示当前会话 compact summary，不得当作长期事实来源。
  9. compact 只能缩减当前上下文窗口，不得替代长期记忆写入。
  10. memory candidate 只表示候选，不表示已写入长期 memory；当前实现不得声称候选已经保存。
  11. session summary 不得作为 user message 注入 `messages[]`；只能作为 `system_prompt` 中独立的 Runtime Session Context section 注入。
  12. Runtime Session Context 只用于恢复当前 session 状态，不是用户新请求、长期 memory 或 Q&A 知识来源。
  13. 每轮注入上下文的 `.memory/*.md` 长期记忆文档全文最多 3 条；`.memory/MEMORY.md` 索引不计入这 3 条。
  14. Web UI 只能展示和发起用户意图，不得绕过 AgentLoop、Tools 或 Store 执行业务动作。

---

## 2. Harness 架构与代码边界

> 本节说明 Agent Harness 的组成，以及各层职责边界。

- **Agent Runtime 职责**:
  - 接收用户输入并维护本轮 messages。
  - 调用 Agent Prompt Builder 获取 system prompt。
  - 调用 LLM Client。
  - 判断 LLM 是否返回 tool calls。
  - 调用 Tool Dispatcher 执行工具。
  - 将 tool result 回填 messages。
  - 在没有 tool calls 时返回最终回答。
  - 使用 LLM API response 中的 usage 记录真实 token 用量，并基于 `usage.prompt_tokens / context_window_tokens` 计算 `prompt_usage_ratio`。
  - `context_window_tokens` 是 Agent Runtime 必备配置值；当前默认模型 `deepseek-v4-flash` 的默认值为 `1_000_000`，可通过 `DEEPSEEK_CONTEXT_WINDOW_TOKENS` 覆盖。
  - 当前不做本地 token 估算、不做字符数 preflight、不引入 provider token count API。
  - 保存上一轮 LLM 调用后的 `last_prompt_usage_ratio`；下一轮 LLM 调用前，如果达到 `0.75`，先执行 runtime compact。
  - 如果 LLM API 明确返回 context length exceeded / token limit exceeded 类错误，应执行 runtime compact，并对同一次 LLM 请求最多重试一次。
  - 上下文超限 retry 只针对明确的上下文超限错误，不得泛化到 429、500、认证失败、参数错误或普通响应解析错误。
  - runtime compact 是 harness 内部能力，不作为 LLM 可自由调用 tool 暴露。
  - Agent Loop 只负责 compact 触发与 retry 编排；具体压缩由 Runtime Context Compactor 负责。
  - Agent loop runner 的主运行骨架保持 `run(user_input) -> str`，不得为了展示层流式效果新增第二套 Agent 主入口。
  - 在关键阶段产生结构化运行事件，包括 `user_input_received`、`llm_call_started`、`answer_delta`、`llm_call_finished`、`tool_call_started`、`tool_call_finished`、`evidence_checked`、`final_answer_generated` 和 `error`。
  - `answer_delta` 只表示最终回答文本的实时增量，用于 CLI / Web 展示；`final_answer_generated` 仍是 evidence check 后的权威最终答案。
  - 运行事件用于 CLI 实时展示和本地开发日志，不作为长期知识来源。
  - `answer_delta` 默认不写入 JSONL 开发日志，避免 token 级事件刷屏；JSONL 日志仍记录 `final_answer_generated` 的完整最终答案。
  - 运行事件只描述可审计过程，不暴露模型完整思考链。

- **Agent Bootstrap 职责**:
  - `agent_component_factory.py` 负责创建 Agent loop runner 及其依赖，包括 Q&A 数据访问、Agent tools、ToolDispatcher、DeepSeekChatClient、conversation session、Agent profile memory 和 tool result compactor。
  - `agent_runtime_config.py` 负责从 `.env` 和环境变量加载 Agent 运行配置。
  - 供 CLI Runtime 和 Web Runtime 复用同一套 Agent 装配逻辑。
  - 不负责 CLI 输入、Web HTTP 请求、HTML 渲染、浏览器打开或进程启动。

- **Agent Context 职责**:
  - 管理每轮 Agent 可用上下文，包括 prompt、conversation session、Agent profile memory 和 tool result compact。
  - 不把 conversation session transcript、summary 或 compact artifact 当作 Q&A 长期事实来源。
  - 不把 Agent profile memory 当作 Q&A 回答来源。
  - Runtime Context Compactor 负责将 runtime `messages[]` 压缩为固定规格 session summary + recent messages，并写入 `.sessions/<session_id>/summary.md`。
  - Runtime Context Compactor 失败时生成 recovery notice；该 notice 只能作为 Runtime Session Context 注入，不得伪装成 user message。

- **Agent Prompt Builder 职责**:
  - 运行时拼接短 system prompt。
  - 包含身份、行为规则、工具使用规则、回答格式和拒答规则。
  - 在 turn-start 阶段接收 memory index、selected memories 和 session summary，并将其压缩注入本轮上下文。
  - session summary 应注入为独立的 `# Runtime Session Context` section；该 section 必须声明 summary 不是用户新请求、不是长期 memory、不是 Q&A 知识来源。
  - 不保存业务数据。
  - 不承担数据库读写职责。

- **Agent Profile Memory 职责**:
  - 读取 `.memory/MEMORY.md` memory index。
  - 按需读取少量相关 `.memory/*.md`。
  - 每轮注入上下文的 `.memory/*.md` 长期记忆文档全文最多 3 条；`.memory/MEMORY.md` 索引不计入这 3 条。
  - 校验 memory frontmatter 和索引字段。
  - 当前仅提供 Agent memory 读取能力；尚未实现 memory candidate 写入入口、确认队列或索引更新流程。
  - 不直接回答用户知识问题。
  - 不把 Agent memory 写入 SQLite `qa_cards` 表。

- **Conversation Transcript 职责**:
  - 将 user message、assistant message、assistant tool call message 和 tool result message 追加写入 `.sessions/<session_id>/transcript.jsonl`。
  - CLI 重启时从 transcript 恢复 runtime `messages[]`。
  - transcript 只服务当前聊天上下文恢复，不作为 Q&A 知识来源。

- **Conversation Session Metadata 职责**:
  - 读写 `.sessions/<session_id>/metadata.json`。
  - 记录 session_id、cwd、model、created_at、updated_at、message_count、event_count、summary_status、summary_attempts 和 last_restore_mode。
  - 不保存 API key、secret、完整 headers 或非恢复必需 payload。

- **Conversation Session Restore / Summarizer 职责**:
  - 当 transcript 未超过预算时原样恢复 `messages[]`。
  - 当 transcript 超过预算时，调用 summarizer 生成 `.sessions/<session_id>/summary.md`。
  - session summary 必须使用固定 Markdown 规格，包含 `# Session Summary`、`## Current Goal`、`## User Constraints`、`## Known Context`、`## Completed Work`、`## Next Step` 和 `## Boundaries`。
  - `## Boundaries` 必须声明 summary 不是用户新请求、不是长期 memory、不是 Q&A 知识来源。
  - session summary 不得作为 user message 注入 `messages[]`；restore compact 成功后应返回 recent messages 和独立 summary，由 Prompt Builder 注入 Runtime Session Context。
  - summarizer 最多重试 3 次。
  - summarizer 失败时使用 recent messages + recovery notice 降级恢复；recovery notice 不得作为 user message 注入，只能作为 Runtime Session Context 注入。

- **Tool Result Compactor 职责**:
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
  - 发起 DeepSeek streaming chat 请求，并在收到最终回答文本增量时调用可选 delta callback。
  - 解析 API response 中的 usage，返回 prompt_tokens、completion_tokens 和 total_tokens。
  - 保守识别 DeepSeek 明确返回的 context length exceeded / token limit exceeded 类错误，并将其转换为专用上下文超限错误供 Agent Runtime 处理。
  - 对 DeepSeek 临时故障执行有上限的有限重试，不得无限阻塞 CLI。
  - 可重试错误包括网络连接类错误、timeout、SSL EOF，以及 HTTP 429、500、503。
  - 不可重试错误包括 HTTP 400、401、402、422，以及响应解析错误和 tool call 参数解析错误。
  - 重试耗尽后抛出明确错误，错误信息不得包含 API key、完整 headers、完整 payload 或完整 system prompt。
  - 将 DeepSeek 响应转换为统一的 LLMResponse。
  - DeepSeek 流式 tool call 分片只能在 LLM Client 内部聚合为完整 ToolCall 后返回，不得把半截 JSON 参数暴露给 CLI / Web UI。
  - LLM Client 不产出 AgentEvent，不包含 CLI、Web、SSE 或 UI 展示逻辑。
  - 不包含 Agent 业务判断逻辑。

- **CLI Runtime 职责**:
  - 作为 `python -m personal_knowledge_agent` 和安装后 `pka` 命令的启动入口。
  - 启动时加载 `.env` 和环境变量配置。
  - 初始化 Q&A 数据访问、Agent tools、ToolDispatcher、DeepSeekChatClient 和 Agent loop runner。
  - 进入持续交互循环，读取用户输入并打印 Agent 回复。
  - 使用 `prompt-toolkit` 提供交互式输入，不使用裸 `input()` 作为主要输入方式。
  - 输入层只负责采集用户输入，不做知识保存、检索或业务判断。
  - 支持 `/exit` 和 `/quit` 退出。
  - 实时接收 Agent Loop 事件。
  - 将事件交给 CLI Renderer 渲染。
  - 将除 `answer_delta` 以外的事件投递给 Async JSONL Logger。
  - CLI 展示长文本时必须做确定性截断。
  - CLI 最终回答应使用 DeepSeek streaming 的真实文本增量展示；收到 `final_answer_generated` 后只做收尾或权威答案修正，不重复打印同一段最终回答。
  - 单轮 AgentLoop 执行失败时，应展示本轮失败提示并继续等待下一轮输入。
  - 单轮模型或工具运行失败不得导致 CLI 进程退出；启动阶段不可恢复错误、用户输入 `/exit` 或 `/quit` 除外。
  - 不直接操作 SQLite。
  - 不绕过 AgentLoop 调用工具。

- **Web Runtime 职责**:
  - 作为 `pka web` 和 `python -m personal_knowledge_agent.web` 的本地浏览器入口。
  - 启动时加载 `.env` 和环境变量配置。
  - 通过 `agent_component_factory.py` 按 `session_id` 创建 Agent loop runner 及其依赖。
  - 启动绑定在 `127.0.0.1` 的本地 HTTP 服务。
  - 提供静态 HTML/CSS/JS 页面。
  - 通过流式聊天接口接收用户输入并调用对应 session 的 AgentLoop。
  - 提供会话创建、会话列表、会话重命名和会话历史消息读取 API。
  - 提供最近卡片、搜索卡片和卡片详情 API。
  - Web 输入层只负责采集用户输入，不判断知识录入或问答意图。
  - Web API 不直接操作 SQLite，不绕过 Tools 或 Store 边界。
  - Web 聊天接口只保留流式 `/api/chat/stream`，不保留非流式 `/api/chat` 聊天路径。
  - `/api/chat/stream` 请求体支持可选 `session_id`；未提供时使用 `default` session。
  - `session_id` 是本地 Harness 概念；DeepSeek API 不接收也不感知 `session_id`。
  - Web Runtime 必须根据 `session_id` 选择本地对应 AgentLoop 的 runtime `messages[]`，并将该 messages 传给 DeepSeek。
  - Web Runtime 必须只转发当前 session 当前请求的 AgentLoop 事件，不得使用全局尾部事件拼接本轮流程。
  - Web Runtime 必须按 session 隔离 AgentLoop、runtime `messages[]`、transcript、metadata 和事件队列。
  - 同一 session 的聊天请求必须串行执行；不同 session 不得共享 runtime `messages[]`。
  - Web Runtime 不缓存 `answer_delta` 到全局事件列表或 JSONL 开发日志。
  - Web Runtime 遇到高风险工具 `ask` 权限时，必须通过当前流式聊天事件向 HTML 页面发出 `permission_requested` 事件，并在当前 Agent run 内等待用户确认。
  - Web Runtime 的高风险工具确认必须通过 HTML 页面中的独立阻断式确认浮层完成，聊天消息流只展示轻量状态提示，不承载允许 / 拒绝按钮。
  - Web Runtime 的高风险工具确认浮层只展示后端生成的参数摘要和风险说明，不向 HTML 页面暴露完整 tool arguments。
  - Web Runtime 的高风险工具确认等待时间为 5 分钟；用户允许后才执行工具，用户拒绝、确认超时、浏览器刷新或 SSE 断连时必须默认拒绝并返回 `permission_denied` tool result。
  - Web 第一版只覆盖 Chat + Cards，不提供编辑、删除、合并或复杂知识管理能力。
  - Web Runtime 的单轮 AgentLoop 执行失败时，应返回结构化错误，不得声称保存、查询或回答成功。

- **CLI Renderer 职责**:
  - 根据事件类型渲染用户可见输出。
  - LLM 阶段展示阶段名、开始、结束和失败状态。
  - Tool call 展示工具名和可展示输入字段。
  - Tool result 展示工具名、状态、耗时和可展示输出字段。
  - `answer_delta` 以类似本地 Codex 的方式追加展示最终回答文本。
  - Final answer 事件用于回答收尾和权威答案修正，不应重复打印已经通过 `answer_delta` 展示的完整回答。
  - 不展示原始 LLM messages、system prompt、API key、secret、完整内部 payload 或模型完整思考链。

- **Agent Tools 职责**:
  - 作为 LLM 可调用工具的 adapter，是 Agent 可执行动作的唯一入口。
  - 校验工具输入。
  - `QAKnowledgeToolHandlers` 只提供 Q&A 卡片保存、检索、读取、更新、删除、最近列表和语义索引维护工具。
  - `AgentMemoryToolHandlers` 只提供 Agent profile memory index 和 memory 全文读取工具。
  - 两组 tool handlers 由 `ToolDispatcher` 独立注册。
  - 不直接拼接最终自然语言回答。
  - 不负责上下文压缩；当前上下文压缩由 Agent runtime 内部的 Tool Result Compactor 自动完成。
  - 将成功、失败和未找到结果统一转换为结构化 tool result。

- **Q&A Data Access 职责**:
  - `QACardRepository` 负责 SQLite `qa_cards` 表初始化、保存、读取、更新、删除、LIKE 检索、最近列表、category 校验和 vectorized 标记。
  - `QACardSemanticIndex` 负责 Q&A card embedding、Qdrant local mode upsert/search/delete。
  - Q&A data access 不调用 LLM，不校验 LLM tool arguments，不组织最终自然语言回答。

- **Agent Profile Memory Repository 职责**:
  - `AgentMemoryDocumentRepository` 负责 `.memory/*.md` 的读取、frontmatter 解析和内容校验。
  - `AgentMemoryIndexRepository` 负责 `.memory/MEMORY.md` 的读取和校验。
  - `AgentMemoryCandidateExtractor` 只生成候选，不直接写入长期 memory。

- **Conversation Session Repository 职责**:
  - `ConversationTranscriptRepository` 负责 `.sessions/<session_id>/transcript.jsonl` 的追加和读取。
  - `ConversationTranscriptRepository` 负责校验 `session_id`，避免路径穿越或非法 session 目录。
  - `ConversationTranscriptRepository` 负责从 transcript 派生用户可见历史消息，只返回 user message 和 assistant 最终回答，不返回 tool result、assistant tool call、system prompt 或完整内部 payload。
  - `ConversationSessionMetadataRepository` 负责 `.sessions/<session_id>/metadata.json` 的读写。
  - `ConversationSessionMetadataRepository` 负责保存 session 标题、标题来源和最后用户消息。
  - `ConversationSessionMetadataRepository` 负责列出本地 `.sessions/*/metadata.json`，供 Web 会话列表使用。
  - `ConversationSessionRestorer` 负责从 transcript / summary 恢复 runtime `messages[]`。
  - `ConversationSessionSummarizer` 负责长 transcript 的 summary 生成和失败降级。

- **Storage / External API 职责**:
  - SQLite `qa_cards` 是第一版 Q&A 知识库的唯一长期记忆来源。
  - `.memory/*.md` 是 Agent 长期工作记忆来源。
  - `.memory/MEMORY.md` 是 Agent memory index，只保存 name、type、description 和 path。
  - `.sessions/<session_id>/transcript.jsonl` 是 runtime `messages[]` 的可恢复持久化记录。
  - `.sessions/<session_id>/summary.md` 是长 transcript compact 后的恢复摘要，不是长期事实来源。
  - `.sessions/<session_id>/metadata.json` 是 session 管理索引，不参与 Q&A 回答。
  - `.sessions/<session_id>/artifacts/` 保存 compact 后可回读的大输出，不是长期事实来源。
  - DeepSeek 是第一版 LLM 服务。
  - Qdrant local mode 仅作为 Q&A 语义索引，不是事实源。
  - 第一版不引入外部知识库或后台任务。

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
| `src/personal_knowledge_agent/agent_bootstrap/` | Agent 运行配置加载和组件装配 |
| `src/personal_knowledge_agent/agent_bootstrap/agent_component_factory.py` | 创建 Agent loop runner 及其依赖，供 CLI Runtime 和 Web Runtime 复用 |
| `src/personal_knowledge_agent/agent_bootstrap/agent_runtime_config.py` | 从 `.env` 和环境变量加载 Agent 运行配置 |
| `src/personal_knowledge_agent/agent_runtime/` | Agent loop 运行、LLM call、tool call、最终回答、来源证据和事件发射 |
| `src/personal_knowledge_agent/agent_runtime/agent_loop_runner.py` | Agent loop 核心调用链 |
| `src/personal_knowledge_agent/agent_runtime/agent_llm_call_runner.py` | 单次 Agent LLM 调用和对应事件 |
| `src/personal_knowledge_agent/agent_runtime/agent_tool_call_runner.py` | 单次 Agent tool call、耗时、compact 和对应事件 |
| `src/personal_knowledge_agent/agent_runtime/agent_answer_finalizer.py` | Agent 最终回答收尾和最大轮次停止 |
| `src/personal_knowledge_agent/agent_runtime/answer_source_evidence.py` | 从本轮真实 tool result 提取和渲染回答来源证据 |
| `src/personal_knowledge_agent/agent_runtime/agent_events.py` | Agent run 结构化事件契约 |
| `src/personal_knowledge_agent/agent_runtime/agent_event_emitter.py` | Agent run 事件发射适配 |
| `src/personal_knowledge_agent/agent_context/` | Agent 每轮上下文来源、conversation session 和 Agent profile memory |
| `src/personal_knowledge_agent/agent_context/agent_prompt_builder.py` | 构建运行时 system prompt |
| `src/personal_knowledge_agent/agent_context/conversation_sessions/` | `.sessions/` 会话恢复、摘要、transcript 和 artifact |
| `src/personal_knowledge_agent/agent_context/conversation_sessions/conversation_transcript_repository.py` | 追加和读取 `.sessions/<session_id>/transcript.jsonl` |
| `src/personal_knowledge_agent/agent_context/conversation_sessions/conversation_session_metadata_repository.py` | 读写 `.sessions/<session_id>/metadata.json` |
| `src/personal_knowledge_agent/agent_context/conversation_sessions/conversation_session_restorer.py` | 从 transcript 或 summary 恢复 runtime `messages[]` |
| `src/personal_knowledge_agent/agent_context/conversation_sessions/conversation_session_summarizer.py` | 长 transcript 自动总结和失败降级 |
| `src/personal_knowledge_agent/agent_context/conversation_sessions/tool_result_compactor.py` | 大工具结果落盘和 compact record 生成 |
| `src/personal_knowledge_agent/agent_context/agent_profile_memory/` | `.memory/` 长期 Agent 工作记忆读取和候选提取 |
| `src/personal_knowledge_agent/agent_context/agent_profile_memory/agent_memory_document_repository.py` | 读取 `.memory/*.md` 长期 Agent memory |
| `src/personal_knowledge_agent/agent_context/agent_profile_memory/agent_memory_index_repository.py` | 读取 `.memory/MEMORY.md` 记忆索引 |
| `src/personal_knowledge_agent/agent_context/agent_profile_memory/agent_memory_candidate_extractor.py` | 生成 memory candidates |
| `src/personal_knowledge_agent/agent_tools/` | LLM 可调用工具 adapter |
| `src/personal_knowledge_agent/agent_tools/qa_knowledge_tools/qa_knowledge_tool_handlers.py` | Q&A 知识工具输入校验和 tool result 组装 |
| `src/personal_knowledge_agent/agent_tools/agent_memory_tools/agent_memory_tool_handlers.py` | Agent memory 读取工具输入校验和 tool result 组装 |
| `src/personal_knowledge_agent/qa_data_access/` | Q&A card 的 SQLite 和 Qdrant 数据访问 |
| `src/personal_knowledge_agent/qa_data_access/qa_card_models.py` | Q&A card 和检索结果数据契约 |
| `src/personal_knowledge_agent/qa_data_access/qa_card_repository.py` | Q&A card SQLite 初始化、写入、读取、检索 |
| `src/personal_knowledge_agent/qa_data_access/qa_card_semantic_index.py` | Q&A card semantic index |
| `src/personal_knowledge_agent/tool_runtime/tool_models.py` | Tool call 数据契约 |
| `src/personal_knowledge_agent/tool_runtime/tool_dispatcher.py` | 工具分发和错误包装 |
| `src/personal_knowledge_agent/tool_runtime/tool_permission_policy.py` | 工具权限判断、审批请求和拒绝结果 |
| `src/personal_knowledge_agent/apps/cli/cli_event_renderer.py` | CLI 实时事件渲染 |
| `src/personal_knowledge_agent/agent_observability/agent_event_jsonl_logger.py` | 异步 Agent event JSONL 开发日志 |
| `src/personal_knowledge_agent/llm_clients/llm_models.py` | LLM response 数据契约 |
| `src/personal_knowledge_agent/llm_clients/deepseek_chat_client.py` | DeepSeek chat 薄客户端 |
| `src/personal_knowledge_agent/__main__.py` | CLI 薄转发入口，供 `python -m personal_knowledge_agent` 和 `pka` 复用 |
| `src/personal_knowledge_agent/apps/cli/cli_main.py` | CLI 持续交互入口和 `pka web` 子命令分发 |
| `src/personal_knowledge_agent/apps/web/` | 本地 Web Runtime、Web API 和静态 HTML 页面 |
| `src/personal_knowledge_agent/apps/web/web_app.py` | 创建本地 Web app，定义聊天和卡片浏览 API |
| `src/personal_knowledge_agent/apps/web/web_main.py` | Web Runtime 启动入口 |
| `src/personal_knowledge_agent/apps/web/static/` | Chat + Cards 的原生 HTML/CSS/JS 页面 |
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
| `hybrid_search_qa_cards` | 混合检索相关 Q&A 卡片 | 用户提出本地知识库问题时优先调用 | 否 | 否 |
| `read_qa_card` | 读取完整 Q&A 卡片 | 需要核对完整来源时 | 否 | 否 |
| `update_qa_card` | 更新 Q&A 当前卡片 | 用户明确要求修改已有卡片时 | 是 | 是 |
| `delete_qa_card` | 物理删除 Q&A 卡片 | 用户明确要求删除已有卡片时 | 是 | 是 |
| `list_recent_cards` | 列出最近保存卡片 | 用户要求查看最近记录或保存后确认时 | 否 | 否 |
| `rebuild_qa_semantic_index` | 重建 Q&A 语义索引 | 本地维护历史卡片向量化状态时 | 是 | 否 |
| `detect_duplicate_cards` | 检测疑似重复 Q&A 卡片 | 用户主动查重/整理/合并，或保存/更新成功后的低打扰自动检测 | 否 | 否 |
| `merge_qa_cards` | 合并多张 Q&A 卡片为新卡片并删除原卡片 | 用户看过候选和合并草案，并明确要求合并时 | 是 | 是 |
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
  "keywords": ["关键词列表，至少 1 个"],
  "category": "语义主归属分类，非空字符串"
}
```

- **输出**:

```json
{
  "ok": true,
  "card_id": "本地唯一卡片 ID",
  "source_type": "manual_qa",
  "created_at": "ISO 8601 时间",
  "category": "语义主归属分类"
}
```

- **可展示输入字段**:
  - `question`
  - `answer`
  - `summary`
  - `keywords`
  - `category`

- **可展示输出字段**:
  - `ok`
  - `card_id`
  - `source_type`
  - `created_at`
  - `category`
  - `error_code`
  - `message`

- **副作用**:
  写入 SQLite `qa_cards` 表。

- **失败处理**:
  输入缺少必填字段、字段为空、category 非法或数据库写入失败时，返回 `ok: false`、`error_code` 和 `message`。工具失败时 Agent 不得声称保存成功。

#### `search_qa_cards`

- **职责**:
  根据用户问题检索本地 Q&A 卡片，返回候选结果供 Agent 判断依据是否足够。

- **输入**:

```json
{
  "query": "用户问题或检索词，非空字符串",
  "limit": 5,
  "category": "可选；用户明确限定分类时传入"
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
      "created_at": "ISO 8601 时间",
      "category": "语义主归属分类"
    }
  ]
}
```

- **可展示输入字段**:
  - `query`
  - `limit`
  - `category`

- **可展示输出字段**:
  - `ok`
  - `cards.card_id`
  - `cards.question`
  - `cards.summary`
  - `cards.answer_snippet`
  - `cards.score`
  - `cards.source_type`
  - `cards.created_at`
  - `cards.category`
  - `error_code`
  - `message`

- **副作用**:
  无。

- **失败处理**:
  输入为空时返回结构化错误。没有检索结果时返回 `ok: true` 和空 `cards`，不得生成虚假结果。

#### `hybrid_search_qa_cards`

- **职责**:
  默认问答检索工具。结合 SQLite LIKE 和 Qdrant 语义召回检索本地 Q&A 知识卡片；语义索引不可用或失败时降级为 SQLite LIKE。

- **输入**:

```json
{
  "query": "用户问题或检索词，非空字符串",
  "limit": 5,
  "category": "可选；用户明确限定分类时传入"
}
```

- **输出**:

```json
{
  "ok": true,
  "cards": [
    {
      "rank": 1,
      "card_id": "卡片 ID",
      "question": "原始问题",
      "summary": "摘要",
      "answer_snippet": "答案片段",
      "score": 0.82,
      "final_score": 0.82,
      "match_level": "strong / medium / weak",
      "matched_by": ["keyword", "semantic"],
      "keyword_score": 3,
      "keyword_score_norm": 1.0,
      "semantic_score": 0.7,
      "source_type": "manual_qa",
      "created_at": "ISO 8601 时间",
      "category": "语义主归属分类"
    }
  ],
  "warning": "可选；降级或弱相关候选提示",
  "message": "可选；无足够相关候选提示"
}
```

- **可展示输入字段**:
  - `query`
  - `limit`
  - `category`

- **可展示输出字段**:
  - `ok`
  - `cards.rank`
  - `cards.card_id`
  - `cards.question`
  - `cards.summary`
  - `cards.answer_snippet`
  - `cards.score`
  - `cards.final_score`
  - `cards.match_level`
  - `cards.matched_by`
  - `cards.keyword_score`
  - `cards.keyword_score_norm`
  - `cards.semantic_score`
  - `cards.source_type`
  - `cards.created_at`
  - `cards.category`
  - `warning`
  - `message`
  - `error_code`

- **副作用**:
  检索本身无副作用。

- **失败处理**:
  输入为空时返回结构化错误。语义索引未启用或失败时返回关键词检索结果并附带 warning。没有足够相关候选时返回 `ok: true` 和空 `cards`，不得生成虚假结果。

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
    "category": "语义主归属分类",
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
  - `card.category`
  - `card.source_type`
  - `card.created_at`
  - `card.updated_at`
  - `error_code`
  - `message`

- **副作用**:
  无。

- **失败处理**:
  card_id 为空时返回结构化错误。找不到卡片时返回 `ok: false`、`error_code: "not_found"` 和 `message`，Agent 不得引用该卡片作为来源。

#### `update_qa_card`

- **职责**:
  更新一条已有 Q&A 卡片的当前内容。更新不保存历史版本；执行前必须经过 harness 权限确认。

- **输入**:

```json
{
  "card_id": "卡片 ID，非空字符串",
  "question": "可选；新的原始问题",
  "answer": "可选；新的原始答案",
  "summary": "可选；新的摘要",
  "keywords": ["可选；新的关键词列表"],
  "category": "可选；新的语义主归属分类"
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
    "category": "语义主归属分类",
    "source_type": "manual_qa",
    "created_at": "ISO 8601 时间",
    "updated_at": "ISO 8601 时间"
  }
}
```

- **可展示输入字段**:
  - `card_id`
  - `question`
  - `answer`
  - `summary`
  - `keywords`
  - `category`

- **可展示输出字段**:
  - `ok`
  - `card.card_id`
  - `card.question`
  - `card.answer`
  - `card.summary`
  - `card.keywords`
  - `card.category`
  - `card.source_type`
  - `card.created_at`
  - `card.updated_at`
  - `error_code`
  - `message`

- **副作用**:
  更新 SQLite `qa_cards` 表；内容变更后将 `is_vectorized` 重置为 `0`，并尽力同步 Qdrant 语义索引。

- **失败处理**:
  card_id 为空、没有提供任何更新字段、字段非法、category 非法或权限拒绝时返回结构化错误。找不到卡片时返回 `ok: false`、`error_code: "not_found"`。

#### `delete_qa_card`

- **职责**:
  物理删除一条 Q&A 卡片。删除不使用软删除；执行前必须经过 harness 权限确认。

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
  "deleted_card_id": "卡片 ID"
}
```

- **可展示输入字段**:
  - `card_id`

- **可展示输出字段**:
  - `ok`
  - `deleted_card_id`
  - `error_code`
  - `message`

- **副作用**:
  从 SQLite `qa_cards` 表物理删除卡片，并尽力删除 Qdrant 语义索引中的对应向量。

- **失败处理**:
  card_id 为空或权限拒绝时返回结构化错误。找不到卡片时返回 `ok: false`、`error_code: "not_found"`。

#### `list_recent_cards`

- **职责**:
  列出最近保存的 Q&A 卡片，方便用户确认本地知识库内容。

- **输入**:

```json
{
  "limit": 10,
  "category": "可选；用户明确限定分类时传入"
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
      "category": "语义主归属分类",
      "source_type": "manual_qa",
      "created_at": "ISO 8601 时间"
    }
  ]
}
```

- **可展示输入字段**:
  - `limit`
  - `category`

- **可展示输出字段**:
  - `ok`
  - `cards.card_id`
  - `cards.question`
  - `cards.summary`
  - `cards.keywords`
  - `cards.category`
  - `cards.source_type`
  - `cards.created_at`
  - `error_code`
  - `message`

- **副作用**:
  无。

- **失败处理**:
  limit 非法时使用安全默认值。数据库读取失败时返回 `ok: false`、`error_code` 和 `message`。

#### `detect_duplicate_cards`

- **职责**:
  检测疑似重复 Q&A 卡片。该工具同时支持目标卡片查重和全库查重；全库查重必须在工具内部批量完成，不得要求 Agent 逐张卡片循环调用。该工具只返回值得用户或模型继续比较的候选或候选组；低于阈值的候选直接过滤，不返回 `discard`。

- **输入**:

```json
{
  "scope": "target 或 all，默认 target",
  "card_id": "可选；要检查的已有卡片 ID",
  "query": "可选；用于查重的一段文本",
  "category": "可选；用户明确限定分类时传入",
  "limit": 20,
  "mode": "manual 或 auto"
}
```

约束：

1. `scope` 默认为 `target`。
2. `scope = "target"` 时，`card_id` 和 `query` 至少提供一个。
3. `scope = "all"` 时，工具检查本地 SQLite 中符合 category 过滤条件的全部 Q&A 卡片，不要求 `card_id` 或 `query`。
4. 用户询问本地是否有重复卡片、全库查重或检查所有卡片重复时，使用 `scope = "all"`；该路由语义属于工具定义，不写入 system prompt。
5. `mode` 默认为 `manual`。
6. `mode = "auto"` 只返回 `duplicate` 级别候选或候选组。
7. `mode = "manual"` 返回 `duplicate` 和 `possible_duplicate` 级别候选或候选组。
8. 如果提供 `card_id`，候选中必须排除该卡片自身。

- **target 输出**:

```json
{
  "ok": true,
  "scope": "target",
  "checked_card_id": "被检查的卡片 ID；query 模式下可为空",
  "candidates": [
    {
      "card_id": "候选卡片 ID",
      "question": "原始问题",
      "summary": "摘要",
      "category": "语义主归属分类",
      "duplicate_score": 0.91,
      "duplicate_level": "duplicate",
      "semantic_score": 0.89,
      "keyword_score_norm": 0.82,
      "keyword_overlap": 0.75,
      "question_overlap": 0.66,
      "same_category": true,
      "reason": "同分类，语义高度相似，关键词重合较高"
    }
  ]
}
```

- **all 输出**:

```json
{
  "ok": true,
  "scope": "all",
  "checked_count": 120,
  "duplicate_groups": [
    {
      "card_ids": ["qa_1", "qa_2"],
      "duplicate_score": 0.91,
      "duplicate_level": "duplicate",
      "reason": "同分类，问题文本和关键词高度相似",
      "cards": [
        {
          "card_id": "qa_1",
          "question": "原始问题",
          "summary": "摘要",
          "category": "语义主归属分类"
        }
      ]
    }
  ]
}
```

- **可展示输入字段**:
  - `scope`
  - `card_id`
  - `query`
  - `category`
  - `limit`
  - `mode`

- **可展示输出字段**:
  - `ok`
  - `scope`
  - `checked_card_id`
  - `checked_count`
  - `candidates.card_id`
  - `candidates.question`
  - `candidates.summary`
  - `candidates.category`
  - `candidates.duplicate_score`
  - `candidates.duplicate_level`
  - `candidates.reason`
  - `duplicate_groups.card_ids`
  - `duplicate_groups.duplicate_score`
  - `duplicate_groups.duplicate_level`
  - `duplicate_groups.reason`
  - `duplicate_groups.cards.card_id`
  - `duplicate_groups.cards.question`
  - `duplicate_groups.cards.summary`
  - `duplicate_groups.cards.category`
  - `error_code`
  - `message`

- **副作用**:
  无。

- **失败处理**:
  `scope` 非法、`scope = "target"` 时输入缺少 `card_id` 和 `query`、`card_id` 不存在、category 非法或数据库读取失败时返回结构化错误。target 查重中 Qdrant 不可用时降级为 SQLite LIKE 候选检测，并返回 warning；不得因为自动检测失败影响保存或更新成功。

#### `merge_qa_cards`

- **职责**:
  将多张 Q&A 卡片合并为一张新卡片，并物理删除原卡片。该工具只执行已经由模型生成、并由用户确认的合并草案；不得自行判断哪些卡片应该合并。

- **输入**:

```json
{
  "card_ids": ["要合并的原卡片 ID，至少 2 个"],
  "question": "合并后的原始问题，非空字符串",
  "answer": "合并后的原始答案，非空字符串",
  "summary": "合并后的摘要，非空字符串",
  "keywords": ["合并后的关键词，至少 1 个"],
  "category": "合并后的语义主归属分类，非空字符串"
}
```

- **输出**:

```json
{
  "ok": true,
  "new_card_id": "新卡片 ID",
  "deleted_card_ids": ["已物理删除的原卡片 ID"],
  "source_type": "manual_qa",
  "created_at": "ISO 8601 时间",
  "category": "语义主归属分类"
}
```

- **可展示输入字段**:
  - `card_ids`
  - `question`
  - `answer`
  - `summary`
  - `keywords`
  - `category`

- **可展示输出字段**:
  - `ok`
  - `new_card_id`
  - `deleted_card_ids`
  - `source_type`
  - `created_at`
  - `category`
  - `warning`
  - `error_code`
  - `message`

- **副作用**:
  写入一张新的 SQLite `qa_cards` 卡片，物理删除原卡片，并尽力同步 Qdrant：删除旧向量，写入新向量。

- **权限**:
  必须经过 PreToolUse permission gate。用户拒绝时不得执行任何写入或删除，并返回 `permission_denied` tool result。

- **失败处理**:
  `card_ids` 少于 2 个、任一原卡片不存在、合并后字段非法或数据库写入失败时返回结构化错误，且不得创建新卡片或删除原卡片。Qdrant 同步失败不回滚 SQLite 合并，但必须返回 warning，提示可通过 `rebuild_qa_semantic_index` 修复。

#### `rebuild_qa_semantic_index`

- **职责**:
  把尚未向量化的历史 Q&A 卡片写入 Qdrant 本地语义索引。该工具是本地维护入口，不改变 SQLite 事实内容。

- **输入**:

```json
{
  "limit": "可选；本次最多处理的未向量化卡片数"
}
```

- **输出**:

```json
{
  "ok": true,
  "status": "ok / partial_failed / disabled",
  "message": "可选；语义索引未启用时的说明",
  "total": 10,
  "indexed": 9,
  "failed": 1,
  "failed_card_ids": ["qa_..."]
}
```

- **可展示输入字段**:
  - `limit`

- **可展示输出字段**:
  - `ok`
  - `status`
  - `message`
  - `total`
  - `indexed`
  - `failed`
  - `failed_card_ids`
  - `error_code`

- **副作用**:
  写入 Qdrant 本地语义索引；单张卡片写入成功后把 SQLite `qa_cards.is_vectorized` 标记为 `1`。

- **失败处理**:
  语义索引未启用时返回 `ok: true`、`status: "disabled"` 和说明。单张卡片失败时记录到 `failed_card_ids` 并继续处理后续卡片。

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
  当前上下文压缩不是 LLM 可调用工具。`AgentLoopRunner` 在 tool result 超过阈值时，通过 `ToolResultCompactor.compact_tool_result()` 自动将原始 tool result 写入 `.sessions/<session_id>/artifacts/`，并通过 compact record 回填 tool result message 和 `context_compacted` 事件。

- **Memory candidate**:
  当前 memory candidate 不是 LLM 可调用工具，也没有写入 `.memory/*.md`、更新 `.memory/MEMORY.md` 或 pending confirmation 队列。`AgentLoopRunner` 只在 turn-end 通过 `AgentMemoryCandidateExtractor` 生成候选，并发出 `memory_candidates_generated` 事件；候选不等于已写入长期 memory。

### 3.4 v0.2-v0.7 工具演进边界

以下表格用于记录 v0.2-v0.7 的工具演进边界。其中 v0.2-v0.5 已实现的工具必须继续遵守上文当前工具契约；v0.6-v0.7 仍是后续规划，实现前必须为对应版本单独提交更细的工具契约和测试。

| 版本 | 工具 / 机制 | 职责 | 是否有副作用 | 是否需要确认 |
|---|---|---|---|---|
| `v0.2` | `turn_messages` / `source_evidence` | 从当前 turn messages 中提取真实工具证据，并由程序生成来源区块 | 否 | 否 |
| `v0.3` | `update_qa_card` | 更新 Q&A 当前卡片 | 是 | 是 |
| `v0.3` | `delete_qa_card` | 物理删除 Q&A 卡片 | 是 | 是 |
| `v0.4` | `hybrid_search_qa_cards` / `rebuild_qa_semantic_index` | 执行 SQLite LIKE + Qdrant 语义召回的混合检索；把未向量化的历史 Q&A 卡片写入 Qdrant local index | 重建和保存/更新/删除后的索引同步有副作用，检索无副作用 | 否 |
| `v0.5` | `save_qa_card` / `update_qa_card` category 扩展 | 保存时写入模型生成的 category，用户可手动更新；tags 暂不引入 | 是 | 保存否；更新沿用 `update_qa_card` 确认 |
| `v0.6` | `detect_duplicate_cards` / `merge_qa_cards` | 检测重复候选；确认后创建合并新卡片并物理删除原卡片 | 合并有副作用 | 合并需要确认 |
| `v0.7` | `extract_graph_candidates` / `confirm_graph_candidate` | 从卡片抽取实体关系候选，并在确认后写入 Kuzu | 确认写入有副作用 | 是 |
| `v0.7` | `search_graph_context` | 查询实体和关系上下文，并返回可追溯 card_id | 否 | 否 |

高风险工具必须在真正执行前经过 PreToolUse permission gate。权限结果包括 `allow`、`deny` 和 `ask`：`allow` 直接执行，`deny` 不执行并返回 `permission_denied` tool result，`ask` 由当前 Runtime 询问用户。CLI Runtime 必须提供真实用户确认；Web Runtime 必须通过 HTML 独立阻断式确认浮层等待用户确认，聊天消息流只展示轻量状态提示。用户允许后才能执行工具；用户拒绝、5 分钟确认超时、浏览器刷新或 SSE 断连时必须默认拒绝并返回 `permission_denied` tool result。工具不得接受模型自由生成的自然语言确认作为执行依据。

v0.2 实现必须保持低侵入：

1. AgentLoop 只记录当前 turn 起始位置，并向 final answer 阶段传入 `turn_messages`。
2. `source_evidence` 只能从当前 turn messages 中提取来源，不能扫描完整历史 `messages[]`。
3. 不引入长期存在的 `TurnEvidence` 状态对象。
4. 不修改 ToolCallStep、ToolDispatcher、KnowledgeTools 或 SQLite 数据模型。
5. `save_qa_card` 的 `question` 可从本轮 assistant tool call arguments 中提取；`card_id`、`source_type` 和 `created_at` 必须来自对应 tool result。
6. `search_qa_cards` 和 `read_qa_card` 的来源必须来自 `ok: true` 且字段完整的 tool result。
7. 空搜索结果、工具失败和字段不完整的结果不得作为来源。
8. 程序必须清理模型自写的“来源：”区块，并用真实工具证据重新渲染来源。
9. 普通无来源回答允许存在，但不得保留“根据本地知识库”“根据知识卡片”“根据检索结果”等无证据声明。

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
4. Agent 生成 summary、keywords 和 category。
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
2. Agent 优先调用 `hybrid_search_qa_cards` 检索本地 Q&A 卡片；必要时使用 `search_qa_cards` 作为关键词检索和降级兜底。
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
4. Agent 展示最近卡片的 card_id、原始问题、summary、keywords、category 和 created_at。

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
8. CLI Runtime 以流式增量展示 Agent 最终回答，并在最终事件到达后完成收尾。
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

### 5.5 Web 多会话持续交互

1. 用户运行 `pka web`，或使用 `python -m personal_knowledge_agent.web` 模块入口。
2. Web Runtime 调用配置加载器读取 `.env` 和环境变量。
3. Web Runtime 启动绑定在 `127.0.0.1` 的本地 HTTP 服务。
4. HTML 页面启动后请求会话列表；如果没有会话，则创建一个新 session。
5. 用户点击某个会话时，HTML 页面请求该 session 的历史消息并渲染。
6. 用户可以手动重命名当前 session；用户手动命名后自动标题不得覆盖该标题。
7. 用户在当前 session 输入 Q&A 录入请求或问题。
8. 流式聊天接口将输入交给该 session 对应的 AgentLoop，并把本轮事件实时转发给 HTML 页面。
9. AgentLoop 按 5.1 或 5.2 流程调用 LLM 和工具。
10. Web Runtime 将本轮可恢复消息写入 `.sessions/<session_id>/transcript.jsonl`。
11. HTML 页面实时展示调用流程和最终回答增量，并以 `final_answer_generated` 作为权威最终答案。

- **成功条件**:  
  用户无需使用 CLI，即可在本地浏览器中创建多个会话、切换会话、重命名会话、连续录入知识和提问；点击某个会话后能看到该会话历史聊天记录。

- **失败条件**:  
  `.env` 或环境变量缺少 `DEEPSEEK_API_KEY`，DeepSeek / SQLite 初始化失败，本地端口不可用，静态页面加载失败，session_id 非法，session 不存在，历史消息读取失败，或单轮 AgentLoop 执行失败。

- **用户可见反馈**:  
  启动失败时输出明确错误；运行中模型或工具失败时，流式接口返回结构化错误事件，HTML 展示本轮失败说明。不得声称保存、查询或回答成功。

### 5.6 Web 会话列表和历史恢复

1. HTML 页面请求 `GET /api/sessions`。
2. Web API 读取 `.sessions/*/metadata.json`，按 `updated_at` 倒序返回 session 列表。
3. 如果不存在任何 session，HTML 页面请求 `POST /api/sessions` 创建新 session。
4. 用户点击某个 session，HTML 页面请求 `GET /api/sessions/{session_id}/messages`。
5. Web API 从 `.sessions/<session_id>/transcript.jsonl` 派生用户可见消息。
6. HTML 页面清空当前聊天区并渲染该 session 的 user / assistant 历史消息。
7. 浏览器刷新时，HTML 页面优先恢复上次选中的 session_id；如果该 session 不存在，则选择最近更新 session。

- **成功条件**:  
  Web UI 展示可切换的会话列表；点击会话能展示该会话历史 user / assistant 聊天记录；刷新页面后能恢复当前会话的可见历史。

- **失败条件**:  
  session_id 非法，metadata 不存在，transcript 读取失败，metadata 格式非法，或历史消息中缺少可展示字段。

- **用户可见反馈**:  
  无会话时显示空状态并允许创建会话；历史为空时显示空聊天区；读取失败时展示结构化错误，不伪造历史消息。

### 5.7 Web 知识卡片浏览

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

### 5.8 CLI 实时运行过程展示

1. CLI Runtime 收到用户输入后生成本轮 `run_id`。
2. Agent Loop 在收到输入、调用 LLM、收到最终回答文本增量、收到 LLM 响应、调用工具、收到工具结果、判断证据和生成最终回答时产生结构化事件。
3. CLI Renderer 在主线程实时渲染事件。
4. Async JSONL Logger 在后台线程异步写入本地 `.logs/agent.log`，但默认跳过 token 级 `answer_delta` 事件。
5. 最终回答仍必须符合来源要求；依据不足时仍必须明确拒答。

- **成功条件**:  
  用户能在 CLI 中实时看到 LLM 阶段、tool call、tool result、证据判断和最终回答增量；本地 JSONL 日志能记录除 `answer_delta` 以外的审计事件和完整最终回答。

- **失败条件**:  
  CLI Renderer 渲染失败、日志队列满、日志写入失败或日志 flush 超时。

- **用户可见反馈**:  
  CLI Renderer 或 Logger 失败时向 stderr 输出简短提示，但不得影响 Agent 工具执行和最终回答。

### 5.9 Turn-start 上下文准备

1. CLI Runtime 选择或创建默认 session：`.sessions/default/`；Web Runtime 根据当前 `session_id` 选择或创建对应 session。
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

### 5.10 上下文压缩

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

### 5.11 v0.3 PreToolUse 权限确认

1. 模型在 LLM 响应中请求调用工具。
2. AgentLoop 将 tool call 交给 ToolCallStep。
3. ToolCallStep 在执行工具 handler 前调用 permission checker。
4. 如果权限结果是 `allow`，ToolCallStep 执行 ToolDispatcher。
5. 如果权限结果是 `deny`，ToolCallStep 不执行工具，并返回 `permission_denied` tool result。
6. 如果权限结果是 `ask`，ToolCallStep 构造 ApprovalRequest 并调用当前 Runtime 注入的 approval callback。
7. CLI Runtime 的 approval callback 必须向用户展示工具名、参数摘要和原因，并要求用户输入明确允许词。
8. 用户允许时，ToolCallStep 执行 ToolDispatcher。
9. 用户拒绝时，ToolCallStep 不执行工具，并返回 `permission_denied` tool result。
10. permission_denied 仍必须作为 tool_result 回填给模型，让模型知道该操作没有执行。

- **成功条件**:
  高风险工具只有在 Runtime 用户确认后才真正执行；普通安全工具不触发用户确认。

- **失败条件**:
  用户拒绝、Runtime 没有确认 UI、权限规则明确拒绝或 approval callback 抛错。

- **用户可见反馈**:
  CLI 应展示高风险工具请求和确认提示；拒绝后 Agent 应说明操作未执行。Web 应通过独立阻断式确认浮层展示后端生成的工具摘要、目标、变更字段和风险说明，聊天消息流只展示待确认和确认结果状态；用户允许后继续执行，拒绝、5 分钟超时、浏览器刷新或 SSE 断连时不执行工具。

### 5.12 v0.4 Hybrid 检索

1. Agent 对本地 Q&A 问答意图优先调用 `hybrid_search_qa_cards`。
2. 工具先执行 SQLite LIKE，得到 keyword candidates。
3. 如果缺少 `DASHSCOPE_API_KEY`，工具直接返回 SQLite LIKE 结果，并附带语义检索未启用的 warning。
4. 如果 embedding 已启用，工具调用 DashScope / Qwen `text-embedding-v4`，把用户 query 转换为 query vector。
5. 工具调用 Qdrant local index，得到 semantic candidates。
6. 工具将两路结果统一为 SearchCandidate，并按 card_id 合并去重。
7. 工具为每个候选计算 `keyword_score`、`keyword_score_norm`、`semantic_score` 和 `final_score`。
8. 工具按 `final_score` 降序排序，返回候选摘要，不返回完整 answer。
9. 工具返回统一候选结果；Qdrant / DashScope 失败时降级为 SQLite LIKE，并返回 warning。

v0.4 hybrid 排序规则：

1. `keyword_score` 来自 SQLite LIKE 字段权重。
2. `semantic_score` 来自 Qdrant 相似度。
3. `keyword_score_norm = keyword_score / max_keyword_score`。
4. 如果本轮没有关键词命中，则 `keyword_score_norm = 0`。
5. `final_score = 0.4 * keyword_score_norm + 0.6 * semantic_score`。
6. 返回候选必须按 `final_score` 降序排序。

v0.4 hybrid 候选分层：

1. `strong`: `final_score >= 0.70`。
2. `medium`: `0.50 <= final_score < 0.70`。
3. `weak`: `0.35 <= final_score < 0.50`。
4. `discard`: `final_score < 0.35`。

v0.4 hybrid 返回规则：

1. 如果存在 `strong` 或 `medium` 候选，返回这些候选，最多 `limit` 条。
2. 如果不存在 `strong` / `medium`，但存在 `weak` 候选，只返回 top weak 1 条，并附带 warning。
3. 如果没有 `weak` 以上候选，返回 `cards = []`，并附带 message。
4. 每个候选应包含 `rank`、`match_level`、`matched_by`、`keyword_score`、`keyword_score_norm`、`semantic_score`、`final_score` 和兼容字段 `score`。

v0.4 hybrid 候选使用规则：

1. `hybrid_search_qa_cards` 是候选召回工具，不是完整依据读取工具。
2. `read_qa_card` 是完整卡片依据读取工具。
3. 如果要基于某张候选卡片回答本地知识库问题，必须先调用 `read_qa_card` 读取该 `card_id` 的完整卡片。
4. 通常应优先读取 `rank = 1` 的候选。
5. 如果跳过 `rank = 1` 读取更低 rank 候选，必须有明确理由，例如 `rank = 1` 与用户问题明显不匹配。
6. 如果 `hybrid_search_qa_cards` 只返回 weak 候选，必须读取完整卡片后再判断是否足够回答；不足时应说明本地知识库依据不足。
7. 如果 `hybrid_search_qa_cards` 返回空 `cards`，不得声称来自本地知识库。

首次启用 v0.4 后，已有 SQLite 历史卡片不会自动假定已进入 Qdrant。工具层必须提供 `rebuild_qa_semantic_index`：

1. 从 SQLite 读取 `is_vectorized = 0` 的 Q&A 卡片。
2. 对每张卡片生成 embedding，并写入 Qdrant local index。
3. 单张卡片写入成功后，将该卡片 `is_vectorized` 标记为 `1`。
4. 单张卡片失败时保持 `is_vectorized = 0`，本次重建继续处理后续卡片。
5. 已经 `is_vectorized = 1` 且未被更新的卡片不得重复向量化。

- **成功条件**:
  hybrid 检索返回候选均可回溯到 SQLite `qa_cards`。历史卡片通过 `rebuild_qa_semantic_index` 成功进入 Qdrant 后，后续可被语义召回命中。

- **失败条件**:
  SQLite 读取失败、DashScope 失败、Qdrant 失败、缺少 `DASHSCOPE_API_KEY` 或 Qdrant 返回已不存在的 card_id。

- **用户可见反馈**:
  hybrid 完整成功时返回候选结果和评分解释字段；向量部分未启用或失败时说明已降级为本地关键词检索。`rebuild_qa_semantic_index` 返回处理总数、成功数量、失败数量和失败 card_id 列表。不得把 Qdrant payload 或 hybrid 候选摘要当作完整事实来源。

### 5.13 v0.5 category

1. 用户录入 Q&A。
2. 模型生成 summary、keywords 和 category。
3. `save_qa_card` 将 category 随 Q&A 卡片写入 SQLite。
4. 用户后续可以通过 `update_qa_card` 手动修改 category；该操作沿用 `update_qa_card` 现有权限确认规则。
5. v0.5 不新增 tags；keywords 继续作为检索词，category 表示卡片的语义主归属分类。
6. category 是必填结构字段，不允许为空，不允许使用兜底分类。
7. 历史卡片必须通过 `scripts/backfill-qa-categories.py` 调用当前 DeepSeek LLM 生成 category，不得默认写入“其他”。

category 生成规则：

1. category 只能有一个。
2. category 必须是 1-24 个字符的短名词短语。
3. category 不允许为空。
4. category 不允许为“其他”“未分类”“杂项”“默认分类”“未知”“待分类”。
5. category 不得是函数名、字段名、模型名、数据库名、工具名或 API 名。
6. 具体技术实体、函数名、字段名和英文术语应进入 keywords，而不是 category。
7. 不确定时也必须选择最接近的具体稳定主题分类。
8. 生成时优先复用已有分类或以下推荐方向：Agent 开发、LLM 基础、工具调用、上下文管理、Prompt 工程、检索与知识库、向量检索、知识治理、数据存储、AI 编程经验、工程架构、调试排错、开发工具、框架选型、权限机制、项目使用说明。

category 搜索规则：

1. 保存时 category 必填。
2. 更新时 category 可选。
3. 搜索时 category 是可选参数。
4. 只有用户明确限定分类时，模型才给 `search_qa_cards`、`hybrid_search_qa_cards` 或 `list_recent_cards` 传 category。
5. 用户未明确限定分类时，不传 category，执行全库搜索。
6. 一旦传了 category，它就是硬过滤条件。
7. 指定 category 下无结果时，不跨分类兜底。
8. `hybrid_search_qa_cards` 不把 category 写入 Qdrant payload；Qdrant 仍按 query 召回，最终通过 SQLite 回源应用 category 精确过滤。

历史 backfill 规则：

1. `scripts/backfill-qa-categories.py` 不是 Agent 工具，只能作为本地维护脚本执行。
2. 脚本读取 category 为空的历史卡片，调用当前 DeepSeek LLM 生成 category。
3. 任意历史卡片生成失败或 category 非法时，脚本停止，不重建约束表。
4. 全部历史卡片 category 合法后，脚本重建 `qa_cards` 表并加 `NOT NULL` + `CHECK` 约束。

- **成功条件**:
  卡片读回时包含 category；搜索和列表可按 category 精确过滤；SQLite 和工具层都能拒绝非法 category。

- **失败条件**:
  category 为空、超过长度限制、属于兜底词、使用函数名/字段名/模型名/数据库名/工具名/API 名，或历史 backfill 失败。

- **用户可见反馈**:
  保存或更新后展示当前 category；指定 category 搜索为空时说明该分类下没有找到相关本地知识卡片。

### 5.14 v0.6 去重和合并

v0.6 只实现轻量 Record Linkage 流程：疑似重复检测和用户确认合并。全库查重是用户显式触发的一次只读工具调用，不是后台扫描或定时任务。不得实现自动合并、后台定时扫描、复杂审计表、历史版本表、LLM-as-judge 或 Web UI 合并入口。

显式触发流程：

1. 用户明确表达查重、重复、相似、整理或合并意图。
2. 如果用户询问本地是否有重复卡片、全库查重或检查所有卡片重复，Agent 调用 `detect_duplicate_cards(scope="all", mode="manual")`，不得通过 `list_recent_cards` 后逐张 `card_id` 调用查重工具来模拟全库查重。
3. 如果用户指定某张卡片或提供一段待查文本，Agent 调用 `detect_duplicate_cards(scope="target", card_id=..., mode="manual")` 或 `detect_duplicate_cards(scope="target", query=..., mode="manual")`。
4. `scope="all"` 时，工具从 SQLite 读取符合 category 过滤条件的全部卡片，基于本地字段召回候选 pair，对 pair 做轻量 scoring，并用 connected components 将相关 pair 合并为 `duplicate_groups`。
5. `scope="target"` 时，工具基于 SQLite LIKE 和 Qdrant 召回候选，排除目标卡片自身，并按 card_id 合并去重。
6. 工具只返回 `duplicate` 和 `possible_duplicate` 候选或候选组；低于阈值的候选直接过滤，不返回 `discard`。
7. Agent 向用户展示候选组或候选、差异和原因。
8. 用户明确要求合并后，模型生成合并后的新 question、answer、summary、keywords 和 category。
9. 模型请求调用 `merge_qa_cards`。
10. `merge_qa_cards` 进入 PreToolUse permission gate。
11. 用户允许后，工具创建新卡片，物理删除原卡片，并尽力同步 Qdrant。
12. 用户拒绝时，不执行合并，并返回 `permission_denied` tool result。

自动触发流程：

1. `save_qa_card` 或 `update_qa_card` 成功后，Agent 可以调用 `detect_duplicate_cards(scope="target", card_id=..., mode="auto")`。
2. 自动检测只调用只读检测工具，不得调用 `merge_qa_cards`。
3. 自动检测只返回 `duplicate` 候选；没有 `duplicate` 候选时不提示用户。
4. 自动检测失败不得影响保存或更新成功。
5. 发现 `duplicate` 候选时，只提示用户是否展开对比并生成合并草案。

初始分层规则：

1. `duplicate`: 同 category 且 `semantic_score >= 0.88`，或同 category 且 `duplicate_score >= 0.82`。
2. `possible_duplicate`: 同 category 且 `duplicate_score >= 0.70`，或同 category 且 `keyword_score_norm >= 0.85` 且 `keyword_overlap >= 0.5`，或跨 category 且 `semantic_score >= 0.93`。
3. 低于 `possible_duplicate` 的候选直接过滤，不进入工具输出。

- **成功条件**:
  `detect_duplicate_cards` 返回的候选和候选组均可回读到 SQLite 卡片，且不包含低于阈值的 `discard` 候选；全库查重通过一次工具调用返回 `checked_count` 和 `duplicate_groups`；`merge_qa_cards` 成功时新卡片创建成功，原卡片物理删除，检索结果不再返回原卡片。

- **失败条件**:
  用户拒绝、目标卡片不存在、候选卡片不存在、新卡片字段非法、数据库写入失败或 Qdrant 同步失败。

- **用户可见反馈**:
  检测到疑似重复时展示候选、`duplicate_level` 和原因；无候选时说明没有发现明显重复。合并成功时展示新 card_id 和已删除的原 card_id；Qdrant 同步失败时提示可通过 rebuild 修复。

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
| `category` | `TEXT` | 是 | 模型生成或用户手动更新的单个语义主归属分类 |
| `source_type` | `TEXT` | 是 | 第一版固定为 `manual_qa` |
| `created_at` | `TEXT` | 是 | 系统生成的 ISO 8601 创建时间 |
| `updated_at` | `TEXT` | 是 | 系统生成的 ISO 8601 更新时间 |
| `is_vectorized` | `INTEGER` | 是 | `0` 表示尚未向量化或内容更新后需重新向量化；`1` 表示已成功写入 Qdrant |

建表 SQL：

```sql
CREATE TABLE IF NOT EXISTS qa_cards (
  id TEXT PRIMARY KEY,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  summary TEXT NOT NULL,
  keywords TEXT NOT NULL,
  category TEXT NOT NULL CHECK (
    length(trim(category)) BETWEEN 1 AND 24
    AND category NOT IN ('其他', '未分类', '杂项', '默认分类', '未知', '待分类')
  ),
  source_type TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  is_vectorized INTEGER NOT NULL DEFAULT 0
);
```

### 6.2 数据约束

1. `id` 必须由工具或 Store 生成，模型不得自称某个未落库 ID 已存在。
2. `question`、`answer`、`summary` 不得为空。
3. `keywords` 在工具输入中是字符串数组，入库时序列化为 JSON 字符串。
4. `category` 必须是 1-24 个字符的具体稳定短名词短语，不得为空，不得使用兜底分类：`其他`、`未分类`、`杂项`、`默认分类`、`未知`、`待分类`。
5. `source_type` 第一版固定为 `manual_qa`。
6. `created_at` 和 `updated_at` 必须由系统生成。
7. 新建卡片默认 `is_vectorized = 0`；更新卡片内容时必须重置为 `0`；成功写入 Qdrant 后才能标记为 `1`。
8. DeepSeek API key 不得写入数据库、代码、文档或日志。

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

`session_id` 必须只包含 ASCII 字母、数字、下划线和连字符，长度必须在 1 到 64 之间。任何包含路径分隔符、`.`、空白字符或其他字符的 session_id 都必须被拒绝。

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

Web 历史消息 API 必须从 transcript 派生用户可见消息：

| 派生字段 | 类型 | 说明 |
|---|---|---|
| `role` | `TEXT` | 仅允许 `user` 或 `assistant` |
| `content` | `TEXT` | user 原始输入或 assistant 最终回答文本 |
| `created_at` | `TEXT` | 来源 transcript event 创建时间 |
| `event_id` | `INTEGER` | 来源 transcript event_id |

Web 历史消息不得返回 assistant tool call、tool result、system prompt、完整 LLM messages、API key、secret 或未声明为可展示的内部 payload。

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
  "title": "SQLite 检索问题",
  "title_source": "auto",
  "last_user_message": "SQLite LIKE 检索怎么做？",
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

`title_source` 只允许 `auto` 或 `user`。新建空会话的默认标题为 `新会话`，`title_source` 为 `auto`。当用户发送第一条或后续用户消息时，如果 `title_source` 仍为 `auto`，Runtime 可以用用户消息前 30 个字符生成标题；如果用户已手动重命名，Runtime 不得自动覆盖标题。

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

### 6.10 v0.2-v0.7 规划数据模型

以下模型仅记录后续版本的数据边界，当前代码尚未实现。实现时必须保持 SQLite 事实源优先，外部索引和图谱只保存可回查的 `card_id` 或轻量 payload。

- **v0.2 Source Evidence**:
  - `card_id`
  - `question`
  - `source_type`
  - `created_at`
  - `evidence_kind`: `saved`、`searched` 或 `read`

- **v0.3 Permission Request**:
  - `tool_name`
  - `arguments`
  - `reason`
  - `behavior`: `allow`、`deny` 或 `ask`

- **v0.4 Qdrant Point**:
  - `id`: 与 `card_id` 稳定关联
  - `vector`: DashScope / Qwen `text-embedding-v4` 生成的 `1024` 维向量
  - `payload.card_id`

- **v0.4 `qa_cards` semantic index marker**:
  - `is_vectorized`: `0` 表示尚未向量化，或内容更新后需要重新向量化；`1` 表示已成功向量化并写入 Qdrant。
  - 新卡片默认 `is_vectorized = 0`。
  - 更新卡片内容时必须把 `is_vectorized` 重置为 `0`。
  - 成功写入 Qdrant 后才能把 `is_vectorized` 标记为 `1`。

- **v0.5 `qa_cards` category 扩展**:
  - `category`: `TEXT NOT NULL`，保存模型生成或用户手动更新的单个语义主归属分类。
  - 数据库必须通过 `CHECK` 约束拒绝空 category 和兜底分类：`其他`、`未分类`、`杂项`、`默认分类`、`未知`、`待分类`。

- **v0.6 Duplicate / Merge**:
  - `duplicate_candidates`: 运行时结构，不入库。
  - `merge_qa_cards` 输入必须包含模型生成的新 question、answer、summary、keywords 和 category。
  - 合并成功后创建新卡片，物理删除原卡片，并尽力同步 Qdrant。

- **v0.7 Kuzu Graph**:
  - `Entity`
  - `Relation`
  - `CardSource`
  - 实体和关系必须能通过 `CardSource.card_id` 回到 SQLite Q&A 卡片。

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
| 高风险工具需确认 | 权限结果为 `ask` | Runtime 询问用户；允许才执行 | 展示工具名、参数摘要和风险原因 |
| 用户拒绝高风险工具 | approval callback 返回 false | 不执行工具，返回 `permission_denied` tool result | 说明操作未执行 |
| Web 高风险工具请求 | Web Runtime 遇到 `ask` 权限 | 通过流式事件触发独立阻断式确认浮层；允许后执行，拒绝、5 分钟超时、浏览器刷新或 SSE 断连时返回 `permission_denied` | HTML 确认浮层展示待确认操作，聊天消息流展示轻量状态，并在未执行时说明操作未执行 |
| CLI 输入为空 | 用户直接回车 | 不调用 AgentLoop | 继续等待输入 |
| CLI 退出 | 用户输入 `/exit` 或 `/quit` | 正常结束循环 | 输出退出提示 |
| CLI Renderer 失败 | 渲染事件时发生异常 | 不影响工具执行和 Agent 最终回答 | 向 stderr 输出简短错误 |
| Web 服务启动失败 | 端口不可用、配置缺失或 Web app 初始化失败 | 不启动 Web Runtime，不创建虚假会话 | 输出明确启动失败原因 |
| Web session_id 非法 | session_id 为空、过长或包含非法字符 / 路径穿越字符 | 不创建或读取 session | HTML 展示 session 无效 |
| Web session 不存在 | 用户请求不存在的 session 历史 | 不伪造会话或历史消息 | HTML 展示 session 不存在并可重新选择 |
| Web session 历史读取失败 | transcript 不存在、格式非法或不可读 | 不伪造历史消息 | HTML 展示历史读取失败 |
| Web session 重命名失败 | 标题为空、过长或 metadata 无法写入 | 不声称重命名成功 | HTML 展示重命名失败原因 |
| Web chat 执行失败 | 流式聊天接口调用 AgentLoop 失败 | 返回结构化错误事件，不声称本轮完成 | HTML 展示本轮失败说明 |
| 流式回答最终修正 | `final_answer_generated` 与已展示的 `answer_delta` 累计文本不一致 | 以 `final_answer_generated` 为权威最终答案，只做一次正文节点修正 | HTML / CLI 不反复重绘，不伪造未校验证据 |
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
  8. `answer_delta` 只服务实时 UI 展示，默认不写入 JSONL 开发日志；完整最终答案由 `final_answer_generated` 记录。

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
  6. Web 历史消息恢复只影响 UI 展示，不得改变 Q&A 来源判断。
  7. Web 历史消息读取失败不得被解释为本地知识库缺少依据。

- **Memory candidate 降级原则**:
  1. 当前实现只生成 memory candidate 事件，不自动写入长期 memory。
  2. 候选生成失败不得阻断 Q&A 保存、检索和回答主流程。
  3. 模型推测、临时讨论、敏感信息和过期任务状态不得被声称为已写入长期 memory。

---

## 8. 测试要求

- **单元测试**:
  1. `QACardRepository.save_card` 能写入并读回 Q&A 卡片。
  2. `QACardRepository.search_cards` 能按 question、answer、summary、keywords 的 LIKE 命中返回结果。
  3. `QACardRepository.list_recent_cards` 能按 created_at 倒序返回。
  4. `QAKnowledgeToolHandlers.save_qa_card` 能校验必填字段。
  5. `QAKnowledgeToolHandlers.read_qa_card` 对不存在 ID 返回结构化 not_found。
  6. `AgentMemoryToolHandlers` 能独立读取 memory index 和 memory 全文。
  7. `DeepSeekChatClient` streaming 请求构造、文本增量回调、tool call 分片聚合和响应解析使用 mock 测试。
  8. `DeepSeekChatClient` 能对可重试网络错误和 HTTP 429、500、503 执行有限重试。
  9. `DeepSeekChatClient` 对 HTTP 400、401、402、422 不重试。
  9a. `DeepSeekChatClient` 重试耗尽时返回明确错误且不泄露 API key、headers、完整 payload 或 system prompt。
  10. `load_config` 能从 `.env` / 环境变量读取 `DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL` 和 `KNOWLEDGE_DB_PATH`。
  11. 缺少 `DEEPSEEK_API_KEY` 时返回明确错误。
  12. `AgentMemoryIndexRepository` 能读取 `.memory/MEMORY.md` 索引。
  13. `AgentMemoryIndexRepository` 对缺少必填列或非法 type 返回结构化错误。
  14. `AgentMemoryDocumentRepository` 能读取合法 `.memory/*.md`。
  15. `AgentMemoryDocumentRepository` 对 frontmatter 缺失或非法 type 返回结构化错误。
  16. `ConversationTranscriptRepository` 能追加和读取 `.sessions/<session_id>/transcript.jsonl`。
  16a. `ConversationTranscriptRepository` 拒绝非法 session_id。
  16b. `ConversationTranscriptRepository` 能从 transcript 派生 Web 可展示历史消息，并过滤 tool result 与内部 payload。
  17. `ConversationSessionMetadataRepository` 能创建、读取和更新 `.sessions/<session_id>/metadata.json`。
  17a. `ConversationSessionMetadataRepository` 能列出 `.sessions/*/metadata.json`，并按 updated_at 倒序返回。
  17b. `ConversationSessionMetadataRepository` 能重命名 session，并防止自动标题覆盖用户标题。
  18. `ConversationSessionRestorer` 能短 transcript 原样恢复 messages。
  19. `ConversationSessionRestorer` 能长 transcript 使用 summary + recent messages 恢复。
  20. summarizer 失败时能使用 first N + recovery notice + recent N 降级恢复。
  21. `ToolResultCompactor` 对超过阈值的大输出生成 compact record。
  22. compact record 必须包含 artifact_path、summary、relevance 和 must_keep。
  23. `AgentMemoryCandidateExtractor` 只生成候选，不直接写入长期 memory。
  24. user / feedback candidate 默认不自动写入长期 memory。
  25. `agent_component_factory.py` 能创建 `AgentLoopRunner` 及其依赖，并可被 CLI Runtime 和 Web Runtime 复用。
  26. `agent_component_factory.py` 支持指定 session_id 创建 `AgentLoopRunner`。

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
  20. Web Runtime 能用 fake AgentLoop 处理一次流式聊天请求。
  21. Web Runtime 能创建 session、列出 session、重命名 session、读取 session 历史消息。
  22. Web Runtime 能按 session_id 隔离多会话聊天上下文和事件队列。
  23. Web Runtime 对同一 session 串行执行聊天请求。
  24. Web Runtime 能返回最近卡片、搜索卡片和卡片详情的结构化结果。
  25. Web Runtime 在 AgentLoop、session 读取或卡片读取失败时返回结构化错误。
  26. CLI Runtime 不把 `answer_delta` 写入 JSONL 开发日志，但仍记录 `final_answer_generated`。

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
  15. 高风险工具被用户拒绝时不得执行 handler。
  16. 高风险工具被用户允许时才执行 handler。
  17. 普通工具不得触发 approval callback。
  18. Web Runtime 遇到高风险工具 ask 时不得阻塞等待终端输入，必须通过 Web 独立阻断式确认浮层获取用户决定。
  18a. Web Runtime 高风险工具确认超时、浏览器刷新或 SSE 断连时不得执行 handler，必须返回 `permission_denied` tool result。
  18b. Web UI 的高风险工具确认浮层不得展示完整 tool arguments，只能展示后端生成的摘要；长文本必须截断或省略，避免破坏聊天布局。
  19. Web Runtime 不保留非流式 `/api/chat` 聊天路径。
  20. Web Runtime 不把 `answer_delta` 缓存到全局事件列表。
  21. 多个 Web session 不得共享 runtime `messages[]`。
  22. Web 历史消息 API 不得返回 tool result、assistant tool call、system prompt 或完整内部 payload。

- **可选 Live Smoke Test**:
  1. 仅在存在 `DEEPSEEK_API_KEY` 时运行。
  2. 使用 `deepseek-v4-flash` 做真实 DeepSeek 调用。
  3. 完成一次保存 Q&A。
  4. 再完成一次检索回答。
  5. 启动 `pka web` 并在浏览器完成一次聊天、最近卡片刷新、搜索和详情查看。
  6. 不把 API key 写入仓库或日志。
  7. CLI / Web 最终回答能展示真实 DeepSeek streaming 文本增量。

- **验收清单**:
  1. 符合本文档定义的能力边界。
  2. SQLite `qa_cards` 是 Q&A 知识库唯一长期记忆来源。
  3. 当前 LLM 可调用工具契约稳定可测。
  4. DeepSeek 只出现在薄 LLM Client 中。
  5. Q&A 知识库和 Agent memory 保持分离。
  6. `.memory/*.md` 是用户可见的 Agent 长期工作记忆来源。
  7. `.sessions/<session_id>/transcript.jsonl` 能恢复 runtime `messages[]`。
  8. `.sessions/<session_id>/summary.md` 只保存长 transcript 的 compact summary。
  9. compact 只缩减上下文窗口，不替代长期 memory。
  10. Web Runtime 只作为本地 Chat + Cards 入口，不改变 Agent 的工具和记忆边界。
  11. Web 聊天只暴露流式接口，流程展示和回答增量不绕过 AgentLoop。
  12. 第一版不包含 Wiki、文件监听、周报、多 Agent、外部知识库和后台任务；Qdrant 仅作为 Q&A 语义索引，不是事实源。

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
| `2026-06-13` | 补充 DeepSeek streaming、`answer_delta`、Web 流式聊天接口和日志过滤边界 | 支持本地 Codex 风格实时流程展示和最终回答真流式输出 | `TBD` |
| `2026-06-16` | 明确 Agent 开发上下文只记录稳定设计边界，不记录任务计划 | 区分 Agent 设计约束与 AI Coding 协作过程 | `TBD` |
| `2026-06-16` | 更新源码模块路径、正式实现名称和独立 tool handler 边界 | 完成架构目录迁移第二阶段前锁定实现边界 | `TBD` |
| `2026-06-20` | 扩展 `detect_duplicate_cards` 支持 `scope=all` 全库查重 | 避免 Agent 逐张卡片循环调用查重工具，锁定一次工具调用完成全库重复检测的契约 | `TBD` |
