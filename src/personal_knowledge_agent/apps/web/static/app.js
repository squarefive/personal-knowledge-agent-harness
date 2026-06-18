const state = {
  cards: [],
  busy: false,
  sessions: [],
  activeSessionId: null,
  selectedCardId: null,
  leftCollapsed: getStoredBoolean("left_pane_collapsed", window.matchMedia("(max-width: 1080px)").matches),
  rightCollapsed: getStoredBoolean("right_pane_collapsed", window.matchMedia("(max-width: 760px)").matches),
};

const elements = {
  appShell: document.querySelector("#appShell"),
  toggleSessionsButton: document.querySelector("#toggleSessionsButton"),
  toggleCardsButton: document.querySelector("#toggleCardsButton"),
  sessionsList: document.querySelector("#sessionsList"),
  sessionStatus: document.querySelector("#sessionStatus"),
  newSessionButton: document.querySelector("#newSessionButton"),
  renameSessionButton: document.querySelector("#renameSessionButton"),
  activeSessionTitle: document.querySelector("#activeSessionTitle"),
  chatForm: document.querySelector("#chatForm"),
  messageInput: document.querySelector("#messageInput"),
  sendButton: document.querySelector("#sendButton"),
  messages: document.querySelector("#messages"),
  statusText: document.querySelector("#statusText"),
  refreshCardsButton: document.querySelector("#refreshCardsButton"),
  searchForm: document.querySelector("#searchForm"),
  searchInput: document.querySelector("#searchInput"),
  cardsPane: document.querySelector(".cards-pane"),
  cardsTitle: document.querySelector("#cardsTitle"),
  cardsCount: document.querySelector("#cardsCount"),
  cardsList: document.querySelector("#cardsList"),
  cardDetail: document.querySelector("#cardDetail"),
  closeCardDetailButton: document.querySelector("#closeCardDetailButton"),
};

const cardTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const detailTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

applyPaneState();

elements.toggleSessionsButton.addEventListener("click", () => {
  setPaneCollapsed("left", !state.leftCollapsed);
});

elements.toggleCardsButton.addEventListener("click", () => {
  setPaneCollapsed("right", !state.rightCollapsed);
});

elements.chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = elements.messageInput.value.trim();
  if (!message || state.busy || !state.activeSessionId) return;

  appendMessage("user", "你", message);
  const agentMessage = appendAgentRunMessage();
  elements.messageInput.value = "";
  setBusy(true, "Agent 正在处理");

  try {
    await streamChat(message, agentMessage);
    await loadSessions();
    renderActiveSessionTitle();
    await loadRecentCards();
  } catch (error) {
    renderRunError(agentMessage, String(error));
  } finally {
    setBusy(false, "本地 Web UI 已就绪");
  }
});

elements.newSessionButton.addEventListener("click", async () => {
  if (state.busy) return;
  const session = await createSession();
  await activateSession(session.session_id);
});

elements.renameSessionButton.addEventListener("click", async () => {
  if (!state.activeSessionId) return;
  const activeSession = state.sessions.find((session) => session.session_id === state.activeSessionId);
  const nextTitle = window.prompt("重命名会话", activeSession?.title || "");
  if (nextTitle === null) return;
  const response = await fetch(`/api/sessions/${encodeURIComponent(state.activeSessionId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: nextTitle }),
  });
  const result = await response.json();
  if (!result.ok) {
    setBusy(false, result.message || "重命名失败");
    return;
  }
  await loadSessions();
  renderActiveSessionTitle();
});

elements.messageInput.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing || state.busy) {
    return;
  }
  event.preventDefault();
  elements.chatForm.requestSubmit();
});

elements.searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = elements.searchInput.value.trim();
  if (!query) {
    await loadRecentCards();
    return;
  }
  await searchCards(query);
});

elements.refreshCardsButton.addEventListener("click", async () => {
  elements.searchInput.value = "";
  await loadRecentCards();
});

elements.closeCardDetailButton.addEventListener("click", closeCardDetail);

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

async function initializeApp() {
  await loadSessions();
  const savedSessionId = window.localStorage.getItem("active_session_id");
  const savedSession = state.sessions.find((session) => session.session_id === savedSessionId);
  if (savedSession) {
    await activateSession(savedSession.session_id);
    return;
  }
  if (state.sessions.length > 0) {
    await activateSession(state.sessions[0].session_id);
    return;
  }
  const session = await createSession();
  await activateSession(session.session_id);
}

async function createSession() {
  const response = await fetch("/api/sessions", { method: "POST" });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  const result = await response.json();
  if (!result.ok) {
    throw new Error(result.message || "创建会话失败");
  }
  await loadSessions();
  return result.session;
}

async function loadSessions() {
  const result = await getJson("/api/sessions");
  if (!result.ok) {
    elements.sessionStatus.textContent = result.message || "读取失败";
    renderSessions([]);
    return;
  }
  state.sessions = result.sessions || [];
  renderSessions(state.sessions);
}

async function activateSession(sessionId) {
  state.activeSessionId = sessionId;
  window.localStorage.setItem("active_session_id", sessionId);
  renderSessions(state.sessions);
  renderActiveSessionTitle();
  await loadSessionMessages(sessionId);
}

async function loadSessionMessages(sessionId) {
  const result = await getJson(`/api/sessions/${encodeURIComponent(sessionId)}/messages`);
  if (!result.ok) {
    resetMessages(result.message || "读取会话历史失败。");
    return;
  }
  renderHistoryMessages(result.messages || []);
}

function renderSessions(sessions) {
  elements.sessionStatus.textContent = sessions.length ? `${sessions.length} 个会话` : "暂无会话";
  elements.sessionsList.replaceChildren();
  if (!sessions.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state session-empty";
    empty.textContent = "还没有会话。";
    elements.sessionsList.append(empty);
    return;
  }
  for (const session of sessions) {
    const button = document.createElement("button");
    button.className = "session-row";
    button.type = "button";
    button.dataset.sessionId = session.session_id;
    button.classList.toggle("is-active", session.session_id === state.activeSessionId);
    button.addEventListener("click", () => {
      if (!state.busy) {
        activateSession(session.session_id).catch((error) => setBusy(false, String(error)));
      }
    });

    const title = document.createElement("strong");
    title.textContent = session.title || "新会话";

    const meta = document.createElement("span");
    meta.textContent = formatSessionMeta(session);

    button.append(title, meta);
    elements.sessionsList.append(button);
  }
}

function renderActiveSessionTitle() {
  const activeSession = state.sessions.find((session) => session.session_id === state.activeSessionId);
  elements.activeSessionTitle.textContent = activeSession?.title || "Personal Knowledge Agent";
}

function resetMessages(message) {
  elements.messages.replaceChildren();
  const greeting = appendMessage("agent", "Agent", message);
  greeting.classList.add("intro-message");
}

function renderHistoryMessages(messages) {
  elements.messages.replaceChildren();
  if (!messages.length) {
    resetMessages("你好。你可以录入一条 Q&A，也可以提问，我会基于本地知识库回答。");
    return;
  }
  for (const message of messages) {
    if (message.role === "user") {
      appendMessage("user", "你", message.content || "");
      continue;
    }
    const node = appendMessage("agent", "Agent", "");
    renderMarkdown(node.querySelector(".message-body"), message.content || "");
  }
}

function appendMessage(kind, role, body) {
  const message = document.createElement("article");
  message.className = `message ${kind}-message`;

  const roleNode = document.createElement("div");
  roleNode.className = "message-role";
  roleNode.textContent = role;

  const bodyNode = document.createElement("div");
  bodyNode.className = "message-body";
  bodyNode.textContent = body;

  message.append(roleNode, bodyNode);
  elements.messages.append(message);
  elements.messages.scrollTop = elements.messages.scrollHeight;
  return message;
}

function appendAgentRunMessage() {
  const message = document.createElement("article");
  message.className = "message agent-message run-message";

  const roleNode = document.createElement("div");
  roleNode.className = "message-role";
  roleNode.textContent = "Agent";

  const steps = document.createElement("div");
  steps.className = "run-steps";

  const approvals = document.createElement("div");
  approvals.className = "approval-list";

  const drafts = document.createElement("div");
  drafts.className = "drafts";

  const answer = document.createElement("div");
  answer.className = "message-body answer-body";

  message.append(roleNode, steps, approvals, drafts, answer);
  message._steps = steps;
  message._approvals = approvals;
  message._approvalCards = new Map();
  message._drafts = drafts;
  message._answer = answer;
  message._answerText = "";
  message._turnDrafts = new Map();
  message._activeAnswerTurn = null;
  elements.messages.append(message);
  elements.messages.scrollTop = elements.messages.scrollHeight;
  return message;
}

async function streamChat(message, agentMessage) {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: state.activeSessionId, message }),
  });
  if (!response.ok || !response.body) {
    throw new Error(`HTTP ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";
    for (const rawEvent of events) {
      const dataLine = rawEvent
        .split("\n")
        .find((line) => line.startsWith("data:"));
      if (!dataLine) continue;
      renderAgentEvent(agentMessage, JSON.parse(dataLine.slice(5).trim()));
    }
  }
  if (buffer.trim()) {
    const dataLine = buffer
      .split("\n")
      .find((line) => line.startsWith("data:"));
    if (dataLine) {
      renderAgentEvent(agentMessage, JSON.parse(dataLine.slice(5).trim()));
    }
  }
}

function renderAgentEvent(message, event) {
  switch (event.event_type) {
    case "user_input_received":
      addStep(message, "收到输入");
      break;
    case "llm_call_started":
      addStep(message, "调用模型");
      break;
    case "llm_call_finished":
      finishLlmTurn(message, event);
      break;
    case "tool_call_started":
      addToolStep(message, event);
      break;
    case "tool_call_finished":
      addStep(message, summarizeToolResult(event));
      break;
    case "permission_requested":
      addApprovalCard(message, event);
      break;
    case "permission_resolved":
      updateApprovalCard(message, event);
      break;
    case "evidence_checked":
      addStep(message, event.source_count ? `已核对 ${event.source_count} 条来源` : "未使用本地来源");
      break;
    case "answer_delta":
      appendAnswerDelta(message, event.turn ?? 0, event.text || "");
      break;
    case "final_answer_generated":
      finishAnswer(message, event.answer || "");
      break;
    case "error":
      renderRunError(message, event.message || "本轮没有完成。");
      break;
    default:
      break;
  }
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function addStep(message, text) {
  const step = document.createElement("div");
  step.className = "run-step";
  step.textContent = text;
  message._steps.append(step);
  return step;
}

function appendAnswerDelta(message, turn, text) {
  if (!text) return;
  const draft = getTurnDraft(message, turn);
  draft.text += text;
  if (message._activeAnswerTurn === turn) {
    message._answerText = draft.text;
    message._answer.textContent = draft.text;
    return;
  }
  draft.node.textContent = draft.text;
}

function finishAnswer(message, answer) {
  if (!message._answerText || message._answerText !== answer) {
    message._answerText = answer;
  }
  renderMarkdown(message._answer, message._answerText);
  message.classList.add("run-complete");
}

function renderRunError(message, body) {
  message.classList.add("error-message");
  addStep(message, "运行失败");
  if (!message._answerText) {
    message._answer.textContent = body;
  }
}

function getTurnDraft(message, turn) {
  if (message._turnDrafts.has(turn)) {
    return message._turnDrafts.get(turn);
  }
  const node = document.createElement("div");
  node.className = "draft-note";
  message._drafts.append(node);
  const draft = { text: "", node };
  message._turnDrafts.set(turn, draft);
  return draft;
}

function finishLlmTurn(message, event) {
  const turn = event.turn ?? 0;
  const toolCallsCount = Number(event.tool_calls_count || 0);
  const draft = message._turnDrafts.get(turn);
  if (toolCallsCount > 0) {
    addStep(message, `准备调用 ${toolCallsCount} 个工具`);
    if (draft && draft.text.trim()) {
      draft.node.classList.add("draft-muted");
    }
    return;
  }
  if (draft) {
    message._activeAnswerTurn = turn;
    message._answerText = draft.text;
    message._answer.textContent = draft.text;
    draft.node.remove();
  }
  addStep(message, "模型响应完成");
}

function addToolStep(message, event) {
  const details = document.createElement("details");
  details.className = "tool-step";

  const summary = document.createElement("summary");
  const label = document.createElement("span");
  label.textContent = toolDisplayName(event.tool_name);

  const hint = document.createElement("span");
  hint.className = "tool-hint";
  hint.textContent = "点击查看参数";

  summary.append(label, hint);

  const body = document.createElement("div");
  body.className = "tool-detail";

  const name = document.createElement("div");
  name.textContent = `工具：${event.tool_name || "unknown"}`;

  const params = document.createElement("pre");
  params.textContent = JSON.stringify(event.input || {}, null, 2);

  body.append(name, params);
  details.append(summary, body);
  message._steps.append(details);
}

function addApprovalCard(message, event) {
  const summary = event.summary || {};
  const card = document.createElement("section");
  card.className = "approval-card is-pending";
  card.dataset.approvalId = event.approval_id || "";

  const heading = document.createElement("div");
  heading.className = "approval-heading";

  const titleWrap = document.createElement("div");
  titleWrap.className = "approval-title-wrap";

  const eyebrow = document.createElement("span");
  eyebrow.className = "approval-eyebrow";
  eyebrow.textContent = "请求权限";

  const title = document.createElement("strong");
  title.className = "approval-title";
  title.textContent = summary.title || "确认高风险工具";

  titleWrap.append(eyebrow, title);

  const status = document.createElement("span");
  status.className = "approval-status";
  status.textContent = `${Math.round(Number(event.timeout_seconds || 0) / 60) || 5} 分钟内确认`;

  heading.append(titleWrap, status);

  const body = document.createElement("div");
  body.className = "approval-body";
  appendApprovalRow(body, "工具", summary.tool_label || summary.tool_name || "高风险工具");
  appendApprovalRow(body, summary.target_label || "目标", summary.target || "未提供");
  if (Array.isArray(summary.changes) && summary.changes.length) {
    appendApprovalRow(body, "变更", summary.changes.join("、"));
  }
  if (summary.preview) {
    appendApprovalRow(body, "摘要", summary.preview, "approval-preview");
  }

  const risk = document.createElement("div");
  risk.className = "approval-risk";
  risk.textContent = summary.risk || "该操作会修改本地数据。";

  const actions = document.createElement("div");
  actions.className = "approval-actions";

  const approveButton = document.createElement("button");
  approveButton.type = "button";
  approveButton.className = "approval-button approval-approve";
  approveButton.textContent = "允许执行";
  approveButton.addEventListener("click", () => submitApproval(card, "approve"));

  const denyButton = document.createElement("button");
  denyButton.type = "button";
  denyButton.className = "approval-button approval-deny";
  denyButton.textContent = "拒绝";
  denyButton.addEventListener("click", () => submitApproval(card, "deny"));

  actions.append(approveButton, denyButton);
  card.append(heading, body, risk, actions);
  message._approvalCards.set(event.approval_id, card);
  message._approvals.append(card);
}

function appendApprovalRow(container, label, value, extraClass = "") {
  const row = document.createElement("div");
  row.className = `approval-row ${extraClass}`.trim();

  const labelNode = document.createElement("span");
  labelNode.className = "approval-row-label";
  labelNode.textContent = label;

  const valueNode = document.createElement("span");
  valueNode.className = "approval-row-value";
  valueNode.textContent = value;
  valueNode.title = value;

  row.append(labelNode, valueNode);
  container.append(row);
}

async function submitApproval(card, decision) {
  const approvalId = card.dataset.approvalId;
  if (!approvalId) return;
  setApprovalCardState(card, decision === "approve" ? "submitting-approve" : "submitting-deny");
  try {
    const response = await fetch(`/api/approvals/${encodeURIComponent(approvalId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) {
      setApprovalCardState(card, "submit-error", result.message || "确认提交失败");
    }
  } catch (error) {
    setApprovalCardState(card, "submit-error", String(error));
  }
}

function updateApprovalCard(message, event) {
  const card = message._approvalCards.get(event.approval_id);
  if (!card) return;
  setApprovalCardState(card, event.status || "denied");
}

function setApprovalCardState(card, status, message = "") {
  const statusNode = card.querySelector(".approval-status");
  const buttons = card.querySelectorAll(".approval-button");
  const disableButtons = !["pending", "submit-error"].includes(status);
  for (const button of buttons) {
    button.disabled = disableButtons;
  }
  card.classList.remove("is-pending", "is-approved", "is-denied", "is-expired", "is-cancelled", "is-error");
  if (status === "approved" || status === "submitting-approve") {
    card.classList.add("is-approved");
    statusNode.textContent = status === "approved" ? "已允许，继续执行" : "正在提交允许";
  } else if (status === "denied" || status === "submitting-deny") {
    card.classList.add("is-denied");
    statusNode.textContent = status === "denied" ? "已拒绝，操作未执行" : "正在提交拒绝";
  } else if (status === "expired") {
    card.classList.add("is-expired");
    statusNode.textContent = "已超时，操作未执行";
  } else if (status === "cancelled") {
    card.classList.add("is-cancelled");
    statusNode.textContent = "连接已断开，操作未执行";
  } else if (status === "submit-error") {
    card.classList.add("is-error");
    statusNode.textContent = message || "确认提交失败";
    for (const button of buttons) {
      button.disabled = false;
    }
  } else {
    card.classList.add("is-pending");
    statusNode.textContent = "等待确认";
  }
}

function toolDisplayName(toolName) {
  const labels = {
    hybrid_search_qa_cards: "搜索本地知识库",
    search_qa_cards: "搜索本地知识库",
    save_qa_card: "保存知识卡片",
    read_qa_card: "读取知识卡片",
    list_recent_cards: "读取最近卡片",
    update_qa_card: "更新知识卡片",
    delete_qa_card: "删除知识卡片",
  };
  return labels[toolName] || "调用工具";
}

function summarizeToolResult(event) {
  const output = event.output || {};
  if (output.error_code === "permission_denied") {
    return "操作未执行";
  }
  if (output.ok === false) {
    return `${toolDisplayName(event.tool_name)}失败`;
  }
  if (Array.isArray(output.cards)) {
    return output.cards.length ? `找到 ${output.cards.length} 条记录` : "未找到相关记录";
  }
  if (output.card_id) {
    return "知识卡片已保存";
  }
  return `${toolDisplayName(event.tool_name)}完成`;
}

function renderMarkdown(container, markdown) {
  container.classList.add("markdown-body");
  container.replaceChildren();
  const lines = markdown.split(/\r?\n/);
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }
    if (/^---+$/.test(line.trim())) {
      container.append(document.createElement("hr"));
      index += 1;
      continue;
    }
    if (/^\|.+\|$/.test(line.trim()) && index + 1 < lines.length && /^\|[\s:-]+\|/.test(lines[index + 1].trim())) {
      const tableLines = [line, lines[index + 1]];
      index += 2;
      while (index < lines.length && /^\|.+\|$/.test(lines[index].trim())) {
        tableLines.push(lines[index]);
        index += 1;
      }
      container.append(renderMarkdownTable(tableLines));
      continue;
    }
    const headingMatch = line.match(/^(#{1,4})\s+(.+)$/);
    if (headingMatch) {
      const level = Math.min(headingMatch[1].length + 2, 6);
      const heading = document.createElement(`h${level}`);
      appendInlineMarkdown(heading, headingMatch[2]);
      container.append(heading);
      index += 1;
      continue;
    }
    const listMatch = line.match(/^(\d+\.\s+|[-*]\s+)(.+)$/);
    if (listMatch) {
      const ordered = /^\d+\./.test(listMatch[1]);
      const list = document.createElement(ordered ? "ol" : "ul");
      while (index < lines.length) {
        const itemMatch = lines[index].match(/^(\d+\.\s+|[-*]\s+)(.+)$/);
        if (!itemMatch || (/^\d+\./.test(itemMatch[1]) !== ordered)) break;
        const item = document.createElement("li");
        appendInlineMarkdown(item, itemMatch[2]);
        list.append(item);
        index += 1;
      }
      container.append(list);
      continue;
    }
    const paragraphLines = [line];
    index += 1;
    while (index < lines.length && lines[index].trim() && !/^(#{1,4})\s+/.test(lines[index]) && !/^(\d+\.\s+|[-*]\s+)/.test(lines[index]) && !/^---+$/.test(lines[index].trim()) && !/^\|.+\|$/.test(lines[index].trim())) {
      paragraphLines.push(lines[index]);
      index += 1;
    }
    const paragraph = document.createElement("p");
    appendInlineMarkdown(paragraph, paragraphLines.join("\n"), { preserveBreaks: true });
    container.append(paragraph);
  }
}

function renderMarkdownTable(lines) {
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const tbody = document.createElement("tbody");
  const rows = lines.filter((_, index) => index !== 1).map(parseTableRow);
  for (const [rowIndex, cells] of rows.entries()) {
    const row = document.createElement("tr");
    for (const cell of cells) {
      const node = document.createElement(rowIndex === 0 ? "th" : "td");
      appendInlineMarkdown(node, cell);
      row.append(node);
    }
    (rowIndex === 0 ? thead : tbody).append(row);
  }
  table.append(thead, tbody);
  return table;
}

function parseTableRow(line) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

function appendInlineMarkdown(parent, text, options = {}) {
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let lastIndex = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > lastIndex) {
      appendText(parent, text.slice(lastIndex, match.index), options);
    }
    const token = match[0];
    if (token.startsWith("**")) {
      const strong = document.createElement("strong");
      strong.textContent = token.slice(2, -2);
      parent.append(strong);
    } else {
      const code = document.createElement("code");
      code.textContent = token.slice(1, -1);
      parent.append(code);
    }
    lastIndex = match.index + token.length;
  }
  if (lastIndex < text.length) {
    appendText(parent, text.slice(lastIndex), options);
  }
}

function appendText(parent, text, options) {
  if (!options.preserveBreaks || !text.includes("\n")) {
    parent.append(document.createTextNode(text));
    return;
  }
  const parts = text.split("\n");
  for (const [index, part] of parts.entries()) {
    if (index > 0) parent.append(document.createElement("br"));
    if (part) parent.append(document.createTextNode(part));
  }
}

function setBusy(busy, text) {
  state.busy = busy;
  elements.sendButton.disabled = busy;
  elements.statusText.textContent = text;
}

async function loadRecentCards() {
  elements.cardsTitle.textContent = "最近卡片";
  setCardsLoading(true);
  const result = await getJson("/api/cards/recent?limit=10").finally(() => setCardsLoading(false));
  if (!result.ok) {
    renderCards([], result.message || "读取最近卡片失败。");
    return;
  }
  renderCards(result.cards || []);
}

async function searchCards(query) {
  elements.cardsTitle.textContent = "搜索结果";
  setCardsLoading(true);
  const result = await getJson(`/api/cards/search?q=${encodeURIComponent(query)}&limit=10`).finally(() =>
    setCardsLoading(false),
  );
  if (!result.ok) {
    renderCards([], result.message || "搜索失败。");
    return;
  }
  renderCards(result.cards || []);
}

function renderCards(cards, emptyText = "暂无卡片。") {
  state.cards = cards;
  if (!cards.some((card) => card.card_id === state.selectedCardId)) {
    closeCardDetail();
  }
  elements.cardsCount.textContent = String(cards.length);
  elements.cardsList.replaceChildren();
  elements.cardsList.setAttribute("aria-busy", "false");

  if (!cards.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = emptyText;
    elements.cardsList.append(empty);
    return;
  }

  for (const card of cards) {
    const button = document.createElement("button");
    button.className = "card-row";
    button.type = "button";
    button.dataset.cardId = card.card_id || "";
    button.setAttribute("aria-pressed", String(card.card_id === state.selectedCardId));
    if (card.card_id === state.selectedCardId) {
      button.classList.add("is-selected");
    }
    button.addEventListener("click", () => loadCardDetail(card.card_id));

    const question = document.createElement("strong");
    question.textContent = card.question || card.card_id;

    const summary = document.createElement("p");
    summary.textContent = card.summary || card.answer_snippet || "";

    const meta = document.createElement("div");
    meta.className = "card-meta";
    meta.textContent = [card.source_type || "unknown", formatTimestamp(card.created_at)].filter(Boolean).join(" · ");

    button.append(question, summary, meta);
    elements.cardsList.append(button);
  }
}

async function loadCardDetail(cardId) {
  if (!cardId) return;
  state.selectedCardId = cardId;
  openCardDetail();
  markSelectedCard(cardId);
  const result = await getJson(`/api/cards/${encodeURIComponent(cardId)}`);
  if (!result.ok) {
    elements.cardDetail.className = "card-detail empty-state";
    elements.cardDetail.textContent = result.message || "读取卡片详情失败。";
    return;
  }
  renderCardDetail(result.card);
}

function openCardDetail() {
  elements.cardsPane.classList.add("has-card-detail");
}

function closeCardDetail() {
  state.selectedCardId = null;
  elements.cardsPane.classList.remove("has-card-detail");
  markSelectedCard(null);
  elements.cardDetail.className = "card-detail empty-state";
  elements.cardDetail.textContent = "选择一张卡片查看详情。";
}

function renderCardDetail(card) {
  elements.cardDetail.className = "card-detail";
  const keywords = Array.isArray(card.keywords) ? card.keywords.join(", ") : "";
  elements.cardDetail.innerHTML = "";

  const list = document.createElement("dl");
  addDetail(list, "card_id", card.card_id);
  addDetail(list, "原始问题", card.question);
  addDetail(list, "原始答案", card.answer);
  addDetail(list, "summary", card.summary);
  addDetail(list, "keywords", keywords);
  addDetail(list, "source_type", card.source_type);
  addDetail(list, "创建时间", formatTimestamp(card.created_at, { detail: true }));
  addDetail(list, "更新时间", formatTimestamp(card.updated_at, { detail: true }));
  elements.cardDetail.append(list);
}

function formatTimestamp(value, options = {}) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const formatter = options.detail ? detailTimeFormatter : cardTimeFormatter;
  const suffix = options.detail ? " (UTC+8)" : "";
  return `${formatter.format(date)}${suffix}`;
}

function formatSessionMeta(session) {
  if (session.last_user_message) {
    return session.last_user_message;
  }
  return formatTimestamp(session.updated_at || session.created_at) || session.session_id;
}

function getStoredBoolean(key, fallback) {
  const value = window.localStorage.getItem(key);
  if (value === "true") return true;
  if (value === "false") return false;
  return fallback;
}

function setPaneCollapsed(side, collapsed) {
  if (side === "left") {
    state.leftCollapsed = collapsed;
    window.localStorage.setItem("left_pane_collapsed", String(collapsed));
  } else {
    state.rightCollapsed = collapsed;
    window.localStorage.setItem("right_pane_collapsed", String(collapsed));
  }
  applyPaneState();
}

function applyPaneState() {
  elements.appShell.classList.toggle("is-left-collapsed", state.leftCollapsed);
  elements.appShell.classList.toggle("is-right-collapsed", state.rightCollapsed);

  const sessionsVisible = !state.leftCollapsed;
  elements.toggleSessionsButton.setAttribute("aria-expanded", String(sessionsVisible));
  elements.toggleSessionsButton.setAttribute("aria-label", sessionsVisible ? "隐藏会话" : "显示会话");
  elements.toggleSessionsButton.title = sessionsVisible ? "隐藏会话" : "显示会话";

  const cardsVisible = !state.rightCollapsed;
  elements.toggleCardsButton.setAttribute("aria-expanded", String(cardsVisible));
  elements.toggleCardsButton.setAttribute("aria-label", cardsVisible ? "隐藏知识卡片" : "显示知识卡片");
  elements.toggleCardsButton.title = cardsVisible ? "隐藏知识卡片" : "显示知识卡片";
}

function setCardsLoading(loading) {
  elements.cardsList.setAttribute("aria-busy", String(loading));
  if (!loading) return;
  elements.cardsList.replaceChildren();
  const loadingNode = document.createElement("div");
  loadingNode.className = "empty-state";
  loadingNode.textContent = "正在读取卡片...";
  elements.cardsList.append(loadingNode);
}

function markSelectedCard(cardId) {
  for (const button of elements.cardsList.querySelectorAll(".card-row")) {
    const selected = Boolean(cardId) && button.dataset.cardId === cardId;
    button.classList.toggle("is-selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  }
}

function addDetail(list, label, value) {
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = value || "";
  list.append(term, description);
}

initializeApp().catch((error) => {
  resetMessages(String(error));
});

loadRecentCards().catch((error) => {
  renderCards([], String(error));
});
