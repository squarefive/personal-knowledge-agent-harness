const state = {
  cards: [],
  busy: false,
};

const elements = {
  chatForm: document.querySelector("#chatForm"),
  messageInput: document.querySelector("#messageInput"),
  sendButton: document.querySelector("#sendButton"),
  messages: document.querySelector("#messages"),
  statusText: document.querySelector("#statusText"),
  refreshCardsButton: document.querySelector("#refreshCardsButton"),
  searchForm: document.querySelector("#searchForm"),
  searchInput: document.querySelector("#searchInput"),
  cardsTitle: document.querySelector("#cardsTitle"),
  cardsCount: document.querySelector("#cardsCount"),
  cardsList: document.querySelector("#cardsList"),
  cardDetail: document.querySelector("#cardDetail"),
};

elements.chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = elements.messageInput.value.trim();
  if (!message || state.busy) return;

  appendMessage("user", "你", message);
  const agentMessage = appendAgentRunMessage();
  elements.messageInput.value = "";
  setBusy(true, "Agent 正在处理");

  try {
    await streamChat(message, agentMessage);
    await loadRecentCards();
  } catch (error) {
    renderRunError(agentMessage, String(error));
  } finally {
    setBusy(false, "本地 Web UI 已就绪");
  }
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

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
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

  const answer = document.createElement("div");
  answer.className = "message-body answer-body";

  message.append(roleNode, steps, answer);
  message._steps = steps;
  message._answer = answer;
  message._answerText = "";
  elements.messages.append(message);
  elements.messages.scrollTop = elements.messages.scrollHeight;
  return message;
}

async function streamChat(message, agentMessage) {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
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
      addStep(message, event.tool_calls_count ? `模型返回 ${event.tool_calls_count} 个工具调用` : "模型响应完成");
      break;
    case "tool_call_started":
      addStep(message, `调用工具 ${event.tool_name || "unknown"}`);
      break;
    case "tool_call_finished":
      addStep(message, `工具完成 ${event.tool_name || "unknown"}`);
      break;
    case "evidence_checked":
      addStep(message, "证据检查完成");
      break;
    case "answer_delta":
      appendAnswerDelta(message, event.text || "");
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
}

function appendAnswerDelta(message, text) {
  if (!text) return;
  message._answerText += text;
  message._answer.textContent = message._answerText;
}

function finishAnswer(message, answer) {
  if (!message._answerText || message._answerText !== answer) {
    message._answerText = answer;
    message._answer.textContent = answer;
  }
  message.classList.add("run-complete");
}

function renderRunError(message, body) {
  message.classList.add("error-message");
  addStep(message, "运行失败");
  if (!message._answerText) {
    message._answer.textContent = body;
  }
}

function setBusy(busy, text) {
  state.busy = busy;
  elements.sendButton.disabled = busy;
  elements.statusText.textContent = text;
}

async function loadRecentCards() {
  elements.cardsTitle.textContent = "最近卡片";
  const result = await getJson("/api/cards/recent?limit=10");
  if (!result.ok) {
    renderCards([], result.message || "读取最近卡片失败。");
    return;
  }
  renderCards(result.cards || []);
}

async function searchCards(query) {
  elements.cardsTitle.textContent = "搜索结果";
  const result = await getJson(`/api/cards/search?q=${encodeURIComponent(query)}&limit=10`);
  if (!result.ok) {
    renderCards([], result.message || "搜索失败。");
    return;
  }
  renderCards(result.cards || []);
}

function renderCards(cards, emptyText = "暂无卡片。") {
  state.cards = cards;
  elements.cardsCount.textContent = String(cards.length);
  elements.cardsList.replaceChildren();

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
    button.addEventListener("click", () => loadCardDetail(card.card_id));

    const question = document.createElement("strong");
    question.textContent = card.question || card.card_id;

    const summary = document.createElement("p");
    summary.textContent = card.summary || card.answer_snippet || "";

    const meta = document.createElement("div");
    meta.className = "card-meta";
    meta.textContent = `${card.source_type || "unknown"} · ${card.created_at || ""}`;

    button.append(question, summary, meta);
    elements.cardsList.append(button);
  }
}

async function loadCardDetail(cardId) {
  if (!cardId) return;
  const result = await getJson(`/api/cards/${encodeURIComponent(cardId)}`);
  if (!result.ok) {
    elements.cardDetail.className = "card-detail empty-state";
    elements.cardDetail.textContent = result.message || "读取卡片详情失败。";
    return;
  }
  renderCardDetail(result.card);
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
  addDetail(list, "created_at", card.created_at);
  addDetail(list, "updated_at", card.updated_at);
  elements.cardDetail.append(list);
}

function addDetail(list, label, value) {
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = value || "";
  list.append(term, description);
}

loadRecentCards().catch((error) => {
  renderCards([], String(error));
});
