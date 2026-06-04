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
  elements.messageInput.value = "";
  setBusy(true, "Agent 正在处理");

  try {
    const result = await postJson("/api/chat", { message });
    if (!result.ok) {
      appendMessage("error", "错误", result.message || "本轮没有完成。");
      return;
    }
    appendMessage("agent", "Agent", result.answer || "");
    await loadRecentCards();
  } catch (error) {
    appendMessage("error", "错误", String(error));
  } finally {
    setBusy(false, "本地 Web UI 已就绪");
  }
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

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

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
