---
module: "local-qa-knowledge-agent"
title: "本地个人 Q&A 知识库"
language: "Python"
agent_type: "Tool-Using Agent / RAG Agent"
last_updated: "2026-05-31"
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
  6. 能维护当前任务的 session memory，用于在上下文压缩后延续任务状态。
  7. 能对过大的上下文材料做 compact，保留摘要、相关性说明和可回读 artifact。

- **包含能力**:
  1. 录入用户提供的 Q&A。
  2. 由模型生成 summary 和 keywords。
  3. 通过工具保存 Q&A 卡片到 SQLite。
  4. 通过工具检索、读取和列出 Q&A 卡片。
  5. 基于检索结果组织回答。
  6. 回答时展示 card_id、原始问题、source_type 和 created_at。
  7. 读取 `.memory/MEMORY.md` 中的 Agent memory index。
  8. 按需读取少量相关 `.memory/*.md`，用于指导 Agent 协作行为。
  9. 读取和更新 `.session/current.md`，用于保存当前任务状态。
  10. 将过大的 tool result 写入 `.session/artifacts/`，并在上下文中保留 compact record。
  11. 在 turn 结束后提取 memory candidates，并按写入规则保存或等待用户确认。

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

- **行为约束**:
  1. 凡是涉及长期记忆的动作，必须通过工具完成。
  2. Agent 不得声称已经保存、查询或更新实际未通过工具完成的数据。
  3. 回答问题前必须先检索本地知识库。
  4. 没有足够依据时必须明确说明本地知识库中没有找到足够依据。
  5. 回答不得引入无来源外部知识。
  6. Q&A 知识库和 Agent memory 必须分开。
  7. `.memory/*.md` 用于 Agent 长期工作记忆，不得作为 Q&A 回答的知识卡片来源。
  8. `.session/current.md` 只表示当前任务状态，不得当作长期事实来源。
  9. compact 只能缩减当前上下文窗口，不得替代长期记忆写入。
  10. memory candidate 写入必须遵守确认规则，不得把模型推测直接写成长期事实。

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
  - 提供 memory candidate 的写入入口，并按写入规则处理确认要求。
  - 不直接回答用户知识问题。
  - 不把 Agent memory 写入 SQLite `qa_cards` 表。

- **Session Manager 职责**:
  - 读取和更新 `.session/current.md`。
  - 保存当前任务目标、已确认决策、开放问题和下一步。
  - 为 turn-start memory 选择提供当前任务状态。
  - 不把 session summary 当作长期记忆。
  - 不把 session summary 作为 Q&A 回答来源。

- **Context Compactor 职责**:
  - 识别过大的 tool result 或旧上下文。
  - 将原始大输出写入 `.session/artifacts/`。
  - 在上下文中保留 compact record，包括 `artifact_path`、`summary`、`relevance` 和 `must_keep`。
  - compact 失败时保留原始上下文或降级为不压缩。
  - 不删除可回读 artifact，除非用户明确要求清理。

- **Memory Extractor 职责**:
  - 在 turn 结束后从 recent dialogue、tool result summaries、session summary 和 memory index 中提取 memory candidates。
  - 输出结构化候选，不直接绕过写入规则。
  - 只提取稳定偏好、明确约束、项目事实、长期反馈和可复用引用。
  - 不提取临时闲聊、敏感信息、模型猜测或已经过期的任务状态作为长期 memory。

- **LLM Client 职责**:
  - 作为 DeepSeek API 的薄适配层。
  - 接收 messages、tools 和 system_prompt。
  - 发起 DeepSeek chat 请求。
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
  - 不直接操作 SQLite。
  - 不绕过 AgentLoop 调用工具。

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
  - 调用 Memory Manager、Session Manager 和 Context Compactor 完成 Agent memory、session memory 和 compact artifact 相关操作。
  - 将成功、失败和未找到结果统一转换为结构化 tool result。

- **Services / Repositories 职责**:
  - 第一版 Q&A 知识库不单独拆分 Service / Repository。
  - `SQLiteStore` 负责数据库初始化、保存、读取、LIKE 检索和最近列表。
  - `SQLiteStore` 不调用 LLM，不组织最终自然语言回答。
  - `MemoryStore` 负责 `.memory/*.md` 的读写、frontmatter 解析和内容校验。
  - `MemoryIndex` 负责 `.memory/MEMORY.md` 的读取、校验和更新。
  - `SessionStore` 负责 `.session/current.md` 和 `.session/artifacts/` 的读写。

- **Storage / External API 职责**:
  - SQLite `qa_cards` 是第一版 Q&A 知识库的唯一长期记忆来源。
  - `.memory/*.md` 是 Agent 长期工作记忆来源。
  - `.memory/MEMORY.md` 是 Agent memory index，只保存 name、type、description 和 path。
  - `.session/current.md` 是当前任务状态来源，不是长期事实来源。
  - `.session/artifacts/` 保存 compact 后可回读的大输出，不是长期事实来源。
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
  5. Agent Loop 不得直接读写 `.memory/` 或 `.session/`。
  6. `.memory/*.md` 不得作为 Q&A 知识库来源。
  7. `.session/current.md` 不得作为长期事实来源。
  8. 未在本文档声明的核心依赖不得擅自引入。

- **核心文件 / 目录**:

| 路径 | 职责 |
|---|---|
| `pyproject.toml` | 声明项目依赖和 `pka` CLI script |
| `src/personal_knowledge_agent/agent_loop.py` | Agent 最小循环 |
| `src/personal_knowledge_agent/events.py` | Agent run 结构化事件契约 |
| `src/personal_knowledge_agent/cli_renderer.py` | CLI 实时事件渲染 |
| `src/personal_knowledge_agent/jsonl_logger.py` | 异步 JSONL 开发日志 |
| `src/personal_knowledge_agent/prompt_builder.py` | 构建运行时 system prompt |
| `src/personal_knowledge_agent/llm_client.py` | DeepSeek 薄客户端 |
| `src/personal_knowledge_agent/config.py` | 读取 `.env` 和环境变量，返回运行配置 |
| `src/personal_knowledge_agent/__main__.py` | CLI 持续交互入口，供 `python -m personal_knowledge_agent` 和 `pka` 复用 |
| `src/personal_knowledge_agent/tool_dispatcher.py` | 工具分发和错误包装 |
| `src/personal_knowledge_agent/tools.py` | 四个知识库工具 |
| `src/personal_knowledge_agent/memory_store.py` | 读写 `.memory/*.md` 长期 Agent memory |
| `src/personal_knowledge_agent/memory_index.py` | 读写 `.memory/MEMORY.md` 记忆索引 |
| `src/personal_knowledge_agent/session_store.py` | 读写 `.session/current.md` 和 `.session/artifacts/` |
| `src/personal_knowledge_agent/context_compactor.py` | 大工具结果落盘和 compact record 生成 |
| `src/personal_knowledge_agent/memory_extractor.py` | 生成 memory candidates |
| `src/personal_knowledge_agent/schemas.py` | 轻量数据契约 |
| `src/personal_knowledge_agent/sqlite_store.py` | SQLite 初始化、写入、读取、检索 |
| `.knowledge/knowledge.db` | 本地知识库数据库文件 |
| `.memory/MEMORY.md` | 用户可见 Agent memory 索引 |
| `.memory/*.md` | 用户可见 Agent 长期记忆文档 |
| `.session/current.md` | 当前任务状态摘要 |
| `.session/artifacts/` | compact 后可回读的大输出 artifact |

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
| `update_session_memory` | 更新当前 session memory | turn-end 或 compact 后 | 是 | 否 |
| `compact_context_artifact` | 将大工具结果落盘并返回 compact record | tool result 超过阈值或显式 compact 时 | 是 | 否 |
| `propose_memory_candidate` | 提交长期 memory 候选 | turn-end 提取到可复用记忆时 | 是 | 视类型而定 |

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

#### `update_session_memory`

- **职责**:
  更新 `.session/current.md`，保存当前任务目标、已确认决策、开放问题和下一步。session memory 用于跨 compact 延续当前任务，不是长期事实来源。

- **输入**:

```json
{
  "current_goal": "当前任务目标",
  "confirmed_decisions": ["已确认决策"],
  "open_questions": ["开放问题"],
  "next_steps": ["下一步"]
}
```

- **输出**:

```json
{
  "ok": true,
  "path": ".session/current.md",
  "updated_at": "ISO 8601 时间"
}
```

- **可展示输入字段**:
  - `current_goal`
  - `confirmed_decisions`
  - `open_questions`
  - `next_steps`

- **可展示输出字段**:
  - `ok`
  - `path`
  - `updated_at`
  - `error_code`
  - `message`

- **副作用**:
  写入或覆盖 `.session/current.md`。

- **失败处理**:
  输入字段类型非法时返回结构化错误。写入失败时返回 `ok: false`、`error_code: "session_write_failed"` 和 `message`，不得影响 Q&A 工具执行。

#### `compact_context_artifact`

- **职责**:
  将过大的 tool result 或上下文材料写入 `.session/artifacts/`，并返回 compact record。compact 只服务当前上下文窗口，不产生长期记忆。

- **输入**:

```json
{
  "run_id": "本轮运行 ID",
  "artifact_name": "artifact 文件名建议",
  "content": "需要落盘的大输出",
  "summary": "摘要",
  "relevance": "与当前任务的关系",
  "must_keep": ["必须保留的关键信息"]
}
```

- **输出**:

```json
{
  "ok": true,
  "compact_record": {
    "artifact_path": ".session/artifacts/run-123-tool-2.txt",
    "summary": "摘要",
    "relevance": "相关性说明",
    "must_keep": ["必须保留的关键信息"]
  }
}
```

- **可展示输入字段**:
  - `run_id`
  - `artifact_name`
  - `summary`
  - `relevance`
  - `must_keep`

- **可展示输出字段**:
  - `ok`
  - `compact_record.artifact_path`
  - `compact_record.summary`
  - `compact_record.relevance`
  - `compact_record.must_keep`
  - `error_code`
  - `message`

- **副作用**:
  写入 `.session/artifacts/`。

- **失败处理**:
  content 为空或写入失败时返回结构化错误。artifact 落盘失败时 Agent 应降级为不 compact 或保留原始 tool result，不得丢失当前回答所需证据。

#### `propose_memory_candidate`

- **职责**:
  提交一条长期 Agent memory 候选。该工具负责按 type、source_type 和 write_policy 判断是否自动写入 `.memory/*.md`，或保存为待用户确认候选。

- **输入**:

```json
{
  "name": "候选 memory 名称",
  "type": "user / feedback / project / reference",
  "description": "简短描述",
  "content": "候选 memory 正文",
  "source_type": "user_explicit / user_decision / project_doc / agent_extracted / reference",
  "source_ref": "来源引用，可为空",
  "confidence": "high / medium / low"
}
```

- **输出**:

```json
{
  "ok": true,
  "status": "written / pending_confirmation / rejected",
  "memory_path": ".memory/project-example.md",
  "requires_confirmation": false,
  "message": "处理结果说明"
}
```

- **可展示输入字段**:
  - `name`
  - `type`
  - `description`
  - `source_type`
  - `source_ref`
  - `confidence`

- **可展示输出字段**:
  - `ok`
  - `status`
  - `memory_path`
  - `requires_confirmation`
  - `message`
  - `error_code`

- **副作用**:
  可能写入 `.memory/*.md` 并更新 `.memory/MEMORY.md`，或写入待确认候选队列。

- **失败处理**:
  字段缺失、type 非法、候选与已有 memory 冲突或 confidence 过低时返回 `ok: false` 或 `status: "pending_confirmation"`。不得在冲突时自动覆盖已有 memory。

- **写入规则**:
  1. `session` 不通过本工具写入长期 memory，应由 `update_session_memory` 覆盖 `.session/current.md`。
  2. `reference` 可自动写入，但只写路径、用途和入口说明，不复制大内容。
  3. `project` 仅在来源是用户明确决策或项目文档时可自动写入。
  4. `user` 默认需要确认，除非用户明确说“记住”“以后”“每次”等长期偏好表达。
  5. `feedback` 默认展示候选，确认后写入。
  6. 模型推测、临时讨论、敏感信息和过期任务状态不得自动写入长期 memory。

---

## 4. 上下文来源与记忆边界

- **运行时上下文来源**:
  1. 用户当前输入。
  2. LLM 当前轮输出。
  3. 工具返回的结构化结果。
  4. Prompt Builder 生成的 system prompt。
  5. `.memory/MEMORY.md` memory index。
  6. 按需读取的少量 `.memory/*.md`。
  7. `.session/current.md` 当前任务摘要。
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
  7. `.session/current.md` 中的当前任务状态。
  8. `.session/artifacts/` 中未整理为长期 memory 的原始大输出。
  9. compact record 本身。

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

- **Session memory 边界**:
  1. `.session/current.md` 保存当前任务目标、已确认决策、开放问题和下一步。
  2. `.session/current.md` 用于处理“继续”“按刚才的来”等依赖当前任务状态的输入。
  3. `.session/current.md` 可以被自动更新和覆盖。
  4. `.session/current.md` 不得作为长期事实来源。
  5. `.session/current.md` 不得作为 Q&A 回答来源。

- **配置边界**:
  1. `.env` 只保存运行配置，不是长期知识来源。
  2. `DEEPSEEK_API_KEY` 不得进入 messages、tool result、SQLite 或日志。
  3. `.env`、`.knowledge/`、`.session/` 和本地 `.memory/` 内容应通过 `.git/info/exclude` 在本地忽略，不要求提交仓库级 `.gitignore`。

- **上下文裁剪规则**:
  1. 第一版优先保留用户当前输入、最近一次 LLM tool call 和 tool result。
  2. 回答必须保留用于引用来源的 card_id、question、source_type 和 created_at。
  3. 不把历史对话当作可靠长期记忆。
  4. turn-start 指收到用户输入后、第一次调用主 LLM 前的上下文准备阶段。
  5. turn-start 选择相关 memory 时，不得只依赖 user_input，还必须结合 `.session/current.md` 中的 current_goal、open_questions、confirmed_decisions 和 next_steps。
  6. 当单个 tool result 或本轮累计工具结果超过阈值时，应优先将原始内容写入 `.session/artifacts/`，并用 compact record 替换上下文中的大输出。
  7. compact record 必须保留 artifact_path、summary、relevance 和 must_keep。
  8. compact 不得删除回答所需证据，不得替代长期 memory 写入。

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
  `.env` 或环境变量缺少 `DEEPSEEK_API_KEY`，或 DeepSeek / SQLite 初始化失败。

- **用户可见反馈**:  
  启动失败时输出明确错误；运行中工具或模型失败时展示 Agent 返回的失败说明。

推荐本地使用方式：

```bash
uv venv
uv pip install -e .
. .venv/bin/activate
pka
```

`pka` 启动后进入持续交互，用户可以连续录入 Q&A 或提问。

### 5.5 CLI 实时运行过程展示

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

### 5.6 Turn-start 上下文准备

1. Agent Loop 收到用户当前输入。
2. Memory Manager 读取 `.memory/MEMORY.md`，得到 memory index。
3. Session Manager 读取 `.session/current.md`，得到当前任务状态；文件不存在时使用空 session summary。
4. Agent Loop 使用 user_input、session current_goal、confirmed_decisions、open_questions、next_steps 和 memory index 生成 retrieval query。
5. Memory Manager 根据 retrieval query 和 memory index 选择最多 N 条相关 memory。
6. Memory Manager 读取所选 `.memory/*.md` 全文。
7. Prompt Builder 将 base system prompt、memory index 摘要、selected memories 和 session summary 组合成本轮 system/context prompt。
8. Agent Loop 继续执行原有 LLM + tool loop。

- **成功条件**:
  本轮上下文包含用户当前输入、基础规则、可用 memory index、相关 memory 和当前 session summary，且未默认注入全部 memory 全文。

- **失败条件**:
  memory index 格式非法、memory 文件读取失败或 session 文件读取失败。

- **用户可见反馈**:
  memory 或 session 读取失败时，Agent 可以降级为空 memory / 空 session 继续处理，并在 CLI 事件中展示简短错误；不得影响 Q&A 主流程的工具检索和回答。

### 5.7 上下文压缩

1. Agent Loop 或 Context Compactor 检查 compact 触发条件。
2. 当单个 tool result 超过阈值、本轮累计 tool result 过大，或用户显式要求总结 / 进入下一阶段时，触发 compact。
3. Context Compactor 将原始大输出写入 `.session/artifacts/`。
4. Context Compactor 生成 compact record，至少包含 artifact_path、summary、relevance 和 must_keep。
5. Agent Loop 用 compact record 替换上下文中的大输出，或在 trace 中记录 compact record。
6. 必要时 Session Manager 更新 `.session/current.md`，保存当前任务目标、已确认决策、开放问题和下一步。

- **成功条件**:
  大输出可通过 artifact_path 回读，当前上下文只保留高相关摘要和关键事实。

- **失败条件**:
  artifact 写入失败、compact record 字段缺失或 summary 无法生成。

- **用户可见反馈**:
  compact 成功时可在事件中展示 artifact_path 和 summary。compact 失败时降级为不压缩或保留原始 tool result，不得丢失回答所需证据。

### 5.8 Turn-end memory candidate 提取

1. Agent Loop 完成本轮最终回答。
2. Memory Extractor 收集 recent dialogue、tool result summaries、session summary 和 memory index。
3. Memory Extractor 提取结构化 memory candidates。
4. Memory Manager 对候选做去重、字段校验和冲突检测。
5. Memory Manager 按写入规则处理候选：自动写入、保存为待确认，或拒绝写入。
6. 自动写入时，Memory Manager 写入 `.memory/*.md` 并更新 `.memory/MEMORY.md`。
7. 需要确认时，Agent 或 CLI 展示候选，不得声称已经写入长期 memory。

- **成功条件**:
  稳定偏好、明确项目决策、长期反馈和引用入口被整理为可追溯候选，并按规则处理。

- **失败条件**:
  候选字段非法、候选与已有 memory 冲突、来源不足、confidence 过低或写入失败。

- **用户可见反馈**:
  自动写入时展示 memory name、type 和 path。需要确认时展示候选内容和确认需求。拒绝写入时说明原因。

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

### 6.5 `.session/current.md`

`.session/current.md` 保存当前任务状态，可以自动更新和覆盖，不是长期事实来源。

格式：

```markdown
# Current Session

## Current Goal
设计本项目的 Agent memory 管理。

## Confirmed Decisions
- Q&A 知识库和 Agent memory 必须分开。
- `.memory/*.md` 是用户可见的长期 Agent memory 来源。

## Open Questions
- memory candidate 的确认交互如何在 CLI 中展示。

## Next Steps
- 实现 memory index 读取。
```

字段约束：

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `current_goal` | `TEXT` | 否 | 当前任务目标 |
| `confirmed_decisions` | `LIST` | 否 | 已确认决策 |
| `open_questions` | `LIST` | 否 | 尚未解决的问题 |
| `next_steps` | `LIST` | 否 | 下一步行动 |

### 6.6 Compact Record

compact record 是上下文压缩后的结构化摘要，必须能指回原始 artifact。

格式：

```json
{
  "artifact_path": ".session/artifacts/run-123-tool-2.txt",
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

### 6.7 Memory Candidate

memory candidate 是 turn-end 提取出的长期 Agent memory 候选。候选不是已写入记忆，只有工具返回 `status: "written"` 后才表示长期 memory 已保存。

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
| 配置缺失 | `.env` 和环境变量中均没有 `DEEPSEEK_API_KEY` | CLI Runtime 不启动 Agent | 提示用户设置 `DEEPSEEK_API_KEY` |
| LLM 调用失败 | DeepSeek API 请求失败 | 不编造工具结果或最终回答 | 说明模型调用失败，可稍后重试 |
| 工具执行失败 | 工具抛错或返回 `ok: false` | 不声称动作成功 | 展示失败原因 |
| CLI 输入为空 | 用户直接回车 | 不调用 AgentLoop | 继续等待输入 |
| CLI 退出 | 用户输入 `/exit` 或 `/quit` | 正常结束循环 | 输出退出提示 |
| CLI Renderer 失败 | 渲染事件时发生异常 | 不影响工具执行和 Agent 最终回答 | 向 stderr 输出简短错误 |
| 日志队列满 | Async JSONL Logger 队列达到上限 | 不阻塞 Agent Loop，丢弃日志事件 | stderr 最多提示一次 |
| 日志写入失败 | `.logs/agent.log` 无法写入 | 停止继续写日志，不影响 Agent | stderr 最多提示一次 |
| 日志 flush 超时 | 正常退出时 2 秒内未 flush 完成 | 继续退出 | 不保证所有日志写入完成 |
| Memory index 缺失 | `.memory/MEMORY.md` 不存在 | 使用空 memory index 继续运行 | 可提示尚未初始化 Agent memory |
| Memory index 非法 | `MEMORY.md` 表格缺少必填字段或字段非法 | 不注入 memory index，继续 Q&A 主流程 | 说明 memory index 格式非法 |
| Memory frontmatter 非法 | `.memory/*.md` 缺少 name、type、description 或 type 非法 | 跳过该 memory，不注入本轮上下文 | 说明 memory 文件格式非法 |
| Memory 读取失败 | memory 文件不存在或无法读取 | 不注入该 memory，继续 Q&A 主流程 | 说明 memory 读取失败 |
| Session summary 读取失败 | `.session/current.md` 无法读取或格式非法 | 使用空 session summary 继续运行 | 说明 session 状态未加载 |
| Session summary 写入失败 | `.session/current.md` 无法写入 | 不影响最终回答，不声称 session 已更新 | 说明 session 状态未更新 |
| Artifact 落盘失败 | `.session/artifacts/` 无法写入 | 降级为不 compact 或保留原始 tool result | 说明 compact artifact 未保存 |
| Compact record 非法 | 缺少 artifact_path、summary、relevance 或 must_keep | 不使用该 compact record | 说明 compact 失败 |
| Memory candidate 冲突 | 候选与已有 memory 含义冲突 | 不自动覆盖，标记为待确认 | 展示冲突并要求用户确认 |
| Memory candidate 需要确认 | type 为 user / feedback 或来源不足 | 不自动写入长期 memory | 展示候选并说明需要确认 |
| Memory candidate 写入失败 | `.memory/*.md` 或 `MEMORY.md` 无法写入 | 不声称已写入 memory | 说明写入失败和错误原因 |

- **通用降级原则**:
  1. 工具失败时不得假装已完成。
  2. 依据不足时必须明确说明。
  3. 未落库内容不得作为长期记忆引用。
  4. 不得为了回答完整而引入无来源外部知识。
  5. Agent memory 失败不得阻断 Q&A 保存、检索和回答主流程。
  6. Session memory 失败不得被解释为长期事实缺失。
  7. Compact 失败不得丢失回答所需证据。
  8. Memory candidate 未写入前不得声称 Agent 已经记住。

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

- **Memory 写入降级原则**:
  1. `session` 自动写入 `.session/current.md`，可覆盖，不进入长期 memory。
  2. `reference` 可自动写入长期 memory，但只写路径、用途和入口说明。
  3. `project` 仅在来源是用户明确决策或项目文档时可自动写入。
  4. `user` 默认需要确认，除非用户明确要求“记住”“以后”“每次”。
  5. `feedback` 默认展示候选，确认后写入。
  6. 模型推测、临时讨论、敏感信息和过期任务状态不得自动写入长期 memory。

---

## 8. 测试要求

- **单元测试**:
  1. `SQLiteStore.save_card` 能写入并读回 Q&A 卡片。
  2. `SQLiteStore.search_cards` 能按 question、answer、summary、keywords 的 LIKE 命中返回结果。
  3. `SQLiteStore.list_recent_cards` 能按 created_at 倒序返回。
  4. `KnowledgeTools.save_qa_card` 能校验必填字段。
  5. `KnowledgeTools.read_qa_card` 对不存在 ID 返回结构化 not_found。
  6. `DeepSeekClient` 请求构造和响应解析使用 mock 测试。
  7. `load_config` 能从 `.env` / 环境变量读取 `DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL` 和 `KNOWLEDGE_DB_PATH`。
  8. 缺少 `DEEPSEEK_API_KEY` 时返回明确错误。
  9. `MemoryIndex` 能读取 `.memory/MEMORY.md` 索引。
  10. `MemoryIndex` 对缺少必填列或非法 type 返回结构化错误。
  11. `MemoryStore` 能读取合法 `.memory/*.md`。
  12. `MemoryStore` 对 frontmatter 缺失或非法 type 返回结构化错误。
  13. `SessionStore` 能创建、读取和覆盖 `.session/current.md`。
  14. `SessionStore` 能将 artifact 写入 `.session/artifacts/`。
  15. `ContextCompactor` 对超过阈值的大输出生成 compact record。
  16. compact record 必须包含 artifact_path、summary、relevance 和 must_keep。
  17. `MemoryExtractor` 只生成候选，不直接写入长期 memory。
  18. user / feedback candidate 默认不自动写入长期 memory。

- **集成测试**:
  1. Agent Loop 能接收 fake LLM 的 tool call，执行工具并回填 tool result。
  2. Agent Loop 在 fake LLM 返回 final answer 时能直接结束。
  3. 保存后再搜索能召回同一张卡片。
  4. CLI Runtime 能用 fake input / fake AgentLoop 跑一次输入和退出流程。
  5. `pyproject.toml` 必须声明 `pka = "personal_knowledge_agent.__main__:main"` 或等价 script 入口。
  6. Agent Loop 关键阶段会产生结构化事件。
  7. CLI Renderer 对长文本进行截断。
  8. Async JSONL Logger 完整记录 `user_input`。
  9. Async JSONL Logger 使用后台线程异步写入，不阻塞主流程。
  10. Async JSONL Logger 在队列满和写入失败时按降级策略处理。
  11. turn-start 能读取 memory index 和 session summary。
  12. turn-start memory 选择必须结合 user_input 和 session summary。
  13. Prompt Builder 能注入 memory index、selected memories 和 session summary。
  14. 大 tool result 能落盘并在 trace 中保留 compact record。
  15. turn-end 能更新 session summary。
  16. turn-end 能生成 memory candidates 并展示待确认候选。

- **回归测试**:
  1. 检索为空时不会生成虚假来源。
  2. 工具失败时不会返回保存成功。
  3. 回答来源至少包含 card_id、question、source_type、created_at。
  4. 日志不输出 API key。
  5. 日志不输出完整 system prompt 或完整 LLM messages。
  6. Tool event 只包含工具契约声明的可展示字段。
  7. 与新事件流重复的旧 logging 成功路径埋点应删除或收缩。
  8. Q&A 检索只使用 `qa_cards`，不得混入 `.memory/*.md`。
  9. `.session/current.md` 不得作为长期事实来源。
  10. compact artifact 不得作为 Q&A 回答来源。
  11. Memory candidate 未写入时不得声称已经记住。
  12. user / feedback candidate 在未确认前不得自动写入 `.memory/*.md`。

- **可选 Live Smoke Test**:
  1. 仅在存在 `DEEPSEEK_API_KEY` 时运行。
  2. 使用 `deepseek-v4-flash` 做真实 DeepSeek 调用。
  3. 完成一次保存 Q&A。
  4. 再完成一次检索回答。
  5. 不把 API key 写入仓库或日志。

- **验收清单**:
  1. 符合本文档定义的能力边界。
  2. SQLite `qa_cards` 是 Q&A 知识库唯一长期记忆来源。
  3. 四个工具契约稳定可测。
  4. DeepSeek 只出现在薄 LLM Client 中。
  5. Q&A 知识库和 Agent memory 保持分离。
  6. `.memory/*.md` 是用户可见的 Agent 长期工作记忆来源。
  7. `.session/current.md` 只保存当前任务状态。
  8. compact 只缩减上下文窗口，不替代长期 memory。
  9. 第一版不包含 Wiki、文件监听、周报、多 Agent、向量库和后台任务。

---

## 9. 变更记录

| 日期 | 变更内容 | 变更原因 | 提交 |
|---|---|---|---|
| `2026-05-30` | 新增本地个人 Q&A 知识库 Agent 开发上下文 | 锁定第一版 Agent 设计边界和实现验收依据 | `TBD` |
| `2026-05-31` | 补充 Agent memory、session memory、context compact 和 memory candidate 设计边界 | 为后续实现 Claude Code 风格记忆管理先锁定文档契约 | `TBD` |
