---
module: "local-qa-knowledge-agent"
title: "本地个人 Q&A 知识库"
language: "Python"
agent_type: "Tool-Using Agent / RAG Agent"
last_updated: "2026-06-25"
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
> 不得擅自扩大 Agent 权限，不得绕过声明的 Tool / Store / Repository 直接操作数据库、文件系统、外部接口或其他底层资源。
> 不得新增未声明的核心流程、外部依赖、高风险操作或数据写入行为。
> 涉及本 Agent 的新增、修改或重构时，AI Coding 工具必须先读取本文档，并以本文档作为实现边界和验收依据。
> 如果实现前发现本文档与目标需求不一致，或需要调整 Agent 的角色边界、工具契约、数据模型、核心流程、外部依赖、权限规则等设计内容，必须先修改本文档，并将文档变更提交到本地 Git；在文档版本被锁定后，才能开始修改代码。
> 禁止在同一次提交中混合 Agent 设计文档变更和对应代码实现变更，除非只是修正文档中的错别字、路径或示例。

---

## 1. Agent 定位与能力边界

- **背景**:
  用户希望把零散 Q&A 转换为可检索、可追溯、可复用的本地知识资产。当前阶段优先保证 Q&A 录入、保存、检索、回答和来源引用闭环稳定。

- **核心价值**:
  通过工具把用户提供的 Q&A 持久化到本地 SQLite，并在后续提问时基于本地检索结果生成可追溯回答。

- **Agent 角色**:
  本 Agent 是本地个人 Q&A 知识库 Agent，负责判断用户是在录入知识、检索知识、维护卡片还是普通对话，并通过声明工具完成实际知识库动作。

- **核心目标**:
  1. 保存用户提供的 Q&A。
  2. 从本地 SQLite 检索相关 Q&A 卡片。
  3. 基于检索结果回答问题并引用来源。
  4. 在依据不足时明确拒答，不编造来源或事实。
  5. 维护当前 CLI / Web session 的 runtime `messages[]`。
  6. 读取用户可见的 Agent memory，用于理解协作偏好和长期约束。
  7. 在 transcript 过长或上下文超限时执行 runtime compact。
  8. 通过本地 Web Runtime 提供浏览器聊天入口和基础 Q&A 卡片浏览能力。

- **包含能力**:
  1. 录入用户提供的 Q&A。
  2. 由模型生成 summary、keywords 和 category。
  3. 保存、检索、读取、更新、删除、列出和合并 Q&A 卡片。
  4. 使用 SQLite LIKE 与 Qdrant 语义索引进行 hybrid 检索。
  5. 检测疑似重复 Q&A 卡片。
  6. 基于本轮真实工具结果组织回答和来源区块。
  7. 读取 `.memory/MEMORY.md` 和少量相关 `.memory/*.md`。
  8. 从 `.sessions/<session_id>/transcript.jsonl` 恢复 runtime messages。
  9. 使用 `.sessions/<session_id>/summary.md` + recent messages 恢复长 session。
  10. 将过大的 tool result 写入 `.sessions/<session_id>/artifacts/` 并保留 compact record。
  11. 生成 memory candidate 事件；当前不自动写入长期 memory。
  12. Web UI 支持聊天、session 列表、历史恢复、最近卡片、搜索卡片和卡片详情。
  13. 保存、查询和更新本地 todo 待办项。

- **不包含能力**:
  1. 不做 Markdown Wiki、文件监听或自动索引。
  2. 不做周报、日报或自动总结。
  3. 不做多 Agent。
  4. 不把 Agent memory 混入 Q&A 知识库来源。
  5. 不默认把完整历史对话作为长期记忆。
  6. 不自动写入长期 memory 或维护 memory 确认队列。
  7. 不使用 Qdrant 或 Kuzu 替代 SQLite 事实源。
  8. Web 第一版不做卡片编辑、删除、合并、自动知识图谱或后台任务。
  9. Todo 第一版不做专门 Web UI、物理删除、提醒、定时任务、自然语言时间解析、优先级、标签、重复任务或历史版本。

- **行为约束**:
  1. 涉及长期知识库保存、检索、读取、更新、删除或合并的动作，必须通过声明工具完成。
  2. Agent 不得声称已经保存、查询、更新或删除实际未通过工具完成的数据。
  3. 声称基于本地知识库回答、引用 `card_id` 或展示来源区块时，必须有本轮真实工具证据。
  4. `.memory/*.md`、`.sessions/<session_id>/summary.md`、compact artifact、memory candidate 和 LLM 临时输出不得作为 Q&A 回答来源。
  5. 删除、更新、合并和图谱关系确认等高风险操作必须经过 permission gate。
  6. SQLite `qa_cards` 是 Q&A 事实源；Qdrant 只作为语义召回索引。
  7. 未调用检索工具时允许普通回答，但不得声称回答来自本地知识库或伪造 `card_id`。
  8. SQLite `todo_items` 是 todo 事实源；todo 数据不得作为 Q&A 知识库回答的来源证据。

---

## 2. Harness 架构与代码边界

> 本节说明 Agent Harness 的组成，以及各层职责边界。

- **Agent Runtime 职责**:
  - 接收用户输入并维护 runtime `messages[]`。
  - 调用 Prompt Builder 获取 system prompt。
  - 调用 LLM Client 并解析 tool calls。
  - 通过 Tool Dispatcher 执行工具并回填 tool result。
  - 在没有 tool calls 时生成最终回答。
  - 基于本轮工具结果执行来源证据校验。
  - 基于 LLM API 返回的真实 usage 触发 runtime compact。
  - 产生结构化运行事件，供 CLI / Web 展示和本地开发日志使用。

- **Agent Bootstrap 职责**:
  - `agent_component_factory.py` 创建 Agent loop runner 及其依赖。
  - `agent_runtime_config.py` 从 `.env` 和环境变量加载运行配置。
  - CLI Runtime 和 Web Runtime 必须复用同一套 Agent 装配逻辑。

- **Prompt Builder 职责**:
  - 拼接身份、行为规则、证据纪律、权限边界、记忆边界、能力边界、回答格式和拒答规则。
  - 注入 memory index、selected memories 和 session summary。
  - 不保存业务数据，不承担数据库读写职责。
  - 不长期维护具体工具参数字段；工具细节以第 3 节和 tool schema 为准。

- **Prompt 修改准入原则**:
  - 只有当某条规则必须由模型在生成或决策时持续遵守，并且不能被更可靠地放进代码、工具 schema、权限层、校验器或测试中时，才允许写入 prompt。
  - Prompt 是模型行为边界，不是工具契约文档。新增或修改 tool 时，默认只更新 tool schema、工具契约、代码和测试；只有 schema 或代码无法约束模型的跨工具决策行为时，才补充 prompt。

- **Tools 职责**:
  - 作为 Agent 可执行知识库动作的唯一入口。
  - 封装 Q&A 工具、todo 工具和 Agent memory 读取工具。
  - 对输入非法、权限不足和底层失败返回结构化错误。

- **Services / Repositories 职责**:
  - Repository 负责 SQLite、Qdrant、`.memory/`、`.sessions/` 和 JSONL 日志等本地数据读写。
  - Service 负责重复检测、语义索引、session 恢复、上下文压缩和 memory candidate 提取等业务逻辑。
  - Tools 必须通过 Service / Repository 完成底层操作，不复制底层逻辑。

- **Storage / External API 职责**:
  - SQLite `qa_cards` 保存 Q&A 事实数据。
  - SQLite `todo_items` 保存 todo 事实数据。
  - Qdrant local mode 保存 Q&A 语义索引。
  - `.memory/` 保存用户可见的 Agent 长期工作记忆。
  - `.sessions/` 保存当前会话恢复数据。
  - DeepSeek 负责主 LLM 调用。
  - DashScope / Qwen embedding 负责文本向量生成。
  - Kuzu 是后续轻量知识图谱的本地存储，不得替代 Q&A 事实源。

- **禁止绕过的边界**:
  1. Agent Runtime 不得直接操作 SQLite、Qdrant、`.memory/` 或 `.sessions/`。
  2. LLM 输出不得被视为已持久化事实。
  3. 工具不得绕过权限规则执行高风险操作。
  4. Web Runtime 不得绕过 AgentLoop、Tools 或 Store 执行业务动作。
  5. 未在本文档声明的核心依赖不得擅自引入。

- **核心文件 / 目录**:

| 路径 | 职责 |
|---|---|
| `src/personal_knowledge_agent/agent_bootstrap/` | 运行配置和跨模块组件装配。 |
| `src/personal_knowledge_agent/agent_runtime/` | Agent loop、LLM 调用、tool call、最终回答、来源校验和事件发射。 |
| `src/personal_knowledge_agent/agent_context/` | Prompt、memory、session transcript、summary 和 compact 管理。 |
| `src/personal_knowledge_agent/agent_tools/` | LLM 可调用工具 adapter。 |
| `src/personal_knowledge_agent/qa_data_access/` | SQLite Q&A 事实库、Qdrant 语义索引和重复检测。 |
| `src/personal_knowledge_agent/todo_data_access/` | SQLite todo 事实库。 |
| `src/personal_knowledge_agent/tool_runtime/` | Tool dispatcher、tool model 和权限策略。 |
| `src/personal_knowledge_agent/llm_clients/` | LLM provider client。 |
| `src/personal_knowledge_agent/agent_observability/` | Agent 运行事件 JSONL 日志。 |
| `src/personal_knowledge_agent/apps/cli/` | CLI Runtime。 |
| `src/personal_knowledge_agent/apps/web/` | Web Runtime 和静态 UI。 |

---

## 3. 可调用工具与工具契约

### 3.1 工具列表

| 工具名 | 工具职责 | 调用时机 | 是否有副作用 | 是否需要确认 |
|---|---|---|---|---|
| `save_qa_card` | 保存一张 Q&A 卡片 | 用户明确提供可保存 Q&A 时 | 是 | 否 |
| `search_qa_cards` | 基于 SQLite LIKE 检索 Q&A | 用户提问或查找知识时 | 否 | 否 |
| `hybrid_search_qa_cards` | 基于关键词与语义召回混合检索 Q&A | 需要更高召回质量时 | 否 | 否 |
| `read_qa_card` | 按 `card_id` 读取卡片详情 | 需要引用或核对具体卡片时 | 否 | 否 |
| `update_qa_card` | 更新已有卡片 | 用户明确要求修改卡片时 | 是 | 是 |
| `delete_qa_card` | 删除已有卡片 | 用户明确要求删除卡片时 | 是 | 是 |
| `list_recent_cards` | 列出最近卡片 | 用户要求查看最近知识时 | 否 | 否 |
| `detect_duplicate_cards` | 检测疑似重复卡片 | 合并前或用户要求查重时 | 否 | 否 |
| `merge_qa_cards` | 合并重复卡片 | 用户确认合并时 | 是 | 是 |
| `rebuild_qa_semantic_index` | 重建语义索引 | 系统维护或索引修复时 | 是 | 否 |
| `create_todo` | 保存一条 todo 待办项 | 用户明确要求记录之后要做的行动项、任务或待办时 | 是 | 否 |
| `list_todos` | 查询 todo 待办项 | 用户要求查看、搜索或核对本地 todo 列表时 | 否 | 否 |
| `update_todo` | 更新 todo 待办项 | 用户要求修改 todo 内容、备注、截止时间或状态时 | 是 | 否 |
| `list_memory_index` | 读取 Agent memory 索引 | 需要理解长期协作偏好时 | 否 | 否 |
| `read_memory` | 读取指定 memory 文档 | memory index 显示相关时 | 否 | 否 |

### 3.2 工具契约

#### `save_qa_card`

- **职责**: 保存用户提供的一张 Q&A 卡片。
- **输入**:

```json
{
  "question": "string, required",
  "answer": "string, required",
  "summary": "string, required",
  "keywords": ["string"],
  "category": "string, required",
  "source_type": "string, required"
}
```

- **输出**:

```json
{
  "ok": "boolean",
  "card_id": "string",
  "created_at": "string",
  "error": "string"
}
```

- **副作用**: 写入 SQLite `qa_cards`，并尽力写入 Qdrant 语义索引。
- **失败处理**: 必填字段缺失、字段类型非法、数据库写入失败或语义索引失败时返回结构化错误。

#### `search_qa_cards`

- **职责**: 使用 SQLite LIKE 检索 Q&A 卡片。
- **输入**:

```json
{
  "query": "string, required",
  "limit": "integer"
}
```

- **输出**:

```json
{
  "ok": "boolean",
  "cards": [
    {
      "card_id": "string",
      "question": "string",
      "summary": "string",
      "source_type": "string",
      "created_at": "string"
    }
  ],
  "error": "string"
}
```

- **副作用**: 无。
- **失败处理**: 查询非法或数据库读取失败时返回结构化错误；检索为空时返回空 `cards`。

#### `hybrid_search_qa_cards`

- **职责**: 使用 SQLite LIKE 与 Qdrant 语义召回合并排序。
- **输入**:

```json
{
  "query": "string, required",
  "limit": "integer",
  "category": "string"
}
```

- **输出**:

```json
{
  "ok": "boolean",
  "cards": [
    {
      "card_id": "string",
      "question": "string",
      "summary": "string",
      "category": "string",
      "score": "number",
      "source_type": "string",
      "created_at": "string"
    }
  ],
  "error": "string"
}
```

- **副作用**: 调用 embedding 服务和读取 Qdrant；不修改事实库。
- **失败处理**: 语义检索失败时可降级为 SQLite LIKE；整体失败时返回结构化错误。

#### `read_qa_card`

- **职责**: 按 `card_id` 读取完整 Q&A 卡片。
- **输入**:

```json
{
  "card_id": "string, required"
}
```

- **输出**:

```json
{
  "ok": "boolean",
  "card": "object",
  "error": "string"
}
```

- **副作用**: 无。
- **失败处理**: 卡片不存在时返回 `not_found` 风格错误，不得生成虚假卡片。

#### `update_qa_card`

- **职责**: 更新已有 Q&A 卡片的内容或分类。
- **输入**:

```json
{
  "card_id": "string, required",
  "question": "string",
  "answer": "string",
  "summary": "string",
  "keywords": ["string"],
  "category": "string"
}
```

- **输出**:

```json
{
  "ok": "boolean",
  "card_id": "string",
  "updated_at": "string",
  "error": "string"
}
```

- **副作用**: 更新 SQLite，并尽力更新 Qdrant 语义索引。
- **失败处理**: 必须经过 permission gate；用户拒绝或工具失败时不得修改卡片。

#### `delete_qa_card`

- **职责**: 物理删除已有 Q&A 卡片。
- **输入**:

```json
{
  "card_id": "string, required"
}
```

- **输出**:

```json
{
  "ok": "boolean",
  "deleted_card_id": "string",
  "error": "string"
}
```

- **副作用**: 物理删除 SQLite 卡片，并尽力删除 Qdrant 向量。
- **失败处理**: 必须经过 permission gate；用户拒绝时返回 `permission_denied`。

#### `list_recent_cards`

- **职责**: 按创建时间倒序列出最近 Q&A 卡片。
- **输入**:

```json
{
  "limit": "integer"
}
```

- **输出**:

```json
{
  "ok": "boolean",
  "cards": ["object"],
  "error": "string"
}
```

- **副作用**: 无。
- **失败处理**: 读取失败时返回结构化错误。

#### `detect_duplicate_cards`

- **职责**: 检测疑似重复 Q&A 卡片，可支持单卡或全库查重。
- **输入**:

```json
{
  "card_id": "string",
  "scope": "string, one of: card, all",
  "limit": "integer"
}
```

- **输出**:

```json
{
  "ok": "boolean",
  "duplicate_groups": ["object"],
  "error": "string"
}
```

- **副作用**: 无。
- **失败处理**: 输入非法、候选不足或底层检索失败时返回结构化错误或空候选。

#### `merge_qa_cards`

- **职责**: 合并用户确认的重复卡片，创建新卡片并物理删除原卡片。
- **输入**:

```json
{
  "source_card_ids": ["string"],
  "question": "string, required",
  "answer": "string, required",
  "summary": "string, required",
  "keywords": ["string"],
  "category": "string, required"
}
```

- **输出**:

```json
{
  "ok": "boolean",
  "merged_card_id": "string",
  "deleted_card_ids": ["string"],
  "error": "string"
}
```

- **副作用**: 新建 SQLite 卡片，物理删除原卡片，并尽力同步 Qdrant。
- **失败处理**: 必须经过 permission gate；任一关键步骤失败时不得声称合并成功。

#### `rebuild_qa_semantic_index`

- **职责**: 为历史 Q&A 卡片重建 Qdrant 语义索引。
- **输入**:

```json
{
  "limit": "integer",
  "force": "boolean"
}
```

- **输出**:

```json
{
  "ok": "boolean",
  "processed": "integer",
  "failed": "integer",
  "error": "string"
}
```

- **副作用**: 写入或重建 Qdrant 向量，并更新 `is_vectorized`。
- **失败处理**: 单卡失败不应破坏 SQLite 事实源；整体失败返回结构化错误。

#### `create_todo`

- **职责**: 保存一条本地 todo 待办项。
- **输入**:

```json
{
  "title": "string, required",
  "notes": "string",
  "due_at": "string"
}
```

- **输出**:

```json
{
  "ok": "boolean",
  "todo": "object",
  "error": "string"
}
```

- **副作用**: 写入 SQLite `todo_items`。
- **失败处理**: `title` 缺失、字段类型非法或数据库写入失败时返回结构化错误。

#### `list_todos`

- **职责**: 查询本地 todo 待办项。
- **输入**:

```json
{
  "query": "string",
  "status": "string, one of: open, done, canceled, all",
  "limit": "integer"
}
```

- **输出**:

```json
{
  "ok": "boolean",
  "todos": ["object"],
  "error": "string"
}
```

- **副作用**: 无。
- **失败处理**: 查询条件非法或数据库读取失败时返回结构化错误；未命中时返回空 `todos`。

#### `update_todo`

- **职责**: 更新已有 todo 待办项的内容、备注、截止时间或状态。
- **输入**:

```json
{
  "todo_id": "string, required",
  "title": "string",
  "notes": "string",
  "status": "string, one of: open, done, canceled",
  "due_at": "string"
}
```

- **输出**:

```json
{
  "ok": "boolean",
  "todo": "object",
  "error": "string"
}
```

- **副作用**: 更新 SQLite `todo_items`。
- **失败处理**: 目标不存在、字段非法、未提供更新字段或数据库写入失败时返回结构化错误；第一版不要求 permission gate。

#### `list_memory_index`

- **职责**: 读取 `.memory/MEMORY.md` memory index。
- **输入**:

```json
{}
```

- **输出**:

```json
{
  "ok": "boolean",
  "memories": ["object"],
  "error": "string"
}
```

- **副作用**: 无。
- **失败处理**: index 缺失或格式非法时返回结构化错误，不阻断 Q&A 主流程。

#### `read_memory`

- **职责**: 读取指定 `.memory/*.md` 文档。
- **输入**:

```json
{
  "name": "string, required"
}
```

- **输出**:

```json
{
  "ok": "boolean",
  "memory": "object",
  "error": "string"
}
```

- **副作用**: 无。
- **失败处理**: 文档不存在、frontmatter 非法或读取失败时返回结构化错误。

### 3.3 当前非工具机制

以下能力属于 Harness 内部机制，不作为 LLM 可自由调用工具暴露：

1. runtime context compact。
2. transcript restore 和 session summary restore。
3. JSONL 开发日志写入。
4. memory candidate 生成事件。
5. Web session 管理和 SSE 事件分发。
6. todo 提醒、定时任务和专门 Web UI。

### 3.4 v0.2-v0.7 工具演进边界

1. v0.2 已完成可信来源闭环。
2. v0.3 已完成 Q&A 更新、删除和高风险权限确认。
3. v0.4 已完成 SQLite LIKE + Qdrant hybrid 检索。
4. v0.5 已完成 category。
5. v0.6 规划去重和合并，必须保持用户确认合并。
6. v0.7 规划轻量知识图谱，图谱回答仍必须追溯到 `card_id`。

---

## 4. 上下文来源与记忆边界

- **运行时上下文来源**:
  1. 用户当前输入。
  2. 当前 session 的 runtime `messages[]`。
  3. Prompt Builder 注入的 Agent 规则。
  4. 本轮真实 tool result。
  5. `.memory/MEMORY.md` 和按需选择的少量 `.memory/*.md`。
  6. `.sessions/<session_id>/summary.md` 和 recent messages。

- **长期记忆来源**:
  1. SQLite `qa_cards` 是 Q&A 知识库事实源。
  2. `.memory/*.md` 是 Agent 协作偏好和长期工作记忆来源。
  3. `.sessions/<session_id>/transcript.jsonl` 是当前会话恢复来源，不是 Q&A 事实源。

- **不得作为长期记忆的内容**:
  1. LLM 临时输出。
  2. 未通过工具保存的对话内容。
  3. tool result compact summary。
  4. `.sessions/<session_id>/summary.md`。
  5. memory candidate 事件。
  6. Web UI 临时状态。

- **上下文裁剪规则**:
  1. 每轮最多注入 3 条 `.memory/*.md` 全文；`.memory/MEMORY.md` 索引不计入上限。
  2. 长 transcript 优先使用 `summary.md` + recent messages 恢复。
  3. 大 tool result 应落盘为 artifact，并在上下文中保留 compact record。
  4. compact 只能缩减当前上下文窗口，不得替代长期记忆写入。
  5. 回答 Q&A 问题时必须优先保留本轮真实检索证据。

---

## 5. 核心业务流

### 5.1 录入 Q&A

1. Agent 判断用户输入是否包含可保存的 Q&A。
2. Agent 提取 question、answer、summary、keywords、category 和 source_type。
3. Agent 调用 `save_qa_card`。
4. Tool 写入 SQLite，并尽力更新语义索引。
5. Agent 基于 tool result 告知用户保存结果。

- **成功条件**: `save_qa_card` 返回 `ok: true` 和 `card_id`。
- **失败条件**: 输入缺失关键字段、工具返回错误或数据库写入失败。
- **用户可见反馈**: 成功时展示 `card_id`；失败时展示失败原因，不得声称已保存。

### 5.2 回答问题

1. Agent 判断用户正在询问本地知识库内容。
2. Agent 调用 `search_qa_cards` 或 `hybrid_search_qa_cards`。
3. 必要时调用 `read_qa_card` 核对完整卡片。
4. Agent 只基于本轮真实工具结果组织回答。
5. Agent 输出来源区块，包含 `card_id`、原始问题、`source_type` 和 `created_at`。

- **成功条件**: 检索结果与用户问题相关，且足以支持回答。
- **失败条件**: 检索为空、结果不相关、工具失败或来源不足。
- **用户可见反馈**: 依据不足时明确说明本地知识库中没有找到足够依据。

### 5.3 维护卡片

1. Agent 识别用户的更新、删除、查重或合并意图。
2. Agent 调用对应工具，并在高风险工具执行前触发 permission gate。
3. 用户允许后执行工具；用户拒绝或确认超时则不执行。
4. Agent 基于 tool result 返回维护结果。

- **成功条件**: 对应工具返回 `ok: true`。
- **失败条件**: 用户拒绝、权限超时、工具失败或目标卡片不存在。
- **用户可见反馈**: 展示已执行动作和目标 `card_id`；未执行时明确说明原因。

### 5.4 维护 todo

1. Agent 识别用户保存、查询或更新 todo 的意图。
2. Agent 调用 `create_todo`、`list_todos` 或 `update_todo`。
3. Tool 读写 SQLite `todo_items`。
4. Agent 基于 tool result 返回维护结果。

- **成功条件**: 对应工具返回 `ok: true`。
- **失败条件**: 输入缺失关键字段、工具失败或目标 todo 不存在。
- **用户可见反馈**: 保存或更新成功时展示 `todo_id`；失败时展示失败原因，不得声称已完成。

### 5.5 CLI / Web 持续交互

1. Runtime 使用同一套 Agent 装配逻辑创建 AgentLoop。
2. CLI 通过终端输入输出驱动；Web 通过本地 HTTP、SSE 和静态页面驱动。
3. 每轮用户输入进入 AgentLoop，不绕过工具和来源校验。
4. Web session 之间必须隔离 runtime `messages[]`。

- **成功条件**: 单轮输入能完成工具调用、事件展示和最终回答。
- **失败条件**: 配置缺失、session 非法、AgentLoop 失败或 Web API 失败。
- **用户可见反馈**: CLI / Web 展示结构化错误，不伪造成功状态。

### 5.6 Session 恢复和上下文压缩

1. Runtime 从 `.sessions/<session_id>/transcript.jsonl` 恢复短 transcript。
2. 长 transcript 使用 `summary.md` + recent messages 恢复。
3. LLM usage 达到阈值或明确上下文超限时执行 runtime compact。
4. compact 失败时使用降级恢复，不阻断 Q&A 主流程。

- **成功条件**: 恢复后的 runtime context 足以继续当前 session。
- **失败条件**: transcript 非法、summary 生成失败或 artifact 落盘失败。
- **用户可见反馈**: 可提示恢复降级，但不得解释为 Q&A 知识库缺少依据。

### 5.7 Turn-end memory candidate 提取

1. Agent 在 turn 结束后从用户反馈和协作偏好中提取候选记忆。
2. Runtime 只通过事件暴露候选。
3. 当前实现不自动写入 `.memory/*.md`，也不维护确认队列。

- **成功条件**: 候选事件生成完成或无候选。
- **失败条件**: 提取失败或候选字段非法。
- **用户可见反馈**: 不得声称候选已经写入长期 memory。

---

## 6. 数据模型

### 6.1 `qa_cards`

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `card_id` / `id` | `TEXT` | 是 | 卡片唯一 ID。 |
| `question` | `TEXT` | 是 | 用户提供的原始问题。 |
| `answer` | `TEXT` | 是 | 用户提供的原始答案。 |
| `summary` | `TEXT` | 是 | 模型生成摘要。 |
| `keywords` | `TEXT` | 是 | JSON 字符串形式保存的关键词数组。 |
| `category` | `TEXT` | 是 | Q&A 语义主分类。 |
| `source_type` | `TEXT` | 是 | 来源类型。 |
| `created_at` | `TEXT` | 是 | 系统生成创建时间。 |
| `updated_at` | `TEXT` | 是 | 系统生成更新时间。 |
| `is_vectorized` | `INTEGER` | 是 | 是否已写入语义索引。 |

### 6.2 数据约束

1. `card_id` 必须稳定且唯一。
2. `question`、`answer`、`summary`、`category` 和 `source_type` 不得为空。
3. SQLite `qa_cards` 是事实源。
4. Qdrant 只保存语义索引，不保存权威事实。
5. 删除卡片是物理删除，不使用软删除。
6. 更新卡片不保存历史版本或 before / after 快照。
7. schema 初始化只能补齐缺失表和字段，不得破坏已有数据。

### 6.3 `todo_items`

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `todo_id` / `id` | `TEXT` | 是 | todo 唯一 ID。 |
| `title` | `TEXT` | 是 | todo 标题。 |
| `notes` | `TEXT` | 是 | todo 补充说明，可为空字符串。 |
| `status` | `TEXT` | 是 | todo 状态，只允许 `open`、`done` 或 `canceled`。 |
| `due_at` | `TEXT` | 否 | 可选截止时间字符串；第一版不做自然语言解析或提醒。 |
| `created_at` | `TEXT` | 是 | 系统生成创建时间。 |
| `updated_at` | `TEXT` | 是 | 系统生成更新时间。 |

### 6.4 Todo 数据约束

1. `todo_id` 必须稳定且唯一。
2. `title` 不得为空。
3. `notes` 为空时保存为空字符串。
4. `status` 只允许 `open`、`done` 或 `canceled`。
5. `list_todos` 默认只返回 `open` 状态；用户明确要求全部、已完成或已取消时才调整过滤条件；`all` 只用于查询不过滤状态，不保存到数据库。
6. `due_at` 只保存用户提供的截止时间字符串或空值，不触发提醒、定时任务或自然语言时间解析。
7. 第一版不提供 `delete_todo`；取消 todo 应通过 `status=canceled` 表达。
8. Todo 不保存历史版本或 before / after 快照。

### 6.5 `.memory/MEMORY.md`

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `name` | `string` | 是 | memory 文档标识。 |
| `type` | `string` | 是 | memory 类型，例如 user、project、feedback。 |
| `description` | `string` | 是 | memory 内容说明。 |
| `path` | `string` | 是 | 对应 `.memory/*.md` 路径。 |

### 6.6 `.memory/*.md`

每个 memory 文档必须包含 frontmatter：`name`、`type`、`description`。Memory 文档用于 Agent 协作行为，不得作为 Q&A 回答事实来源。

### 6.7 `.sessions/<session_id>/transcript.jsonl`

transcript 保存可恢复 messages，包括 user message、assistant message、assistant tool call message 和 tool result message。它用于恢复当前 session，不是长期知识来源。

### 6.8 `.sessions/<session_id>/metadata.json`

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `session_id` | `string` | 是 | 会话 ID。 |
| `title` | `string` | 是 | 会话标题。 |
| `title_source` | `string` | 是 | `auto` 或 `user`。 |
| `created_at` | `string` | 是 | 创建时间。 |
| `updated_at` | `string` | 是 | 更新时间。 |

### 6.9 `.sessions/<session_id>/summary.md`

`summary.md` 是长 transcript compact 后的恢复摘要，不是长期事实来源。

格式示例：

```markdown
# Session Summary

Conversation Focus:
- 本会话主要围绕本地 Q&A 知识库 Agent 的上下文恢复行为展开。

User Preferences:
- 用户希望文档只记录稳定设计边界。

Relevant Decisions:
- session summary 只能用于恢复当前会话上下文。
- session summary 不得作为 Q&A 知识来源。

Recent State:
- 最近讨论集中在 transcript 恢复、summary 降级和 runtime messages 边界。
```

### 6.10 Compact Record

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `artifact_path` | `string` | 是 | 原始 artifact 路径。 |
| `summary` | `string` | 是 | 压缩摘要。 |
| `relevance` | `string` | 是 | 与当前任务的相关性说明。 |
| `must_keep` | `boolean` | 是 | 是否必须保留。 |

### 6.11 Memory Candidate

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `type` | `string` | 是 | 候选类型。 |
| `content` | `string` | 是 | 候选内容。 |
| `reason` | `string` | 是 | 提取原因。 |
| `confidence` | `number` | 是 | 置信度。 |

### 6.12 v0.2-v0.7 规划数据模型

1. v0.4 引入 Qdrant 语义索引和 `is_vectorized`。
2. v0.5 引入必填 `category`。
3. v0.6 合并仍以 SQLite 卡片为事实对象，不保存历史版本。
4. v0.7 Kuzu 图谱只保存候选实体关系和来源链接，不替代 `qa_cards`。

---

## 7. 失败模式与降级策略

| 失败模式 | 触发条件 | Agent 行为 | 用户反馈 |
|---|---|---|---|
| 检索为空 | 检索工具返回空 cards | 不编造答案 | 说明本地知识库中没有找到足够依据 |
| 检索结果不相关 | 候选卡片无法支持问题 | 不基于弱证据回答 | 说明没有足够可靠依据 |
| 读取卡片失败 | `read_qa_card` 找不到目标或数据库错误 | 不引用该卡片 | 说明来源读取失败 |
| 工具执行失败 | 工具返回 `ok: false` 或抛错 | 不声称动作成功 | 展示失败原因 |
| Todo 不存在 | `update_todo` 找不到目标 | 不声称已更新 | 说明目标 todo 不存在 |
| 高风险工具需确认 | 权限策略返回 `ask` | 等待用户确认 | 展示操作摘要和风险说明 |
| 用户拒绝高风险工具 | 用户未批准操作 | 不执行 handler | 说明操作未执行 |
| LLM 可重试故障 | 网络错误、timeout、HTTP 429、500 或 503 | 有限重试 | 说明模型调用失败，可稍后重试 |
| LLM 不可重试错误 | HTTP 400、401、402、422 或响应解析失败 | 不重试，不进入工具流程 | 展示明确失败原因 |
| 配置缺失 | 缺少 `DEEPSEEK_API_KEY` 等必需配置 | 不启动真实 Agent 调用 | 提示用户设置配置 |
| Memory 读取失败 | memory index 或文档不可读 | 跳过该 memory，继续主流程 | 说明 memory 未注入 |
| Transcript 恢复失败 | transcript 缺失或格式非法 | 使用空 messages 或降级恢复 | 说明 session 未完整恢复 |
| Summary 生成失败 | summarizer 多次失败 | 使用 first N + recovery notice + recent N | 说明 summary 降级 |
| Artifact 落盘失败 | compact artifact 无法写入 | 降级为不 compact 或保留原始结果 | 说明 compact artifact 未保存 |
| Memory candidate 失败 | 候选生成异常 | 不写入长期 memory | 可通过事件或日志说明失败 |
| Web session 非法 | session_id 为空、过长或包含路径穿越字符 | 拒绝读取或创建 session | 展示 session 无效 |
| Web API 失败 | AgentLoop、session 或卡片读取失败 | 返回结构化错误 | HTML 展示失败说明 |
| 日志写入失败 | JSONL 日志不可写、队列满或 flush 超时 | 不阻断 Agent 主流程 | stderr 最多提示一次 |

- **通用降级原则**:
  1. 工具失败时不得假装已完成。
  2. 依据不足时必须明确说明。
  3. 未落库内容不得作为长期记忆引用。
  4. Agent memory 失败不得阻断 Q&A 主流程。
  5. Todo 工具失败不得阻断 Q&A 主流程。
  6. Session transcript / summary 失败不得被解释为本地知识库缺少依据。
  7. Compact 失败不得丢失回答所需证据。
  8. Memory candidate 只是候选事件；当前实现不得声称 Agent 已经记住。
  9. Web API 失败时必须返回结构化错误，不得伪造成功状态。
  10. 日志不得记录 API key、完整 prompt、完整 messages、secret 或未声明为可展示的内部 payload。

---

## 8. 测试要求

- **单元测试**:
  1. Q&A Repository 覆盖保存、读取、检索、更新、删除、最近列表和 category 约束。
  2. Qdrant 语义索引覆盖写入、检索、重建和失败降级。
  3. Q&A tool handler 覆盖必填字段、非法输入、结构化错误和展示字段。
  4. Tool Dispatcher 覆盖工具分发、未知工具、权限策略和展示字段筛选。
  5. LLM Client 覆盖 streaming、tool call 聚合、usage、可重试错误和不可重试错误。
  6. Todo Repository 覆盖保存、查询、更新、状态约束和非法输入。
  7. Todo tool handler 覆盖必填字段、非法输入、结构化错误和展示字段。
  8. Memory repository 覆盖 index、document、frontmatter 和非法格式。
  9. Session repository 覆盖 transcript、metadata、summary、restore 和非法 session_id。
  10. Tool result compactor 覆盖 artifact 落盘、compact record 和失败降级。
  11. Memory candidate extractor 覆盖只生成候选、不写入长期 memory。

- **集成测试**:
  1. Agent Loop 能执行 fake LLM tool call 并回填 tool result。
  2. 保存后再搜索能召回同一张卡片。
  3. Agent 最终回答只引用本轮真实工具证据。
  4. Agent Loop 能在 usage 阈值和上下文超限时触发 runtime compact。
  5. CLI Runtime 能持续处理输入、退出、错误和权限确认。
  6. Web Runtime 能处理流式聊天、session 隔离、历史恢复和卡片浏览。
  7. Web 高风险操作必须通过阻断式确认流程。
  8. JSONL Logger 异步写入运行事件，且失败不阻断主流程。
  9. Todo 保存后查询能召回同一条待办，更新后能读取最新状态。

- **回归测试**:
  1. 检索为空时不会生成虚假来源。
  2. 工具失败时不会返回保存成功。
  3. Q&A 检索不得混入 `.memory/*.md`。
  4. Q&A 来源证据不得混入 todo 工具结果。
  5. `.sessions/<session_id>/summary.md` 和 compact artifact 不得作为 Q&A 回答来源。
  6. Memory candidate 未写入时不得声称已经记住。
  7. 日志不得输出 API key、完整 system prompt 或完整 messages。
  8. Web UI 不得展示完整内部 payload。
  9. 高风险工具被拒绝、超时、刷新或 SSE 断连时不得执行 handler。
  10. 多个 Web session 不得共享 runtime `messages[]`。
  11. Web Markdown renderer 不得渲染未允许的 HTML 标签。

- **验收清单**:
  1. 符合本文档定义的能力边界。
  2. SQLite `qa_cards` 是 Q&A 知识库唯一事实源。
  3. 工具契约稳定、可测、可审计。
  4. DeepSeek 只出现在薄 LLM Client 中。
  5. Q&A 知识库和 Agent memory 保持分离。
  6. Q&A 知识库和 todo 保持分离。
  7. session summary 和 compact artifact 只用于上下文恢复，不作为长期事实。
  8. CLI / Web Runtime 不绕过 AgentLoop 和 Tools。
  9. 失败场景不会编造结果或伪造来源。

---

## 9. 变更记录

| 日期 | 变更内容 | 变更原因 | 提交 |
|---|---|---|---|
| `2026-05-30` | 新增本地个人 Q&A 知识库 Agent 开发上下文 | 锁定第一版 Agent 设计边界和实现验收依据 | `TBD` |
| `2026-05-31` | 补充 Agent memory、session memory、context compact 和 memory candidate 设计边界 | 锁定记忆管理契约 | `TBD` |
| `2026-06-02` | 补充 Web Runtime、Chat + Cards UI 和 agent_factory 设计边界 | 支持本地浏览器聊天入口和基础 Q&A 卡片浏览 | `TBD` |
| `2026-06-07` | 将工具列表、上下文压缩、memory candidate 和 Web 状态调整为当前代码实现边界 | 修正内部机制与 LLM 可调用工具边界 | `TBD` |
| `2026-06-13` | 补充 DeepSeek streaming、`answer_delta`、Web 流式聊天接口和日志过滤边界 | 支持实时流程展示和最终回答流式输出 | `TBD` |
| `2026-06-16` | 明确 Agent 开发上下文只记录稳定设计边界，不记录任务计划 | 区分 Agent 设计约束与 AI Coding 协作过程 | `TBD` |
| `2026-06-20` | 扩展 `detect_duplicate_cards` 支持 `scope=all` 全库查重 | 避免 Agent 逐张卡片循环调用查重工具 | `TBD` |
| `2026-06-25` | 按模板章节整理正文内容并压缩重复描述 | 保持模板架构不变，提升设计文档可读性和维护性 | `TBD` |
| `2026-06-26` | 补充本地 todo 工具和数据边界 | 支持聊天内待办保存、查询和更新闭环 | `TBD` |
