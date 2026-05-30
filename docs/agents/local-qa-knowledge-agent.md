---
module: "local-qa-knowledge-agent"
title: "本地个人 Q&A 知识库"
language: "Python"
agent_type: "Tool-Using Agent / RAG Agent"
last_updated: "2026-05-30"
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
  通过工具把用户提供的 Q&A 保存到本地 SQLite，并在后续提问时基于本地检索结果生成可追溯回答。

- **Agent 角色**:  
  本 Agent 是本地个人 Q&A 知识库 Agent，负责判断用户是在录入知识还是提问，并通过工具完成保存、检索、读取和列出最近卡片。

- **核心目标**:
  1. 能保存用户提供的一组 Q&A。
  2. 能从本地 SQLite 检索相关 Q&A 卡片。
  3. 能基于检索结果回答问题并引用来源。
  4. 在依据不足时明确拒答，不编造来源或事实。

- **包含能力**:
  1. 录入用户提供的 Q&A。
  2. 由模型生成 summary 和 keywords。
  3. 通过工具保存 Q&A 卡片到 SQLite。
  4. 通过工具检索、读取和列出 Q&A 卡片。
  5. 基于检索结果组织回答。
  6. 回答时展示 card_id、原始问题、source_type 和 created_at。

- **不包含能力**:
  1. 不做 Markdown Wiki。
  2. 不做文件监听或自动索引。
  3. 不做周报、日报或自动总结。
  4. 不做多 Agent。
  5. 不做向量数据库。
  6. 不做去重合并。
  7. 不做后台任务。
  8. 不做复杂权限系统。

- **行为约束**:
  1. 凡是涉及长期记忆的动作，必须通过工具完成。
  2. Agent 不得声称已经保存、查询或更新实际未通过工具完成的数据。
  3. 回答问题前必须先检索本地知识库。
  4. 没有足够依据时必须明确说明本地知识库中没有找到足够依据。
  5. 回答不得引入无来源外部知识。

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

- **Prompt Builder 职责**:
  - 运行时拼接短 system prompt。
  - 包含身份、行为规则、工具使用规则、回答格式和拒答规则。
  - 不保存业务数据。
  - 不承担数据库读写职责。

- **LLM Client 职责**:
  - 作为 DeepSeek API 的薄适配层。
  - 接收 messages、tools 和 system_prompt。
  - 发起 DeepSeek chat 请求。
  - 将 DeepSeek 响应转换为统一的 LLMResponse。
  - 不包含 Agent 业务判断逻辑。

- **CLI Runtime 职责**:
  - 作为 `python -m personal_knowledge_agent` 的启动入口。
  - 启动时加载 `.env` 和环境变量配置。
  - 初始化 SQLite Store、KnowledgeTools、ToolDispatcher、DeepSeekClient 和 AgentLoop。
  - 进入持续交互循环，读取用户输入并打印 Agent 回复。
  - 支持 `/exit` 和 `/quit` 退出。
  - 不直接操作 SQLite。
  - 不绕过 AgentLoop 调用工具。

- **Tools 职责**:
  - 作为 Agent 可执行动作的唯一入口。
  - 校验工具输入。
  - 调用 SQLite Store 完成保存、检索、读取和列出最近卡片。
  - 将成功、失败和未找到结果统一转换为结构化 tool result。

- **Services / Repositories 职责**:
  - 第一版不单独拆分 Service / Repository。
  - `SQLiteStore` 负责数据库初始化、保存、读取、LIKE 检索和最近列表。
  - `SQLiteStore` 不调用 LLM，不组织最终自然语言回答。

- **Storage / External API 职责**:
  - SQLite 是第一版唯一长期记忆来源。
  - DeepSeek 是第一版 LLM 服务。
  - 第一版不引入向量库、外部知识库或后台任务。

- **Logging 职责**:
  - 使用 Python 标准库 `logging`。
  - 记录 Agent Loop、LLM Client、Tool Dispatcher、Tools 和 SQLite Store 的关键事件。
  - 不记录 API key、完整 headers 或默认完整 prompt/messages。
  - 默认不记录完整 question 和 answer；只记录 card_id、工具名、结果数量、轮次、错误类型等调试信息。

- **禁止绕过的边界**:
  1. Agent Loop 不得直接操作 SQLite。
  2. LLM 输出不得被视为已持久化事实。
  3. Tools 不得绕过 SQLite Store 直接拼接外部副作用。
  4. SQLite Store 不得调用 LLM。
  5. 未在本文档声明的核心依赖不得擅自引入。

- **核心文件 / 目录**:

| 路径 | 职责 |
|---|---|
| `src/personal_knowledge_agent/agent_loop.py` | Agent 最小循环 |
| `src/personal_knowledge_agent/prompt_builder.py` | 构建运行时 system prompt |
| `src/personal_knowledge_agent/llm_client.py` | DeepSeek 薄客户端 |
| `src/personal_knowledge_agent/config.py` | 读取 `.env` 和环境变量，返回运行配置 |
| `src/personal_knowledge_agent/__main__.py` | CLI 持续交互入口 |
| `src/personal_knowledge_agent/tool_dispatcher.py` | 工具分发和错误包装 |
| `src/personal_knowledge_agent/tools.py` | 四个知识库工具 |
| `src/personal_knowledge_agent/schemas.py` | 轻量数据契约 |
| `src/personal_knowledge_agent/sqlite_store.py` | SQLite 初始化、写入、读取、检索 |
| `.knowledge/knowledge.db` | 本地知识库数据库文件 |

---

## 3. 可调用工具与工具契约

### 3.1 工具列表

| 工具名 | 工具职责 | 调用时机 | 是否有副作用 | 是否需要确认 |
|---|---|---|---|---|
| `save_qa_card` | 保存 Q&A 卡片 | 用户明确提供 Q&A 并要求记录时 | 是 | 否 |
| `search_qa_cards` | 检索相关 Q&A 卡片 | 用户提出问题时 | 否 | 否 |
| `read_qa_card` | 读取完整 Q&A 卡片 | 需要核对完整来源时 | 否 | 否 |
| `list_recent_cards` | 列出最近保存卡片 | 用户要求查看最近记录或保存后确认时 | 否 | 否 |

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

- **副作用**:  
  无。

- **失败处理**:  
  limit 非法时使用安全默认值。数据库读取失败时返回 `ok: false`、`error_code` 和 `message`。

---

## 4. 上下文来源与记忆边界

- **运行时上下文来源**:
  1. 用户当前输入。
  2. LLM 当前轮输出。
  3. 工具返回的结构化结果。
  4. Prompt Builder 生成的 system prompt。
  5. `.env` 和环境变量提供的运行配置。

- **长期记忆来源**:
  1. SQLite `qa_cards` 表。

- **不得作为长期记忆的内容**:
  1. 未通过 `save_qa_card` 写入 SQLite 的 LLM 临时输出。
  2. 未落库的对话上下文。
  3. 日志内容。
  4. DeepSeek 响应中未保存到 SQLite 的内容。
  5. `.env` 中的运行配置。

- **配置边界**:
  1. `.env` 只保存运行配置，不是长期知识来源。
  2. `DEEPSEEK_API_KEY` 不得进入 messages、tool result、SQLite 或日志。
  3. `.env` 和 `.knowledge/` 应通过 `.git/info/exclude` 在本地忽略，不要求提交仓库级 `.gitignore`。

- **上下文裁剪规则**:
  1. 第一版优先保留用户当前输入、最近一次 LLM tool call 和 tool result。
  2. 回答必须保留用于引用来源的 card_id、question、source_type 和 created_at。
  3. 不把历史对话当作可靠长期记忆。

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

1. 用户运行 `python -m personal_knowledge_agent`。
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

- **通用降级原则**:
  1. 工具失败时不得假装已完成。
  2. 依据不足时必须明确说明。
  3. 未落库内容不得作为长期记忆引用。
  4. 不得为了回答完整而引入无来源外部知识。

- **日志降级原则**:
  1. Agent Loop 记录轮次、是否收到 tool calls、是否返回 final answer。
  2. LLM Client 记录 model、请求成功或失败、tool_calls 数量，不记录 API key。
  3. Tool Dispatcher 记录 tool name、tool_call_id、成功或失败和耗时。
  4. Tools 记录保存成功的 card_id、检索结果数量和 not_found。
  5. SQLite Store 记录 schema 初始化、插入、搜索数量和数据库错误。
  6. 默认不记录完整 question、answer、prompt、messages。

- **配置安全规则**:
  1. `.env` 必须通过 `.git/info/exclude` 在本地忽略，不要求提交仓库级 `.gitignore`。
  2. 不得把 `.env` 内容打印到日志。
  3. 不得把 DeepSeek key 写入文档、测试快照或数据库。

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

- **集成测试**:
  1. Agent Loop 能接收 fake LLM 的 tool call，执行工具并回填 tool result。
  2. Agent Loop 在 fake LLM 返回 final answer 时能直接结束。
  3. 保存后再搜索能召回同一张卡片。
  4. CLI Runtime 能用 fake input / fake AgentLoop 跑一次输入和退出流程。

- **回归测试**:
  1. 检索为空时不会生成虚假来源。
  2. 工具失败时不会返回保存成功。
  3. 回答来源至少包含 card_id、question、source_type、created_at。
  4. 日志不输出 API key。

- **可选 Live Smoke Test**:
  1. 仅在存在 `DEEPSEEK_API_KEY` 时运行。
  2. 使用 `deepseek-v4-flash` 做真实 DeepSeek 调用。
  3. 完成一次保存 Q&A。
  4. 再完成一次检索回答。
  5. 不把 API key 写入仓库或日志。

- **验收清单**:
  1. 符合本文档定义的能力边界。
  2. SQLite 是第一版唯一长期记忆来源。
  3. 四个工具契约稳定可测。
  4. DeepSeek 只出现在薄 LLM Client 中。
  5. 第一版不包含 Wiki、文件监听、周报、多 Agent、向量库和后台任务。

---

## 9. 变更记录

| 日期 | 变更内容 | 变更原因 | 提交 |
|---|---|---|---|
| `2026-05-30` | 新增本地个人 Q&A 知识库 Agent 开发上下文 | 锁定第一版 Agent 设计边界和实现验收依据 | `TBD` |
