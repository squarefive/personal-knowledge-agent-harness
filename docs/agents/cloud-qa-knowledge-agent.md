---
module: "cloud-qa-knowledge-agent"
title: "云端个人 Q&A 知识库"
language: "Python"
agent_type: "Tool-Using Agent / RAG Agent"
last_updated: "2026-06-28"
---

# 云端个人 Q&A 知识库 Agent 开发上下文

> **文档定位**
> 本文档是面向人类开发者和 AI Coding 工具的 Agent 开发上下文文档。
> 它用于约束云端个人 Q&A 知识库 Agent 的角色定位、能力边界、Harness 架构、可调用工具、上下文来源、核心业务流、数据模型和测试要求。
> 本文档不是终端用户说明，也不是运行时 Prompt。
> 本文档只记录可长期维护的 Agent 设计边界。
> 本文档不得记录单次任务计划、临时实施步骤、Git 分支安排、工作进度或当前对话待办。
> 任务计划应按照协作规约在当前对话中单独输出。

> **AI 阅读契约**
> AI Coding 工具在生成、修改或重构代码时，必须遵守本文档定义的角色边界、工具边界、数据边界和业务流程。
> 不得擅自扩大 Agent 权限，不得绕过声明的 Tool / Service / Repository 直接操作数据库、文件系统、外部接口或其他底层资源。
> 不得新增未声明的核心流程、外部依赖、高风险操作或数据写入行为。
> 涉及本 Agent 的新增、修改或重构时，AI Coding 工具必须先读取本文档，并以本文档作为实现边界和验收依据。
> 如果实现前发现本文档与目标需求不一致，或需要调整 Agent 的角色边界、工具契约、数据模型、核心流程、外部依赖、权限规则等设计内容，必须先修改本文档，并将文档变更提交到本地 Git；在文档版本被锁定后，才能开始修改代码。
> 禁止在同一次提交中混合 Agent 设计文档变更和对应代码实现变更，除非只是修正文档中的错别字、路径或示例。

---

## 1. Agent 定位与能力边界

- **背景**:
  本项目当前 runtime 是 cloud-only Web 服务。旧本地个人 Q&A 知识库只作为历史来源和 Q&A 一次性迁移输入，不再作为运行时降级路径。云端化目标是让同一个知识资产闭环通过账号访问、服务端持久化和用户级隔离运行，同时继续保持可追溯回答和诚实拒答。

- **核心价值**:
  通过账号化 Web 服务，把用户录入的 Q&A、todo、session 和用户偏好记忆安全隔离地保存在云端 PostgreSQL / pgvector 中，并让 Agent 只基于授权用户的数据回答。

- **Agent 角色**:
  本 Agent 是 cloud-only 云端个人 Q&A 知识库 Agent，负责理解用户意图、调用声明工具读写知识和任务数据、基于证据回答；账号注册、登录、验证码、会话身份和权限校验由 Web / Auth / Service 层负责。

- **核心目标**:
  1. 只提供 cloud-only Web runtime，不提供 CLI、本地 Web、SQLite / Qdrant、`.sessions/` 或 `.memory/` runtime fallback。
  2. 支持云端账号化访问，但当前只允许 `1033795760@qq.com` 登录和使用。
  3. 使用邮箱验证码登录，不做密码登录，不做 magic link。
  4. 使用 PostgreSQL 作为事实库，使用 pgvector 保存 Q&A 语义向量。
  5. 所有 Q&A、todo、session 和 user-preference memory 业务读写必须经过认证用户上下文并执行用户隔离。
  6. Tool schema 不向模型暴露 `user_id`，用户身份由服务端上下文注入。
  7. DeepSeek 请求只使用非隐私、不可反推出邮箱的 `llm_provider_user_id`。
  8. 基于本轮真实工具结果回答并引用来源；依据不足时明确拒答。

- **包含能力**:
  1. 录入、检索、读取、更新、删除、列出、查重和合并当前用户的 Q&A 卡片。
  2. 使用 PostgreSQL 关键词检索与 pgvector 语义召回进行 hybrid 检索。
  3. 保存、查询和更新当前用户的 todo 待办项。
  4. 恢复当前用户的 conversation session，并在同一 session 内防止并发重入。
  5. 读取当前用户的 user-preference memory，用于协作偏好和长期行为约束。
  6. 生成 memory candidate 事件；是否写入长期偏好记忆必须走服务端确认边界。
  7. 通过已认证 cloud-only Web Runtime 提供聊天、session 历史和 Q&A 卡片浏览能力。

- **不包含能力**:
  1. Agent loop 不承载账号系统、验证码发送、登录态签发或用户准入判断。
  2. 不做密码登录，不做 magic link，不开放多用户注册。
  3. 不在 tool schema、prompt、tool result 或日志中暴露 `user_id`、邮箱验证码、SMTP 密码、API key 或数据库凭据。
  4. 不使用生产明文 `.env` 保存 secrets；生产 secrets 必须由部署环境或受控 secret 机制注入。
  5. HTTP 只允许作为临时部署阶段；长期对外访问必须切换到 HTTPS。
  6. 不引入 Redis、KMS、多副本运行、管理后台或复杂迁移框架作为当前边界。
  7. 旧 SQLite 迁移只迁 Q&A；不迁旧 `.sessions/`、Qdrant、todo 或本地 memory 数据。
  8. 旧 SQLite、Qdrant、`.sessions/` 和 `.memory/` 不作为 PostgreSQL / pgvector 不可用时的 runtime fallback。
  9. CLI 和旧本地 Web 入口不属于稳定 runtime 边界。
  10. 不做 Markdown Wiki、文件监听、自动索引、周报、日报或多 Agent。

- **行为约束**:
  1. 所有业务数据读写必须带服务端解析出的当前用户身份，并在 Repository / Service 层执行隔离。
  2. Repository / Service 层的业务读写必须使用 PostgreSQL / pgvector，不得回退到旧 SQLite、Qdrant 或文件型 session / memory。
  3. LLM 只能看到业务所需内容和工具 schema，不得看到服务端 `user_id` 或登录凭据。
  4. 工具返回的 `card_id`、`todo_id`、`session_id` 必须限定在当前用户可访问范围内。
  5. 声称基于知识库回答、引用 `card_id` 或展示来源区块时，必须有本轮真实工具证据。
  6. Todo、session、user-preference memory、compact summary 和 LLM 临时输出不得作为 Q&A 回答事实来源。
  7. 高风险 Q&A 操作必须经过 permission gate；服务端身份校验不得由模型决定。

---

## 2. Harness 架构与代码边界

> 本节说明 Agent Harness 的组成，以及各层职责边界。

- **Agent Loop 职责**:
  - 接收已认证 Web Runtime 传入的用户输入、session 上下文和服务端用户上下文。
  - 构建 runtime `messages[]`、调用 Prompt Builder、调用 LLM Client、解析 tool calls。
  - 通过 Tool Dispatcher 执行工具并回填 tool result。
  - 基于本轮工具结果执行来源证据校验，生成最终回答和结构化事件。
  - 不处理邮箱验证码、登录态、cookie、session token 或账号准入。

- **Web / Auth 边界**:
  - Web / Auth 层负责邮箱验证码发送、验证码校验、登录态签发、当前用户解析和唯一允许邮箱校验。
  - 当前唯一允许账号是 `1033795760@qq.com`。
  - 验证码是短期登录凭证，不是 Agent 可见上下文，不得进入 Prompt、tool schema 或 DeepSeek payload。
  - 后端必须阻止同一用户同一 session 的并发 Agent run 重入。

- **Prompt Builder 职责**:
  - 拼接身份、行为规则、证据纪律、权限边界、记忆边界、能力边界、回答格式和拒答规则。
  - 可注入当前用户可见的 session summary 和 user-preference memory 摘要。
  - 不保存业务数据，不承担身份认证或用户隔离职责。
  - 工具字段语义优先写入 tool schema；prompt 只承载跨工具的模型行为规则。

- **Tools 职责**:
  - 作为 Agent 可执行知识库、todo 和 memory 动作的唯一入口。
  - Tool schema 不包含 `user_id`；handler 从服务端 tool context 读取当前用户身份。
  - 对输入非法、权限不足、跨用户访问、底层失败返回结构化错误。

- **Services / Repositories 职责**:
  - Repository 负责 PostgreSQL / pgvector 的真实读写，并把用户隔离作为查询条件和写入约束。
  - Service 负责 hybrid 检索、重复检测、session 恢复、上下文压缩、memory candidate 提取和业务校验。
  - Tools 必须通过 Service / Repository 完成底层操作，不复制数据库逻辑。

- **Storage / External API 职责**:
  - PostgreSQL 保存用户、Q&A、todo、session、user-preference memory、验证码和运行元数据。
  - pgvector 保存 Q&A 语义向量；权威 Q&A 文本仍在 PostgreSQL 事实表中。
  - 旧 SQLite 只作为 Q&A 一次性迁移来源，不参与 cloud-only runtime 读写。
  - DeepSeek 负责主 LLM 调用，调用时只传非隐私 `llm_provider_user_id`。
  - 邮件服务只用于发送验证码，不进入 Agent loop。
  - 生产 secrets 必须来自部署环境或受控 secret 注入，不使用生产明文 `.env`。

- **禁止绕过的边界**:
  1. Agent Loop 不得直接操作数据库、邮件服务、登录态或验证码存储。
  2. LLM 输出不得被视为已持久化事实。
  3. 工具不得绕过服务端用户上下文或权限规则执行高风险操作。
  4. Web Runtime 不得绕过 AgentLoop、Tools 或 Service 执行业务动作。
  5. CLI、本地 Web、SQLite / Qdrant、`.sessions/` 或 `.memory/` 不得作为 cloud-only runtime fallback。
  6. 未在本文档声明的核心依赖不得擅自引入。

- **核心文件 / 目录**:

| 路径 | 职责 |
|---|---|
| `src/personal_knowledge_agent/agent_bootstrap/` | 运行配置和跨模块组件装配。 |
| `src/personal_knowledge_agent/agent_runtime/` | Agent loop、LLM 调用、tool call、最终回答、来源校验和事件发射。 |
| `src/personal_knowledge_agent/agent_context/` | Prompt、memory、session transcript、summary 和 compact 管理。 |
| `src/personal_knowledge_agent/agent_tools/` | LLM 可调用工具 adapter。 |
| `src/personal_knowledge_agent/postgres/` | cloud-only runtime 的 PostgreSQL / pgvector 数据访问、schema 和 session adapter。 |
| `src/personal_knowledge_agent/qa_data_access/` | 旧 SQLite / Qdrant Q&A 模块；只可作为 Q&A 一次性迁移来源或遗留代码参考，不是 runtime fallback。 |
| `src/personal_knowledge_agent/todo_data_access/` | 旧 SQLite todo 模块；不属于 cloud-only runtime 数据源。 |
| `src/personal_knowledge_agent/tool_runtime/` | Tool dispatcher、tool model 和权限策略。 |
| `src/personal_knowledge_agent/llm_clients/` | LLM provider client。 |
| `src/personal_knowledge_agent/apps/web/` | Web Runtime 和静态 UI。 |

---

## 3. 可调用工具与工具契约

### 3.1 工具列表

| 工具名 | 工具职责 | 调用时机 | 是否有副作用 | 是否需要确认 |
|---|---|---|---|---|
| `save_qa_card` | 保存当前用户的一张 Q&A 卡片 | 用户明确提供可保存 Q&A 时 | 是 | 否 |
| `search_qa_cards` | 检索当前用户的 Q&A | 用户提问或查找知识时 | 否 | 否 |
| `hybrid_search_qa_cards` | 关键词与 pgvector 语义召回混合检索当前用户 Q&A | 需要更高召回质量时 | 否 | 否 |
| `read_qa_card` | 读取当前用户可访问的卡片详情 | 需要引用或核对具体卡片时 | 否 | 否 |
| `update_qa_card` | 更新当前用户已有卡片 | 用户明确要求修改卡片时 | 是 | 是 |
| `delete_qa_card` | 删除当前用户已有卡片 | 用户明确要求删除卡片时 | 是 | 是 |
| `list_recent_cards` | 列出当前用户最近卡片 | 用户要求查看最近知识时 | 否 | 否 |
| `detect_duplicate_cards` | 检测当前用户疑似重复卡片 | 合并前或用户要求查重时 | 否 | 否 |
| `merge_qa_cards` | 合并当前用户确认的重复卡片 | 用户确认合并时 | 是 | 是 |
| `rebuild_qa_semantic_index` | 重建当前用户或受控范围内的语义索引 | 系统维护或索引修复时 | 是 | 否 |
| `create_todo` | 保存当前用户的一条 todo | 用户明确要求记录行动项时 | 是 | 否 |
| `list_todos` | 查询当前用户 todo | 用户要求查看、搜索或核对 todo 时 | 否 | 否 |
| `update_todo` | 更新当前用户 todo | 用户要求修改 todo 内容或状态时 | 是 | 是 |
| `list_memory_index` | 读取当前用户 memory 索引 | 需要理解长期协作偏好时 | 否 | 否 |
| `read_memory` | 读取当前用户指定 memory | memory index 显示相关时 | 否 | 否 |

### 3.2 工具契约

#### 通用契约

- Tool schema 不包含 `user_id`、邮箱、验证码、session token、API key 或 secret 字段。
- Handler 必须从服务端 tool context 获取当前用户身份，并在 Service / Repository 层校验数据归属。
- 输出只包含模型回答所需的业务字段和结构化错误，不暴露内部主键、凭据或跨用户数据。
- 跨用户读取、更新或删除必须返回结构化权限错误，不得表现为成功。

#### `save_qa_card`

- **职责**: 保存当前用户提供的一张 Q&A 卡片。
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

- **副作用**: 写入当前用户的 PostgreSQL Q&A 事实表，并尽力写入 pgvector 语义向量。
- **失败处理**: 必填字段缺失、字段类型非法、用户上下文缺失、数据库写入失败或向量写入失败时返回结构化错误。

#### `hybrid_search_qa_cards`

- **职责**: 使用关键词检索与 pgvector 语义召回合并排序当前用户 Q&A。
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

- **副作用**: 可调用 embedding 服务并读取 pgvector；不修改事实库。
- **失败处理**: 语义召回失败时可降级为关键词检索；整体失败时返回结构化错误。

#### Q&A 维护工具

- **适用工具**: `read_qa_card`、`update_qa_card`、`delete_qa_card`、`list_recent_cards`、`detect_duplicate_cards`、`merge_qa_cards`、`rebuild_qa_semantic_index`。
- **职责**: 读取或维护当前用户的 Q&A 数据。
- **输入**: 只接收业务字段，例如 `card_id`、`query`、`limit`、`source_card_ids`、可更新内容字段和维护参数。
- **输出**: 返回 `ok`、业务对象或对象列表、可展示 ID、时间戳和 `error`。
- **副作用**: 读取工具无副作用；更新、删除、合并和索引重建会修改 PostgreSQL / pgvector。
- **失败处理**: 高风险写操作必须经过 permission gate；跨用户目标、目标不存在或用户拒绝时不得修改数据。

#### Todo 工具

- **适用工具**: `create_todo`、`list_todos`、`update_todo`。
- **职责**: 保存、查询和更新当前用户的 todo 待办项。
- **输入**: 只接收 `title`、`notes`、`due_at`、`status`、`todo_id`、`query`、`limit` 等业务字段。
- **输出**: 返回 `ok`、`todo` 或 `todos`、可展示 ID、时间戳和 `error`。
- **副作用**: `create_todo` 和 `update_todo` 写入 PostgreSQL；`list_todos` 无副作用。
- **失败处理**: title 缺失、状态非法、目标不存在、跨用户目标、用户拒绝确认或数据库失败时返回结构化错误；用户拒绝确认时不得修改 todo。

#### Memory 工具

- **适用工具**: `list_memory_index`、`read_memory`。
- **职责**: 读取当前用户的 user-preference memory。
- **输入**: `list_memory_index` 不需要业务输入；`read_memory` 接收 memory 标识。
- **输出**: 返回 `ok`、memory index 或 memory 文档摘要、`error`。
- **副作用**: 无。
- **失败处理**: memory 不存在、格式非法、跨用户目标或读取失败时返回结构化错误，不阻断 Q&A 主流程。

### 3.3 当前非工具机制

以下能力属于 Harness 或 Web / Auth 内部机制，不作为 LLM 可自由调用工具暴露：

1. 邮箱验证码发送和校验。
2. 登录态签发、解析和用户准入。
3. 服务端用户上下文注入。
4. 同一 session 防重入。
5. runtime context compact。
6. transcript restore 和 session summary restore。
7. JSONL 或结构化运行日志写入。
8. memory candidate 生成事件。
9. Web session 管理和 SSE 事件分发。
10. 最近一次 prompt usage ratio 记录和 Web Context UI 展示。

---

## 4. 上下文来源与记忆边界

- **运行时上下文来源**:
  1. 用户当前输入。
  2. 当前 session 的 runtime `messages[]`。
  3. Prompt Builder 注入的 Agent 规则。
  4. 本轮真实 tool result。
  5. 当前用户可见的 user-preference memory。
  6. 当前用户当前 session 的 summary 和 recent messages。

- **长期记忆来源**:
  1. PostgreSQL Q&A 表是 Q&A 知识库事实源。
  2. PostgreSQL todo 表是 todo 事实源。
  3. PostgreSQL session 表是当前用户会话恢复来源。
  4. PostgreSQL user-preference memory 表是 Agent 协作偏好来源。
  5. 旧 `.sessions/` 和 `.memory/` 文件不是 cloud-only runtime 的 session 或 memory 来源。

- **不得作为长期记忆的内容**:
  1. LLM 临时输出。
  2. 未通过工具保存的对话内容。
  3. tool result compact summary。
  4. session summary。
  5. memory candidate 事件。
  6. 邮箱验证码、登录态、SMTP 配置或任何 secret。

- **上下文裁剪规则**:
  1. 长 session 优先使用 summary + recent messages 恢复。
  2. 大 tool result 应压缩为 compact record 或服务端 artifact 引用，不把完整内部 payload 暴露给模型。
  3. compact 只能缩减当前上下文窗口，不得替代长期记忆写入。
  4. 回答 Q&A 问题时必须优先保留本轮真实检索证据。
  5. DeepSeek payload 使用非隐私 `llm_provider_user_id`，不得使用邮箱或服务端 `user_id`。

---

## 5. 核心业务流

### 5.1 邮箱验证码登录

1. 用户在 Web 输入邮箱。
2. Auth 层校验邮箱是否为 `1033795760@qq.com`。
3. Auth 层生成短期验证码并通过邮件服务发送。
4. 用户提交验证码后，Auth 层校验并签发登录态。
5. Web Runtime 通过登录态解析当前用户。

- **成功条件**: 邮箱在允许列表内，验证码有效，登录态签发成功。
- **失败条件**: 邮箱不允许、验证码错误或过期、邮件发送失败、登录态签发失败。
- **用户可见反馈**: 展示登录成功或明确失败原因；不得暴露验证码存储、SMTP secret 或内部错误详情。

### 5.2 录入 Q&A

1. 已认证用户发送包含可保存 Q&A 的消息。
2. Agent 提取 question、answer、summary、keywords、category 和 source_type。
3. Agent 调用 `save_qa_card`，tool context 注入当前用户身份。
4. Service 写入当前用户的 PostgreSQL Q&A 事实表，并尽力写入 pgvector。
5. Agent 基于 tool result 告知用户保存结果。

- **成功条件**: 工具返回 `ok: true` 和当前用户的 `card_id`。
- **失败条件**: 输入缺失关键字段、用户上下文缺失、工具返回错误或数据库写入失败。
- **用户可见反馈**: 成功时展示 `card_id`；失败时展示失败原因，不得声称已保存。

### 5.3 回答问题

1. Agent 判断用户正在询问知识库内容。
2. Agent 调用 `search_qa_cards` 或 `hybrid_search_qa_cards`。
3. 必要时调用 `read_qa_card` 核对完整卡片。
4. Tool 只能返回当前用户可访问的卡片。
5. Agent 只基于本轮真实工具结果组织回答和来源区块。

- **成功条件**: 检索结果与用户问题相关，且足以支持回答。
- **失败条件**: 检索为空、结果不相关、工具失败或来源不足。
- **用户可见反馈**: 依据不足时明确说明知识库中没有找到足够依据。

### 5.4 维护 Q&A 和 todo

1. Agent 识别用户的更新、删除、查重、合并或 todo 维护意图。
2. Agent 调用对应工具；高风险 Q&A 写操作先触发 permission gate。
3. Handler 使用服务端用户上下文限定目标数据。
4. Agent 基于 tool result 返回维护结果。

- **成功条件**: 对应工具返回 `ok: true`，且目标属于当前用户。
- **失败条件**: 用户拒绝、权限超时、跨用户目标、工具失败或目标不存在。
- **用户可见反馈**: 展示已执行动作和目标 ID；未执行时明确说明原因。

### 5.5 Session 恢复、防重入和上下文压缩

1. Web Runtime 解析当前用户和 session。
2. 后端检查同一用户同一 session 是否已有运行中的 Agent run。
3. Runtime 从当前用户当前 session 恢复 messages 或 summary + recent messages。
4. LLM usage 达到阈值或上下文超限时执行 runtime compact。
5. LLM 返回 usage 后，Web Runtime 将最近一次 prompt usage ratio 记录到当前用户当前 session metadata，用于刷新后恢复 Context UI 展示。
6. turn 结束后释放 session run 锁并记录结果。

- **成功条件**: 单个 session 同时只有一个运行中的 Agent run，恢复后的上下文足以继续对话，刷新后可展示当前 session 最近一次真实 prompt usage ratio。
- **失败条件**: session 非法、跨用户 session、重复提交、summary 生成失败或 compact 失败。
- **用户可见反馈**: 对重复提交返回明确忙碌状态；恢复或 compact 降级不得解释为知识库缺少依据；无 usage 记录时 Context UI 应展示未知状态而不是伪造 0%。

### 5.6 旧数据迁移

1. 只迁移旧 SQLite 中的 Q&A 卡片；SQLite 不是迁移后的 runtime fallback。
2. 为迁入卡片绑定当前唯一允许用户。
3. 为迁入 Q&A 生成或重建 pgvector 语义向量。
4. 不迁移旧 `.sessions/`、Qdrant、todo 或本地 memory。

- **成功条件**: Q&A 事实数据迁入 PostgreSQL，语义索引可重建或可重试。
- **失败条件**: SQLite 源不可读、字段不兼容、目标写入失败或向量重建失败。
- **用户可见反馈**: 展示迁移数量、失败数量和可重试信息；不得声称未迁移数据已经可用。

---

## 6. 数据模型

### 6.1 用户与登录

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `user_id` | server-generated id | 是 | 服务端内部用户标识，不暴露给 LLM。 |
| `email` | text | 是 | 当前只允许 `1033795760@qq.com`。 |
| `llm_provider_user_id` | text | 是 | 传给 DeepSeek 的非隐私标识，不得包含邮箱或可反推邮箱的信息。 |
| `created_at` | timestamp | 是 | 创建时间。 |
| `updated_at` | timestamp | 是 | 更新时间。 |

验证码数据必须短期有效、可失效、不可进入 Prompt 或日志明文。当前不定义密码哈希字段，不定义 magic link token 字段。

### 6.2 Q&A 卡片

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `card_id` | public id | 是 | 当前用户范围内可展示的卡片 ID。 |
| `user_id` | server id | 是 | 数据归属；只在服务端使用，不暴露给 LLM。 |
| `question` | text | 是 | 用户提供的原始问题。 |
| `answer` | text | 是 | 用户提供的原始答案。 |
| `summary` | text | 是 | 模型生成摘要。 |
| `keywords` | json / array | 是 | 关键词数组。 |
| `category` | text | 是 | Q&A 语义主分类。 |
| `source_type` | text | 是 | 来源类型。 |
| `embedding` | vector | 否 | pgvector 语义向量。 |
| `created_at` | timestamp | 是 | 创建时间。 |
| `updated_at` | timestamp | 是 | 更新时间。 |

### 6.3 Todo、Session 与 Memory

| 数据 | 必须隔离字段 | 说明 |
|---|---|---|
| todo | `user_id`, `todo_id` | 保存 title、notes、status、due_at、created_at、updated_at。 |
| session | `user_id`, `session_id` | 保存 session metadata、transcript / messages、summary、运行状态、最近一次 prompt usage ratio 和更新时间。 |
| user-preference memory | `user_id`, memory id | 保存协作偏好、长期行为约束和可读摘要，不作为 Q&A 事实来源。 |

### 6.4 数据约束

1. Q&A、todo、session、user-preference memory 的所有读取和写入必须带用户隔离。
2. PostgreSQL Q&A 表是 Q&A 事实源；pgvector 只负责语义召回。
3. Todo 不得作为 Q&A 回答来源证据。
4. Session summary 和 compact record 只用于上下文恢复，不是长期事实。
5. Session 最近一次 prompt usage ratio 只用于 Web Context UI 展示和上下文压缩状态感知，不是 Q&A 事实来源。
6. 更新卡片不要求保存历史版本；删除卡片是当前用户范围内的删除。
7. 旧 SQLite 迁移只迁 Q&A，不迁旧 session、Qdrant、todo 或本地 memory。
8. 当前阶段不引入 Redis、KMS、多副本运行、管理后台或复杂迁移框架。

---

## 7. 失败模式与降级策略

| 失败模式 | 触发条件 | Agent / 系统行为 | 用户反馈 |
|---|---|---|---|
| 邮箱不允许 | 登录邮箱不是 `1033795760@qq.com` | Auth 拒绝登录 | 说明当前账号不允许访问 |
| 验证码失败 | 验证码错误、过期或已使用 | Auth 拒绝签发登录态 | 说明验证码无效或已过期 |
| 邮件发送失败 | SMTP 或邮件服务失败 | 不创建有效登录态 | 说明验证码发送失败 |
| 用户上下文缺失 | Tool handler 未收到服务端用户上下文 | 拒绝执行工具 | 展示认证状态异常 |
| 跨用户访问 | 请求目标不属于当前用户 | 拒绝读取或修改 | 说明目标不存在或无权访问 |
| 同 session 重入 | 同一用户同一 session 已有 Agent run | 拒绝新 run 或返回忙碌状态 | 提示稍后重试 |
| 检索为空 | 检索工具返回空 cards | 不编造答案 | 说明知识库中没有找到足够依据 |
| 检索结果不相关 | 候选卡片无法支持问题 | 不基于弱证据回答 | 说明没有足够可靠依据 |
| 工具执行失败 | 工具返回 `ok: false` 或抛错 | 不声称动作成功 | 展示失败原因 |
| 高风险工具需确认 | 权限策略返回 `ask` | 等待用户确认 | 展示操作摘要和风险说明 |
| LLM 可重试故障 | 网络错误、timeout、HTTP 429、500 或 503 | 有限重试 | 说明模型调用失败，可稍后重试 |
| Secrets 配置缺失 | 缺少 LLM、邮件或数据库配置 | 不启动对应真实调用 | 提示服务配置不完整 |
| 旧数据迁移部分失败 | 部分 Q&A 写入或向量重建失败 | 保留可重试记录 | 展示成功和失败数量 |

- **通用降级原则**:
  1. 工具失败时不得假装已完成。
  2. 依据不足时必须明确说明。
  3. 未落库内容不得作为长期记忆引用。
  4. 用户隔离失败时必须拒绝业务动作。
  5. Session 恢复失败不得被解释为知识库缺少依据。
  6. 日志不得记录 API key、验证码、SMTP 密码、完整 prompt、完整 messages、secret 或未声明为可展示的内部 payload。
  7. 临时 HTTP 阶段不得扩大为长期生产边界。

---

## 8. 测试要求

- **单元测试**:
  1. Auth 规则覆盖唯一允许邮箱、验证码过期、验证码错误和重复使用。
  2. Repository 覆盖 Q&A、todo、session、memory 的用户隔离查询和写入。
  3. Q&A tool handler 覆盖不接收 `user_id`、从 context 取用户、跨用户目标拒绝和结构化错误。
  4. Hybrid 检索覆盖 PostgreSQL 关键词检索、pgvector 召回、合并排序和降级。
  5. DeepSeek client 覆盖 `llm_provider_user_id` 使用非隐私标识。
  6. Session run guard 覆盖同一用户同一 session 防重入。
  7. Session metadata 覆盖最近一次 prompt usage ratio 的用户隔离写入和读取。
  8. Secrets 配置覆盖生产环境不依赖明文 `.env`。

- **集成测试**:
  1. 邮箱验证码登录成功后可启动 Web chat。
  2. 未认证请求不能调用 Agent 或工具。
  3. 保存 Q&A 后只能由同一用户检索和读取。
  4. Agent 最终回答只引用本轮当前用户工具证据。
  5. Todo、session、memory 与 Q&A 来源证据保持分离。
  6. 同一 session 并发请求只允许一个 Agent run 执行。
  7. Web session 恢复后可展示当前 session 最近一次真实 prompt usage ratio；无记录时展示未知状态。
  8. 旧 SQLite Q&A 迁移后可在 PostgreSQL / pgvector 中检索。

- **回归测试**:
  1. Tool schema 和 DeepSeek payload 不包含 `user_id`、邮箱验证码、SMTP secret 或数据库凭据。
  2. 检索为空时不会生成虚假来源。
  3. 工具失败时不会返回保存成功。
  4. Q&A 来源证据不得混入 todo、session summary 或 user-preference memory。
  5. HTTP 临时部署不会被文档或代码标记为长期生产方案。
  6. 旧 session、Qdrant、todo 和本地 memory 不会被迁移脚本误迁。

- **验收清单**:
  1. 符合本文档定义的云端账号化和用户隔离边界。
  2. PostgreSQL 是事实源，pgvector 是语义召回索引。
  3. Agent loop 不承载账号系统。
  4. Tool schema 不暴露 `user_id`。
  5. DeepSeek 只接收非隐私 `llm_provider_user_id`。
  6. 生产 secrets 不使用明文 `.env`。
  7. 旧数据迁移范围仅限 Q&A。
  8. CLI、本地 Web、SQLite / Qdrant、`.sessions/` 和 `.memory/` 不承担 runtime 职责。

---

## 9. 变更记录

| 日期 | 变更内容 | 变更原因 | 提交 |
|---|---|---|---|
| `2026-05-30` | 新增本地个人 Q&A 知识库 Agent 开发上下文 | 锁定第一版 Agent 设计边界和实现验收依据 | `TBD` |
| `2026-06-26` | 补充本地 todo 工具和数据边界 | 支持聊天内待办保存、查询和更新闭环 | `TBD` |
| `2026-06-27` | 将 Agent 边界改名并压缩为云端个人 Q&A 知识库边界 | 锁定云端账号化、用户隔离、PostgreSQL / pgvector 和迁移范围 | `TBD` |
| `2026-06-28` | 锁定 cloud-only Web runtime 边界 | 明确 PostgreSQL / pgvector 是唯一业务 runtime，旧本地存储只作 Q&A 一次性迁移来源 | `TBD` |
