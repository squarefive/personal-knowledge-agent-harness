const appConstants = window.PKA_CONSTANTS;

const state = {
  authUser: null,
  loginCodeSent: false,
  resendTimerId: null,
  cards: [],
  busy: false,
  sessions: [],
  activeSessionId: null,
  selectedCardId: null,
  approvalDialogs: new Map(),
  activeTypingController: null,
  leftCollapsed: getStoredBoolean(
    appConstants.LEFT_PANE_COLLAPSED_KEY,
    window.matchMedia(appConstants.DESKTOP_COLLAPSE_MEDIA_QUERY).matches,
  ),
  rightCollapsed: getStoredBoolean(
    appConstants.RIGHT_PANE_COLLAPSED_KEY,
    window.matchMedia(appConstants.MOBILE_MEDIA_QUERY).matches,
  ),
};

const FRONTEND_TRACE_ID = `page_${Date.now().toString(36)}_${Math.random().toString(16).slice(2, 8)}`;
const FRONTEND_START_MS = performance.now();

frontendLog("app.loaded", {
  ready_state: document.readyState,
  visibility: document.visibilityState,
});

document.addEventListener("readystatechange", () => {
  frontendLog("document.ready_state", { ready_state: document.readyState });
});

window.addEventListener("load", () => {
  frontendLog("window.load", { duration_ms: elapsedSince(FRONTEND_START_MS) });
  logResourceTiming("styles.css");
  logResourceTiming("app.js");
});

window.addEventListener("visibilitychange", () => {
  frontendLog("page.visibility", { visibility: document.visibilityState });
});

window.addEventListener("error", (event) => {
  frontendError("window.error", {
    message: event.message,
    filename: event.filename,
    lineno: event.lineno,
    colno: event.colno,
  });
});

window.addEventListener("unhandledrejection", (event) => {
  frontendError("promise.unhandled_rejection", { message: errorMessage(event.reason) });
});

const elements = {
  authGate: document.querySelector("#authGate"),
  authForm: document.querySelector("#authForm"),
  authEmailInput: document.querySelector("#authEmailInput"),
  authCodeGroup: document.querySelector("#authCodeGroup"),
  authCodeInput: document.querySelector("#authCodeInput"),
  authStatus: document.querySelector("#authStatus"),
  requestCodeButton: document.querySelector("#requestCodeButton"),
  authSubmitButton: document.querySelector("#authSubmitButton"),
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
  contextStatus: document.querySelector("#contextStatus"),
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
  currentUserEmail: document.querySelector("#currentUserEmail"),
  logoutButton: document.querySelector("#logoutButton"),
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
setLoginCodeSent(false);

elements.requestCodeButton.addEventListener("click", () => {
  requestLoginCode().catch((error) => setAuthStatus(String(error), "error"));
});

elements.authForm.addEventListener("submit", (event) => {
  event.preventDefault();
  verifyLoginCode().catch((error) => setAuthStatus(String(error), "error"));
});

elements.logoutButton.addEventListener("click", () => {
  logout().catch((error) => setAuthStatus(String(error), "error"));
});

elements.toggleSessionsButton.addEventListener("click", () => {
  setPaneCollapsed("left", !state.leftCollapsed);
});

elements.toggleCardsButton.addEventListener("click", () => {
  setPaneCollapsed("right", !state.rightCollapsed);
});

elements.chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = elements.messageInput.value.trim();
  if (!message || state.busy || !state.activeSessionId) {
    frontendLog("chat.submit.skipped", {
      reason: !message ? "empty_message" : state.busy ? "busy" : "missing_session",
      busy: state.busy,
      session_id: state.activeSessionId || "",
    });
    return;
  }
  const startedAt = performance.now();
  frontendLog("chat.submit.start", { session_id: state.activeSessionId });

  appendMessage("user", "你", message);
  const agentMessage = appendAgentRunMessage();
  elements.messageInput.value = "";
  setBusy(true, "Agent 正在处理");

  try {
    await streamChat(message, agentMessage);
    await loadSessions();
    renderActiveSessionTitle();
    await loadRecentCards();
    frontendLog("chat.submit.done", {
      session_id: state.activeSessionId || "",
      duration_ms: elapsedSince(startedAt),
    });
  } catch (error) {
    clearOpenApprovalDialogs(appConstants.APPROVAL_STATUS_CANCELLED);
    renderRunError(agentMessage, String(error));
    frontendError("chat.submit.error", {
      session_id: state.activeSessionId || "",
      duration_ms: elapsedSince(startedAt),
      message: errorMessage(error),
    });
  } finally {
    setBusy(false, "个人知识库已就绪");
  }
});

elements.newSessionButton.addEventListener("click", async () => {
  if (state.busy) {
    frontendLog("session.create.skipped", { reason: "busy" });
    return;
  }
  const session = await createSession();
  await activateSession(session.session_id);
});

elements.renameSessionButton.addEventListener("click", async () => {
  if (!state.activeSessionId) return;
  const activeSession = state.sessions.find((session) => session.session_id === state.activeSessionId);
  const nextTitle = window.prompt("重命名会话", activeSession?.title || "");
  if (nextTitle === null) return;
  const result = await getJson(`${appConstants.API_SESSIONS_BASE_PATH}/${encodeURIComponent(state.activeSessionId)}`, {
    method: appConstants.HTTP_METHOD_PATCH,
    headers: { [appConstants.HEADER_CONTENT_TYPE]: appConstants.CONTENT_TYPE_JSON },
    body: JSON.stringify({ title: nextTitle }),
  });
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

elements.closeCardDetailButton.addEventListener("click", () => {
  closeCardDetail();
  if (isMobileViewport()) {
    setPaneCollapsed("right", true);
  }
});

async function bootApp() {
  const startedAt = performance.now();
  frontendLog("boot.start");
  setAuthStatus("正在检查登录状态。", "muted");
  const result = await getJson(appConstants.API_AUTH_ME_PATH, {}, { allowAuthError: true });
  if (result.ok) {
    await enterAuthenticatedApp(result.user);
    frontendLog("boot.done", { authenticated: true, duration_ms: elapsedSince(startedAt) });
    return;
  }
  const message =
    result.error_code === appConstants.ERROR_CODE_NOT_AUTHENTICATED
      ? ""
      : resultMessage(result, "认证服务暂时不可用。");
  showLogin(message, message ? "error" : "muted");
  frontendLog("boot.done", {
    authenticated: false,
    error_code: result.error_code || "",
    duration_ms: elapsedSince(startedAt),
  });
}

async function enterAuthenticatedApp(user) {
  const startedAt = performance.now();
  frontendLog("app.enter_authenticated.start");
  state.authUser = user || null;
  elements.currentUserEmail.textContent = state.authUser?.email || "已登录";
  stopResendTimer();
  setLoginCodeSent(false);
  elements.authGate.hidden = true;
  elements.appShell.hidden = false;
  await initializeApp();
  await loadRecentCards();
  setBusy(false, "个人知识库已就绪");
  frontendLog("app.enter_authenticated.done", {
    sessions_count: state.sessions.length,
    cards_count: state.cards.length,
    duration_ms: elapsedSince(startedAt),
  });
}

async function requestLoginCode() {
  const startedAt = performance.now();
  frontendLog("auth.request_code.start");
  const email = elements.authEmailInput.value.trim();
  if (!email) {
    setAuthStatus("请输入邮箱。", "error");
    frontendLog("auth.request_code.invalid", { reason: "missing_email" });
    return;
  }
  elements.requestCodeButton.disabled = true;
  setAuthStatus("正在发送验证码。", "muted");
  const result = await postJson(appConstants.API_AUTH_REQUEST_CODE_PATH, { email }, { allowAuthError: true });
  if (!result.ok) {
    elements.requestCodeButton.disabled = false;
    setLoginCodeSent(false);
    setAuthStatus(resultMessage(result, "验证码发送失败。"), "error");
    frontendLog("auth.request_code.done", {
      ok: false,
      error_code: result.error_code || "",
      duration_ms: elapsedSince(startedAt),
    });
    return;
  }
  setLoginCodeSent(true);
  elements.authCodeInput.focus();
  startResendTimer();
  frontendLog("auth.request_code.done", { ok: true, duration_ms: elapsedSince(startedAt) });
}

async function verifyLoginCode() {
  const startedAt = performance.now();
  frontendLog("auth.verify_code.start");
  const email = elements.authEmailInput.value.trim();
  const code = elements.authCodeInput.value.trim();
  if (!email) {
    setAuthStatus("请输入邮箱。", "error");
    frontendLog("auth.verify_code.invalid", { reason: "missing_email" });
    return;
  }
  if (!/^\d{6}$/.test(code)) {
    setAuthStatus("请输入 6 位验证码。", "error");
    frontendLog("auth.verify_code.invalid", { reason: "invalid_code_format" });
    return;
  }
  elements.authSubmitButton.disabled = true;
  setAuthStatus("正在登录。", "muted");
  const result = await postJson(appConstants.API_AUTH_VERIFY_CODE_PATH, { email, code }, { allowAuthError: true });
  if (!result.ok) {
    elements.authSubmitButton.disabled = false;
    setAuthStatus(resultMessage(result, "验证码无效或已过期。"), "error");
    frontendLog("auth.verify_code.done", {
      ok: false,
      error_code: result.error_code || "",
      duration_ms: elapsedSince(startedAt),
    });
    return;
  }
  stopResendTimer();
  setAuthStatus("登录成功，正在载入知识库。", "success");
  await enterAuthenticatedApp(result.user);
  frontendLog("auth.verify_code.done", { ok: true, duration_ms: elapsedSince(startedAt) });
}

async function logout() {
  if (state.busy) {
    frontendLog("auth.logout.skipped", { reason: "busy" });
    return;
  }
  const startedAt = performance.now();
  frontendLog("auth.logout.start");
  elements.logoutButton.disabled = true;
  try {
    await postJson(appConstants.API_AUTH_LOGOUT_PATH, {}, { allowAuthError: true });
  } finally {
    elements.logoutButton.disabled = false;
    clearOpenApprovalDialogs(appConstants.APPROVAL_STATUS_CANCELLED);
    resetAuthenticatedState();
    showLogin("已退出登录。", "muted");
    frontendLog("auth.logout.done", { duration_ms: elapsedSince(startedAt) });
  }
}

async function postJson(url, body, options = {}) {
  return getJson(
    url,
    {
      method: appConstants.HTTP_METHOD_POST,
      headers: { [appConstants.HEADER_CONTENT_TYPE]: appConstants.CONTENT_TYPE_JSON },
      body: JSON.stringify(body || {}),
    },
    options,
  );
}

async function getJson(url, init = {}, options = {}) {
  const method = (init.method || appConstants.HTTP_METHOD_GET).toUpperCase();
  const startedAt = performance.now();
  frontendLog("api.start", { method, url });
  try {
    const response = await fetch(url, { credentials: appConstants.FETCH_CREDENTIALS_SAME_ORIGIN, ...init });
    frontendLog("api.response", {
      method,
      url,
      status: response.status,
      duration_ms: elapsedSince(startedAt),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const result = await response.json();
    frontendLog("api.done", {
      method,
      url,
      ok: result?.ok !== false,
      error_code: result?.error_code || "",
      duration_ms: elapsedSince(startedAt),
    });
    if (!options.allowAuthError && isNotAuthenticated(result)) {
      showLogin("登录状态已失效，请重新登录。", "error");
      throw new Error(appConstants.ERROR_CODE_NOT_AUTHENTICATED);
    }
    return result;
  } catch (error) {
    frontendError("api.error", {
      method,
      url,
      duration_ms: elapsedSince(startedAt),
      message: errorMessage(error),
    });
    throw error;
  }
}

function isNotAuthenticated(result) {
  return result && result.ok === false && result.error_code === appConstants.ERROR_CODE_NOT_AUTHENTICATED;
}

function resultMessage(result, fallback) {
  const messages = {
    [appConstants.ERROR_CODE_AUTH_NOT_CONFIGURED]: "认证服务暂时不可用。",
    [appConstants.ERROR_CODE_AUTH_REQUEST_ERROR]: "验证码发送失败，请稍后再试。",
    [appConstants.ERROR_CODE_AUTH_VERIFY_ERROR]: "登录验证失败，请稍后再试。",
    [appConstants.ERROR_CODE_EMAIL_NOT_ALLOWED]: "该邮箱不在允许登录范围内。",
    [appConstants.ERROR_CODE_INVALID_LOGIN_CODE]: "验证码无效。",
    [appConstants.ERROR_CODE_LOGIN_CODE_EXPIRED]: "验证码已过期，请重新发送。",
    [appConstants.ERROR_CODE_LOGIN_CODE_CONSUMED]: "验证码已使用，请重新发送。",
    [appConstants.ERROR_CODE_LOGIN_CODE_NOT_FOUND]: "请先发送验证码。",
    [appConstants.ERROR_CODE_TOO_MANY_ATTEMPTS]: "验证码尝试次数过多，请重新发送。",
    [appConstants.ERROR_CODE_USER_NOT_FOUND]: "没有找到该邮箱对应的账号。",
  };
  return messages[result?.error_code] || result?.message || fallback;
}

function showLogin(message = "", variant = "muted") {
  state.authUser = null;
  elements.appShell.hidden = true;
  elements.authGate.hidden = false;
  setBusy(false, "个人知识库问答助手");
  if (message) {
    setAuthStatus(message, variant);
  } else if (!state.loginCodeSent) {
    setAuthStatus("输入邮箱后获取验证码。", "muted");
  }
}

function resetAuthenticatedState() {
  stopActiveTyping();
  state.sessions = [];
  state.cards = [];
  state.activeSessionId = null;
  state.selectedCardId = null;
  window.localStorage.removeItem(appConstants.ACTIVE_SESSION_ID_KEY);
  renderSessions([]);
  renderCards([]);
  resetMessages("登录后开始提问或录入 Q&A。");
}

function setLoginCodeSent(sent) {
  state.loginCodeSent = sent;
  elements.authCodeGroup.hidden = !sent;
  elements.authSubmitButton.disabled = !sent;
  if (!sent) {
    elements.authCodeInput.value = "";
  }
}

function setAuthStatus(message, variant = "muted") {
  elements.authStatus.textContent = message;
  elements.authStatus.dataset.variant = variant;
}

function startResendTimer(seconds = appConstants.RESEND_TIMER_SECONDS) {
  stopResendTimer();
  let remaining = seconds;
  elements.requestCodeButton.disabled = true;
  const tick = () => {
    if (remaining <= 0) {
      stopResendTimer();
      elements.requestCodeButton.disabled = false;
      setAuthStatus("可以重新发送验证码。", "muted");
      return;
    }
    setAuthStatus(`验证码已发送，请查看 QQ 邮箱。${remaining} 秒后可重新发送。`, "success");
    remaining -= 1;
  };
  tick();
  state.resendTimerId = window.setInterval(tick, appConstants.TIMER_INTERVAL_MS);
}

function stopResendTimer() {
  if (state.resendTimerId) {
    window.clearInterval(state.resendTimerId);
    state.resendTimerId = null;
  }
}

async function initializeApp() {
  const startedAt = performance.now();
  frontendLog("app.initialize.start");
  await loadSessions();
  const savedSessionId = window.localStorage.getItem(appConstants.ACTIVE_SESSION_ID_KEY);
  const savedSession = state.sessions.find((session) => session.session_id === savedSessionId);
  if (savedSession) {
    await activateSession(savedSession.session_id);
    frontendLog("app.initialize.done", {
      source: "saved_session",
      session_id: savedSession.session_id,
      duration_ms: elapsedSince(startedAt),
    });
    return;
  }
  if (state.sessions.length > 0) {
    await activateSession(state.sessions[0].session_id);
    frontendLog("app.initialize.done", {
      source: "first_session",
      session_id: state.sessions[0].session_id,
      duration_ms: elapsedSince(startedAt),
    });
    return;
  }
  const session = await createSession();
  await activateSession(session.session_id);
  frontendLog("app.initialize.done", {
    source: "created_session",
    session_id: session.session_id,
    duration_ms: elapsedSince(startedAt),
  });
}

async function createSession() {
  const startedAt = performance.now();
  frontendLog("session.create.start");
  const result = await postJson(appConstants.API_SESSIONS_BASE_PATH);
  if (!result.ok) {
    throw new Error(result.message || "创建会话失败");
  }
  await loadSessions();
  frontendLog("session.create.done", {
    session_id: result.session?.session_id || "",
    duration_ms: elapsedSince(startedAt),
  });
  return result.session;
}

async function loadSessions() {
  const startedAt = performance.now();
  frontendLog("sessions.load.start");
  const result = await getJson(appConstants.API_SESSIONS_BASE_PATH);
  if (!result.ok) {
    elements.sessionStatus.textContent = result.message || "读取失败";
    renderSessions([]);
    frontendLog("sessions.load.done", {
      ok: false,
      error_code: result.error_code || "",
      duration_ms: elapsedSince(startedAt),
    });
    return;
  }
  state.sessions = result.sessions || [];
  renderSessions(state.sessions);
  frontendLog("sessions.load.done", {
    ok: true,
    count: state.sessions.length,
    duration_ms: elapsedSince(startedAt),
  });
}

async function activateSession(sessionId) {
  const startedAt = performance.now();
  const collapseMobilePane = isMobileViewport() && !state.leftCollapsed;
  frontendLog("session.activate.start", { session_id: sessionId });
  stopActiveTyping();
  state.activeSessionId = sessionId;
  window.localStorage.setItem(appConstants.ACTIVE_SESSION_ID_KEY, sessionId);
  renderSessions(state.sessions);
  renderActiveSessionTitle();
  renderContextForSession(sessionId);
  await loadSessionMessages(sessionId);
  if (collapseMobilePane) {
    setPaneCollapsed("left", true);
  }
  frontendLog("session.activate.done", {
    session_id: sessionId,
    mobile_left_collapsed: collapseMobilePane,
    duration_ms: elapsedSince(startedAt),
  });
}

async function loadSessionMessages(sessionId) {
  const startedAt = performance.now();
  frontendLog("session.messages.load.start", { session_id: sessionId });
  const result = await getJson(`${appConstants.API_SESSIONS_BASE_PATH}/${encodeURIComponent(sessionId)}/messages`);
  if (!result.ok) {
    resetMessages(result.message || "读取会话历史失败。");
    frontendLog("session.messages.load.done", {
      ok: false,
      session_id: sessionId,
      error_code: result.error_code || "",
      duration_ms: elapsedSince(startedAt),
    });
    return;
  }
  if (result.session) {
    mergeSession(result.session);
    renderContextForSession(sessionId);
  }
  renderHistoryMessages(result.messages || []);
  frontendLog("session.messages.load.done", {
    ok: true,
    session_id: sessionId,
    count: (result.messages || []).length,
    duration_ms: elapsedSince(startedAt),
  });
}

function renderSessions(sessions) {
  elements.sessionStatus.textContent = sessions.length ? `${sessions.length} 个会话` : "暂无会话";
  elements.sessionsList.replaceChildren();
  if (!sessions.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state session-empty";
    empty.textContent = "创建会话后开始录入或检索 Q&A。";
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
      frontendLog("session.row.click", {
        session_id: session.session_id,
        busy: state.busy,
      });
      if (!state.busy) {
        activateSession(session.session_id).catch((error) => {
          frontendError("session.activate.error", {
            session_id: session.session_id,
            message: errorMessage(error),
          });
          setBusy(false, String(error));
        });
      }
    });

    const rowIcon = document.createElement("span");
    rowIcon.className = "row-icon";
    rowIcon.append(icon("message"));

    const title = document.createElement("span");
    title.className = "session-title";
    title.textContent = session.title || "新会话";

    const time = document.createElement("span");
    time.className = "session-time";
    time.textContent = formatRelativeSessionTime(session);

    button.append(rowIcon, title, time);
    elements.sessionsList.append(button);
  }
}

function renderActiveSessionTitle() {
  elements.activeSessionTitle.textContent = "检索结果";
}

function resetMessages(message) {
  stopActiveTyping();
  elements.messages.replaceChildren();
  appendEmptyWorkspace(message);
}

function renderHistoryMessages(messages) {
  const startedAt = performance.now();
  stopActiveTyping();
  elements.messages.replaceChildren();
  if (!messages.length) {
    resetMessages("你好。你可以录入一条 Q&A，也可以提问，我会基于知识库回答并列出来源。");
    frontendLog("session.messages.render.done", {
      count: 0,
      duration_ms: elapsedSince(startedAt),
    });
    return;
  }
  for (const message of messages) {
    if (message.role === appConstants.MESSAGE_ROLE_USER) {
      appendMessage("user", "你", message.content || "", { scroll: false });
      continue;
    }
    if (message.role === appConstants.MESSAGE_ROLE_ASSISTANT_RUN) {
      appendHistoryRunMessage(message);
      continue;
    }
    const node = appendMessage("agent", "Agent", "", { scroll: false });
    renderMarkdown(node.querySelector(".message-body"), message.content || "");
  }
  scrollMessagesToBottom();
  frontendLog("session.messages.render.done", {
    count: messages.length,
    duration_ms: elapsedSince(startedAt),
  });
}

function appendMessage(kind, role, body, options = {}) {
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
  if (options.scroll !== false) {
    scrollMessagesToBottom();
  }
  return message;
}

function appendAgentRunMessage(options = {}) {
  const message = document.createElement("article");
  message.className = "message agent-message run-message";
  if (options.history) {
    message.classList.add("history-run-message");
  }

  const roleNode = document.createElement("div");
  roleNode.className = "message-role";
  roleNode.textContent = "Agent";

  const steps = document.createElement("div");
  steps.className = "run-steps";

  const drafts = document.createElement("div");
  drafts.className = "drafts";

  const answer = document.createElement("div");
  answer.className = "message-body answer-body";

  message.append(roleNode, steps, drafts, answer);
  message._steps = steps;
  message._drafts = drafts;
  message._answer = answer;
  message._answerText = "";
  message._turnDrafts = new Map();
  message._activeAnswerTurn = null;
  message._typingController = options.history ? null : createTypingController(answer);
  if (message._typingController) {
    state.activeTypingController = message._typingController;
  }
  elements.messages.append(message);
  if (options.scroll !== false) {
    scrollMessagesToBottom();
  }
  return message;
}

function appendHistoryRunMessage(historyMessage) {
  const message = appendAgentRunMessage({ history: true, scroll: false });
  const steps = Array.isArray(historyMessage.steps) ? historyMessage.steps : [];
  for (const step of steps) {
    addStep(message, step);
  }
  finishAnswer(message, historyMessage.answer || "", { immediate: true });
  return message;
}

async function streamChat(message, agentMessage) {
  const startedAt = performance.now();
  const streamStats = {
    startedAt,
    eventCount: 0,
    firstEvent: false,
    firstDelta: false,
    finalAnswer: false,
  };
  agentMessage._streamStats = streamStats;
  frontendLog("chat.stream.start", { session_id: state.activeSessionId || "" });
  try {
    const response = await fetch(appConstants.API_CHAT_STREAM_PATH, {
      method: appConstants.HTTP_METHOD_POST,
      credentials: appConstants.FETCH_CREDENTIALS_SAME_ORIGIN,
      headers: { [appConstants.HEADER_CONTENT_TYPE]: appConstants.CONTENT_TYPE_JSON },
      body: JSON.stringify({ session_id: state.activeSessionId, message }),
    });
    frontendLog("chat.stream.open", {
      session_id: state.activeSessionId || "",
      status: response.status,
      duration_ms: elapsedSince(startedAt),
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
          .find((line) => line.startsWith(appConstants.SSE_DATA_PREFIX));
        if (!dataLine) continue;
        renderAgentEvent(agentMessage, JSON.parse(dataLine.slice(appConstants.SSE_DATA_PREFIX.length).trim()));
      }
    }
    if (buffer.trim()) {
      const dataLine = buffer
        .split("\n")
        .find((line) => line.startsWith(appConstants.SSE_DATA_PREFIX));
      if (dataLine) {
        renderAgentEvent(agentMessage, JSON.parse(dataLine.slice(appConstants.SSE_DATA_PREFIX.length).trim()));
      }
    }
    if (agentMessage._typingController) {
      await agentMessage._typingController.whenIdle();
    }
    frontendLog("chat.stream.done", {
      session_id: state.activeSessionId || "",
      count: streamStats.eventCount,
      final_answer: streamStats.finalAnswer,
      duration_ms: elapsedSince(startedAt),
    });
  } catch (error) {
    frontendError("chat.stream.error", {
      session_id: state.activeSessionId || "",
      count: streamStats.eventCount,
      duration_ms: elapsedSince(startedAt),
      message: errorMessage(error),
    });
    throw error;
  }
}

function renderAgentEvent(message, event) {
  recordStreamEvent(message, event);
  const shouldStickToBottom = isNearMessageBottom();
  switch (event.event_type) {
    case appConstants.EVENT_USER_INPUT_RECEIVED:
      addStep(message, "收到输入");
      break;
    case appConstants.EVENT_LLM_CALL_STARTED:
      addStep(message, "调用模型");
      break;
    case appConstants.EVENT_LLM_CALL_FINISHED:
      finishLlmTurn(message, event);
      break;
    case appConstants.EVENT_PROMPT_USAGE_UPDATED:
      updateContextStatus(event.prompt_usage_ratio);
      rememberActiveSessionContext(event.prompt_usage_ratio);
      break;
    case appConstants.EVENT_RUNTIME_CONTEXT_COMPACTION_STARTED:
      addStep(message, contextCompactionStartText(event));
      break;
    case appConstants.EVENT_RUNTIME_CONTEXT_COMPACTION_FINISHED:
      addStep(message, contextCompactionFinishText(event));
      break;
    case appConstants.EVENT_TOOL_CALL_STARTED:
      addToolStep(message, event);
      break;
    case appConstants.EVENT_TOOL_CALL_FINISHED:
      addStep(message, summarizeToolResult(event));
      break;
    case appConstants.EVENT_PERMISSION_REQUESTED:
      showApprovalDialog(message, event);
      break;
    case appConstants.EVENT_PERMISSION_RESOLVED:
      resolveApprovalDialog(event);
      break;
    case appConstants.EVENT_EVIDENCE_CHECKED:
      addStep(message, event.source_count ? `已核对 ${event.source_count} 条来源` : "未使用知识库来源");
      break;
    case appConstants.EVENT_ANSWER_DELTA:
      appendAnswerDelta(message, event.turn ?? 0, event.text || "");
      break;
    case appConstants.EVENT_FINAL_ANSWER_GENERATED:
      finishAnswer(message, event.answer || "");
      break;
    case appConstants.EVENT_ERROR:
      if (event.error_code === appConstants.ERROR_CODE_NOT_AUTHENTICATED) {
        renderRunError(message, event.message || "登录状态已失效。");
        showLogin("登录状态已失效，请重新登录。", "error");
        break;
      }
      renderRunError(message, event.message || "本轮没有完成。");
      break;
    default:
      break;
  }
  if (shouldStickToBottom) {
    scrollMessagesToBottom();
  }
}

function addStep(message, text) {
  const step = document.createElement("div");
  step.className = "run-step";
  step.textContent = text;
  message._steps.append(step);
  return step;
}

function updateContextStatus(promptUsageRatio) {
  const ratio = Number(promptUsageRatio);
  if (!Number.isFinite(ratio)) {
    elements.contextStatus.textContent = "Context --";
    const emptyFill = document.querySelector(".context-fill");
    if (emptyFill) {
      emptyFill.style.width = "0%";
    }
    return;
  }
  const percentage = Math.max(
    appConstants.MIN_CONTEXT_RATIO,
    Math.round(Math.min(appConstants.MAX_CONTEXT_RATIO, ratio) * appConstants.PERCENT_MULTIPLIER),
  );
  elements.contextStatus.textContent = `Context ${percentage}%`;
  const fill = document.querySelector(".context-fill");
  if (fill) {
    fill.style.width = `${Math.min(appConstants.PERCENT_MULTIPLIER, percentage)}%`;
  }
}

function renderContextForSession(sessionId) {
  const session = state.sessions.find((candidate) => candidate.session_id === sessionId);
  updateContextStatus(session?.last_prompt_usage_ratio ?? null);
}

function rememberActiveSessionContext(promptUsageRatio) {
  const ratio = Number(promptUsageRatio);
  const normalizedRatio = Number.isFinite(ratio)
    ? Math.max(appConstants.MIN_CONTEXT_RATIO, Math.min(appConstants.MAX_CONTEXT_RATIO, ratio))
    : null;
  state.sessions = state.sessions.map((session) =>
    session.session_id === state.activeSessionId
      ? { ...session, last_prompt_usage_ratio: normalizedRatio }
      : session
  );
}

function mergeSession(session) {
  const index = state.sessions.findIndex((candidate) => candidate.session_id === session.session_id);
  if (index === -1) {
    state.sessions = [session, ...state.sessions];
    return;
  }
  state.sessions = state.sessions.map((candidate, candidateIndex) =>
    candidateIndex === index ? { ...candidate, ...session } : candidate
  );
}

function createTypingController(node) {
  let visibleText = "";
  let queue = "";
  let timerId = null;
  let finalAnswer = null;
  let completeCallback = null;
  let idleResolvers = [];

  const resolveIdle = () => {
    const resolvers = idleResolvers;
    idleResolvers = [];
    for (const resolve of resolvers) {
      resolve();
    }
  };

  const tick = () => {
    if (!queue) {
      timerId = null;
      if (finalAnswer !== null) {
        renderMarkdown(node, finalAnswer);
        node.classList.remove("typing-caret");
        const callback = completeCallback;
        completeCallback = null;
        if (callback) {
          callback();
        }
        resolveIdle();
      } else {
        resolveIdle();
      }
      return;
    }

    const shouldStickToBottom = isNearMessageBottom();
    const take =
      queue.length > appConstants.TYPING_BURST_THRESHOLD
        ? appConstants.TYPING_BURST_TAKE
        : appConstants.TYPING_SINGLE_TAKE;
    visibleText += queue.slice(0, take);
    queue = queue.slice(take);
    node.textContent = visibleText;
    node.classList.add("typing-caret");
    if (shouldStickToBottom) {
      scrollMessagesToBottom();
    }
    timerId = window.setTimeout(tick, appConstants.TYPING_INTERVAL_MS);
  };

  const start = () => {
    if (!timerId) {
      tick();
    }
  };

  return {
    delta(text) {
      if (!text) return;
      queue += text;
      start();
    },
    final(answer, onComplete) {
      finalAnswer = answer;
      completeCallback = onComplete;
      const pendingText = visibleText + queue;
      if (answer.startsWith(pendingText)) {
        queue += answer.slice(pendingText.length);
      } else if (answer.startsWith(visibleText)) {
        queue = answer.slice(visibleText.length);
      } else {
        visibleText = "";
        queue = answer;
      }
      start();
    },
    reset() {
      if (timerId) {
        window.clearTimeout(timerId);
      }
      visibleText = "";
      queue = "";
      timerId = null;
      finalAnswer = null;
      completeCallback = null;
      node.classList.remove("typing-caret");
      node.textContent = "";
      resolveIdle();
    },
    stop() {
      if (timerId) {
        window.clearTimeout(timerId);
      }
      timerId = null;
      node.classList.remove("typing-caret");
      resolveIdle();
    },
    hasVisibleText() {
      return Boolean(visibleText || queue);
    },
    whenIdle() {
      if (!timerId) {
        return Promise.resolve();
      }
      return new Promise((resolve) => idleResolvers.push(resolve));
    },
  };
}

function stopActiveTyping() {
  if (state.activeTypingController) {
    state.activeTypingController.stop();
    state.activeTypingController = null;
  }
}

function contextCompactionStartText(event) {
  if (event.reason === appConstants.RUNTIME_COMPACTION_REASON_CONTEXT_LENGTH_EXCEEDED) {
    return "上下文超限，正在压缩上下文";
  }
  return "正在压缩上下文";
}

function contextCompactionFinishText(event) {
  if (event.reason === appConstants.RUNTIME_COMPACTION_REASON_CONTEXT_LENGTH_EXCEEDED) {
    return "上下文已压缩，正在重试";
  }
  return "上下文已压缩";
}

function appendAnswerDelta(message, turn, text) {
  if (!text) return;
  const draft = getTurnDraft(message, turn);
  draft.text += text;
  if (message._activeAnswerTurn === null) {
    message._activeAnswerTurn = turn;
  }
  if (message._activeAnswerTurn === turn) {
    message._answerText = draft.text;
    if (message._typingController) {
      message._typingController.delta(text);
    } else {
      message._answer.textContent = draft.text;
    }
    return;
  }
  draft.node.textContent = draft.text;
}

function finishAnswer(message, answer, options = {}) {
  message._answerText = answer;
  if (options.immediate || !message._typingController) {
    renderMarkdown(message._answer, message._answerText);
    message.classList.add("run-complete");
    return;
  }
  message._typingController.final(answer, () => {
    message.classList.add("run-complete");
    if (state.activeTypingController === message._typingController) {
      state.activeTypingController = null;
    }
  });
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
      draft.node.textContent = draft.text;
      draft.node.classList.add("draft-muted");
    }
    if (message._activeAnswerTurn === turn) {
      if (message._typingController) {
        message._typingController.reset();
      }
      message._answerText = "";
      message._answer.textContent = "";
      message._activeAnswerTurn = null;
    }
    return;
  }
  if (draft) {
    message._activeAnswerTurn = turn;
    message._answerText = draft.text;
    if (message._typingController && !message._typingController.hasVisibleText()) {
      message._typingController.delta(draft.text);
    } else if (!message._typingController) {
      message._answer.textContent = draft.text;
    }
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

function showApprovalDialog(message, event) {
  const summary = event.summary || {};
  const approvalId = event.approval_id || "";
  frontendLog("approval.requested", {
    approval_id: approvalId,
    tool_name: summary.tool_name || "",
    timeout_seconds: event.timeout_seconds || 0,
  });
  const statusStep = addApprovalStatusStep(message, "Agent 请求高风险操作确认");
  const overlay = document.createElement("section");
  overlay.className = "approval-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");

  const dialog = document.createElement("article");
  dialog.className = "approval-dialog is-pending";
  dialog.dataset.approvalId = approvalId;

  const heading = document.createElement("div");
  heading.className = "approval-dialog-heading";

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
  status.textContent = `${
    Math.round(Number(event.timeout_seconds || 0) / appConstants.SECONDS_PER_MINUTE) ||
    appConstants.DEFAULT_APPROVAL_TIMEOUT_MINUTES
  } 分钟内确认`;

  heading.append(titleWrap, status);

  const description = document.createElement("p");
  description.className = "approval-description";
  description.textContent = "这是高风险工具调用。确认前，Agent 会暂停等待你的决定。";

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
  risk.textContent = summary.risk || "该操作会修改知识库数据。";

  const actions = document.createElement("div");
  actions.className = "approval-actions";

  const approveButton = document.createElement("button");
  approveButton.type = "button";
  approveButton.className = "approval-button approval-approve";
  approveButton.textContent = "允许执行";
  approveButton.addEventListener("click", () => submitApproval(dialog, appConstants.APPROVAL_DECISION_APPROVE));

  const denyButton = document.createElement("button");
  denyButton.type = "button";
  denyButton.className = "approval-button approval-deny";
  denyButton.textContent = "拒绝";
  denyButton.addEventListener("click", () => submitApproval(dialog, appConstants.APPROVAL_DECISION_DENY));

  actions.append(approveButton, denyButton);
  dialog.append(heading, description, body, risk, actions);
  overlay.append(dialog);
  document.body.append(overlay);
  state.approvalDialogs.set(approvalId, { overlay, dialog, statusStep });
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function addApprovalStatusStep(message, text) {
  const step = document.createElement("div");
  step.className = "approval-status-note";

  const dot = document.createElement("span");
  dot.className = "approval-status-dot";

  const label = document.createElement("span");
  label.className = "approval-status-text";
  label.textContent = text;

  step.append(dot, label);
  message._steps.append(step);
  return step;
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

async function submitApproval(dialog, decision) {
  const approvalId = dialog.dataset.approvalId;
  if (!approvalId) return;
  const startedAt = performance.now();
  frontendLog("approval.submit.start", { approval_id: approvalId, decision });
  setApprovalDialogState(
    dialog,
    decision === appConstants.APPROVAL_DECISION_APPROVE
      ? appConstants.APPROVAL_STATUS_SUBMITTING_APPROVE
      : appConstants.APPROVAL_STATUS_SUBMITTING_DENY,
  );
  try {
    const result = await postJson(`${appConstants.API_APPROVALS_BASE_PATH}/${encodeURIComponent(approvalId)}`, { decision });
    if (!result.ok) {
      setApprovalDialogState(dialog, appConstants.APPROVAL_STATUS_SUBMIT_ERROR, result.message || "确认提交失败");
      frontendLog("approval.submit.done", {
        ok: false,
        approval_id: approvalId,
        decision,
        error_code: result.error_code || "",
        duration_ms: elapsedSince(startedAt),
      });
      return;
    }
    frontendLog("approval.submit.done", {
      ok: true,
      approval_id: approvalId,
      decision,
      duration_ms: elapsedSince(startedAt),
    });
  } catch (error) {
    setApprovalDialogState(dialog, appConstants.APPROVAL_STATUS_SUBMIT_ERROR, String(error));
    frontendError("approval.submit.error", {
      approval_id: approvalId,
      decision,
      duration_ms: elapsedSince(startedAt),
      message: errorMessage(error),
    });
  }
}

function resolveApprovalDialog(event) {
  frontendLog("approval.resolve", {
    approval_id: event.approval_id || "",
    status: event.status || "",
  });
  const record = state.approvalDialogs.get(event.approval_id);
  if (!record) return;
  const status = event.status || appConstants.APPROVAL_STATUS_FALLBACK;
  setApprovalDialogState(record.dialog, status);
  updateApprovalStatusStep(record.statusStep, approvalResultText(status), status);
  state.approvalDialogs.delete(event.approval_id);
  record.overlay.remove();
}

function clearOpenApprovalDialogs(status) {
  frontendLog("approval.clear_open", {
    status,
    count: state.approvalDialogs.size,
  });
  for (const [approvalId, record] of state.approvalDialogs.entries()) {
    setApprovalDialogState(record.dialog, status);
    updateApprovalStatusStep(record.statusStep, approvalResultText(status), status);
    record.overlay.remove();
    state.approvalDialogs.delete(approvalId);
  }
}

function updateApprovalStatusStep(step, text, status) {
  const label = step.querySelector(".approval-status-text");
  if (label) {
    label.textContent = text;
  }
  step.classList.remove("is-approved", "is-denied", "is-expired", "is-cancelled", "is-error");
  step.classList.add(`is-${status}`);
}

function approvalResultText(status) {
  if (status === appConstants.APPROVAL_STATUS_APPROVED) return "已允许高风险操作，继续执行";
  if (status === appConstants.APPROVAL_STATUS_EXPIRED) return "确认已超时，操作未执行";
  if (status === appConstants.APPROVAL_STATUS_CANCELLED) return "连接已断开，操作未执行";
  return "已拒绝高风险操作，操作未执行";
}

function setApprovalDialogState(dialog, status, message = "") {
  const statusNode = dialog.querySelector(".approval-status");
  const buttons = dialog.querySelectorAll(".approval-button");
  const disableButtons = ![appConstants.APPROVAL_STATUS_PENDING, appConstants.APPROVAL_STATUS_SUBMIT_ERROR].includes(status);
  for (const button of buttons) {
    button.disabled = disableButtons;
  }
  dialog.classList.remove("is-pending", "is-approved", "is-denied", "is-expired", "is-cancelled", "is-error");
  if (status === appConstants.APPROVAL_STATUS_APPROVED || status === appConstants.APPROVAL_STATUS_SUBMITTING_APPROVE) {
    dialog.classList.add("is-approved");
    statusNode.textContent = status === appConstants.APPROVAL_STATUS_APPROVED ? "已允许，继续执行" : "正在提交允许";
  } else if (status === appConstants.APPROVAL_STATUS_DENIED || status === appConstants.APPROVAL_STATUS_SUBMITTING_DENY) {
    dialog.classList.add("is-denied");
    statusNode.textContent = status === appConstants.APPROVAL_STATUS_DENIED ? "已拒绝，操作未执行" : "正在提交拒绝";
  } else if (status === appConstants.APPROVAL_STATUS_EXPIRED) {
    dialog.classList.add("is-expired");
    statusNode.textContent = "已超时，操作未执行";
  } else if (status === appConstants.APPROVAL_STATUS_CANCELLED) {
    dialog.classList.add("is-cancelled");
    statusNode.textContent = "连接已断开，操作未执行";
  } else if (status === appConstants.APPROVAL_STATUS_SUBMIT_ERROR) {
    dialog.classList.add("is-error");
    statusNode.textContent = message || "确认提交失败";
    for (const button of buttons) {
      button.disabled = false;
    }
  } else {
    dialog.classList.add("is-pending");
    statusNode.textContent = "等待确认";
  }
}

function toolDisplayName(toolName) {
  const labels = {
    [appConstants.TOOL_NAME_HYBRID_SEARCH_QA_CARDS]: "搜索知识库",
    [appConstants.TOOL_NAME_SEARCH_QA_CARDS]: "搜索知识库",
    [appConstants.TOOL_NAME_SAVE_QA_CARD]: "保存知识卡片",
    [appConstants.TOOL_NAME_READ_QA_CARD]: "读取知识卡片",
    [appConstants.TOOL_NAME_LIST_RECENT_CARDS]: "读取最近卡片",
    [appConstants.TOOL_NAME_UPDATE_QA_CARD]: "更新知识卡片",
    [appConstants.TOOL_NAME_DELETE_QA_CARD]: "删除知识卡片",
    [appConstants.TOOL_NAME_MERGE_QA_CARDS]: "合并知识卡片",
    [appConstants.TOOL_NAME_CREATE_TODO]: "保存待办",
    [appConstants.TOOL_NAME_LIST_TODOS]: "查询待办",
    [appConstants.TOOL_NAME_UPDATE_TODO]: "更新待办",
  };
  return labels[toolName] || "调用工具";
}

function summarizeToolResult(event) {
  const output = event.output || {};
  if (output.error_code === appConstants.TOOL_OUTPUT_ERROR_CODE_PERMISSION_DENIED) {
    return "操作未执行";
  }
  if (output.ok === false) {
    return `${toolDisplayName(event.tool_name)}失败`;
  }
  if (Array.isArray(output.cards)) {
    return output.cards.length ? `找到 ${output.cards.length} 条记录` : "未找到相关记录";
  }
  if (Array.isArray(output.todos)) {
    return output.todos.length ? `找到 ${output.todos.length} 条待办` : "未找到待办";
  }
  if (output.todo && output.todo.todo_id) {
    return output.todo.status === appConstants.TOOL_OUTPUT_TODO_STATUS_OPEN ? "待办已保存" : "待办已更新";
  }
  if (output.card_id) {
    return "知识卡片已保存";
  }
  return `${toolDisplayName(event.tool_name)}完成`;
}

function renderMarkdown(container, markdown) {
  const startedAt = performance.now();
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
  frontendLog("markdown.render.done", {
    length: markdown.length,
    duration_ms: elapsedSince(startedAt),
  });
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
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|<br\s*\/?>)/gi;
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
    } else if (/^<br\s*\/?>$/i.test(token)) {
      parent.append(document.createElement("br"));
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
  frontendLog("ui.busy", { busy, message: text });
}

async function loadRecentCards() {
  const startedAt = performance.now();
  frontendLog("cards.recent.load.start");
  elements.cardsTitle.textContent = "保存记录";
  setCardsLoading(true);
  const result = await getJson(
    `${appConstants.API_CARDS_RECENT_PATH}?${appConstants.QUERY_PARAM_LIMIT}=${appConstants.CARD_QUERY_LIMIT}`,
  ).finally(() =>
    setCardsLoading(false),
  );
  if (!result.ok) {
    renderCards([], result.message || "读取最近卡片失败。");
    frontendLog("cards.recent.load.done", {
      ok: false,
      error_code: result.error_code || "",
      duration_ms: elapsedSince(startedAt),
    });
    return;
  }
  renderCards(result.cards || []);
  frontendLog("cards.recent.load.done", {
    ok: true,
    count: (result.cards || []).length,
    duration_ms: elapsedSince(startedAt),
  });
}

async function searchCards(query) {
  const startedAt = performance.now();
  frontendLog("cards.search.start");
  elements.cardsTitle.textContent = "检索结果";
  setCardsLoading(true);
  const result = await getJson(
    `${appConstants.API_CARDS_SEARCH_PATH}?${appConstants.QUERY_PARAM_QUERY}=${encodeURIComponent(query)}&${appConstants.QUERY_PARAM_LIMIT}=${appConstants.CARD_QUERY_LIMIT}`,
  ).finally(() =>
    setCardsLoading(false),
  );
  if (!result.ok) {
    renderCards([], result.message || "搜索失败。");
    frontendLog("cards.search.done", {
      ok: false,
      error_code: result.error_code || "",
      duration_ms: elapsedSince(startedAt),
    });
    return;
  }
  renderCards(result.cards || []);
  frontendLog("cards.search.done", {
    ok: true,
    count: (result.cards || []).length,
    duration_ms: elapsedSince(startedAt),
  });
}

function renderCards(cards, emptyText = "还没有知识卡片。保存一条 Q&A 后会显示在这里。") {
  const startedAt = performance.now();
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
    const text = document.createElement("span");
    text.textContent = emptyText;
    empty.append(text);
    elements.cardsList.append(empty);
    frontendLog("cards.render.done", {
      count: 0,
      duration_ms: elapsedSince(startedAt),
    });
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

    const rowIcon = document.createElement("span");
    rowIcon.className = "row-icon";
    rowIcon.append(icon("file"));

    const content = document.createElement("span");
    content.className = "row-content";

    const question = document.createElement("strong");
    question.textContent = card.question || card.card_id;

    const summary = document.createElement("p");
    summary.textContent = card.summary || card.answer_snippet || "";

    const meta = document.createElement("div");
    meta.className = "card-meta";
    meta.textContent = [card.category, card.source_type || "unknown", formatTimestamp(card.created_at)]
      .filter(Boolean)
      .join(" · ");

    content.append(question, summary, meta);
    button.append(rowIcon, content);
    elements.cardsList.append(button);
  }
  frontendLog("cards.render.done", {
    count: cards.length,
    duration_ms: elapsedSince(startedAt),
  });
}

async function loadCardDetail(cardId) {
  if (!cardId) return;
  const startedAt = performance.now();
  frontendLog("card.detail.load.start", { card_id: cardId });
  state.selectedCardId = cardId;
  openCardDetail();
  markSelectedCard(cardId);
  const result = await getJson(`${appConstants.API_CARDS_BASE_PATH}/${encodeURIComponent(cardId)}`);
  if (!result.ok) {
    elements.cardDetail.className = "card-detail empty-state";
    elements.cardDetail.textContent = result.message || "读取卡片详情失败。";
    frontendLog("card.detail.load.done", {
      ok: false,
      card_id: cardId,
      error_code: result.error_code || "",
      duration_ms: elapsedSince(startedAt),
    });
    return;
  }
  renderCardDetail(result.card);
  frontendLog("card.detail.load.done", {
    ok: true,
    card_id: cardId,
    duration_ms: elapsedSince(startedAt),
  });
}

function openCardDetail() {
  elements.cardsPane.classList.add("has-card-detail");
}

function closeCardDetail() {
  state.selectedCardId = null;
  elements.cardsPane.classList.remove("has-card-detail");
  markSelectedCard(null);
  elements.cardDetail.className = "card-detail empty-state";
  elements.cardDetail.textContent = "选择一张知识卡片查看来源详情。";
}

function renderCardDetail(card) {
  const startedAt = performance.now();
  elements.cardDetail.className = "card-detail";
  const keywords = Array.isArray(card.keywords) ? card.keywords.join(", ") : "";
  elements.cardDetail.innerHTML = "";

  const cardBody = document.createElement("article");
  cardBody.className = "knowledge-card";

  const questionBlock = document.createElement("section");
  questionBlock.className = "knowledge-section knowledge-question";
  const questionLabel = document.createElement("div");
  questionLabel.className = "knowledge-label";
  questionLabel.textContent = "问题";
  const questionTitle = document.createElement("h4");
  questionTitle.textContent = card.question || card.card_id || "";
  const copyButton = document.createElement("button");
  copyButton.className = "inline-copy-button";
  copyButton.type = "button";
  copyButton.title = "复制问题";
  copyButton.setAttribute("aria-label", "复制问题");
  copyButton.append(icon("copy"));
  questionBlock.append(questionLabel, questionTitle, copyButton);

  const summaryBlock = document.createElement("section");
  summaryBlock.className = "knowledge-section";
  appendKnowledgeText(summaryBlock, "摘要", card.summary || card.answer || "");

  const answerBlock = document.createElement("section");
  answerBlock.className = "knowledge-section";
  appendKnowledgeText(answerBlock, "原始答案", card.answer || "");

  const metaGrid = document.createElement("section");
  metaGrid.className = "knowledge-meta-grid";
  metaGrid.append(
    metaItem("分类", card.category || "未分类", "chip"),
    metaItem("关键词", keywords || "无"),
    metaItem("创建时间", formatTimestamp(card.created_at, { detail: true })),
    metaItem("更新时间", formatTimestamp(card.updated_at, { detail: true })),
    metaItem("来源类型", card.source_type || "unknown"),
    metaItem("card_id", card.card_id || "")
  );

  const sources = document.createElement("section");
  sources.className = "source-list-section";
  const sourceTitle = document.createElement("div");
  sourceTitle.className = "knowledge-label";
  sourceTitle.textContent = "来源";
  const sourceList = document.createElement("div");
  sourceList.className = "source-list";
  sourceList.append(
    sourceRow("Q&A 卡片", card.card_id || "", "100%"),
    sourceRow(card.source_type || appConstants.DEFAULT_QA_SOURCE_TYPE, "PostgreSQL", "事实源")
  );
  const sourceLink = document.createElement("button");
  sourceLink.className = "source-link";
  sourceLink.type = "button";
  sourceLink.append(document.createTextNode("查看原文"), icon("external"));
  sources.append(sourceTitle, sourceList, sourceLink);

  cardBody.append(questionBlock, summaryBlock, answerBlock, metaGrid, sources);
  elements.cardDetail.append(cardBody);
  frontendLog("card.detail.render.done", {
    card_id: card.card_id || "",
    duration_ms: elapsedSince(startedAt),
  });
}

function formatTimestamp(value, options = {}) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const formatter = options.detail ? detailTimeFormatter : cardTimeFormatter;
  const suffix = options.detail ? " (UTC+8)" : "";
  return `${formatter.format(date)}${suffix}`;
}

function formatRelativeSessionTime(session) {
  const value = session.updated_at || session.created_at;
  if (!value) return "";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";

  const diffMs = Math.max(0, Date.now() - date.getTime());
  const diffMinutes = Math.floor(diffMs / appConstants.MILLISECONDS_PER_MINUTE);

  if (diffMinutes < appConstants.JUST_NOW_MINUTES_THRESHOLD) return "刚刚";
  if (diffMinutes < appConstants.MINUTES_PER_HOUR) return `${diffMinutes} 分`;

  const diffHours = Math.floor(diffMinutes / appConstants.MINUTES_PER_HOUR);
  if (diffHours < appConstants.HOURS_PER_DAY) return `${diffHours} 时`;

  const diffDays = Math.floor(diffHours / appConstants.HOURS_PER_DAY);
  if (diffDays < appConstants.DAYS_PER_WEEK) return `${diffDays} 天`;

  const diffWeeks = Math.floor(diffDays / appConstants.DAYS_PER_WEEK);
  if (diffWeeks < appConstants.WEEKS_PER_MONTH) return `${diffWeeks} 周`;

  if (diffDays < appConstants.DAYS_PER_YEAR) {
    return `${Math.min(appConstants.DISPLAY_MONTHS_PER_YEAR, Math.floor(diffDays / appConstants.DAYS_PER_MONTH))} 月`;
  }

  return `${Math.floor(diffDays / appConstants.DAYS_PER_YEAR)} 年`;
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
    if (!collapsed && window.matchMedia(appConstants.MOBILE_MEDIA_QUERY).matches) {
      state.rightCollapsed = true;
      window.localStorage.setItem(appConstants.RIGHT_PANE_COLLAPSED_KEY, String(state.rightCollapsed));
    }
    window.localStorage.setItem(appConstants.LEFT_PANE_COLLAPSED_KEY, String(collapsed));
  } else {
    state.rightCollapsed = collapsed;
    if (!collapsed && window.matchMedia(appConstants.MOBILE_MEDIA_QUERY).matches) {
      state.leftCollapsed = true;
      window.localStorage.setItem(appConstants.LEFT_PANE_COLLAPSED_KEY, String(state.leftCollapsed));
    }
    window.localStorage.setItem(appConstants.RIGHT_PANE_COLLAPSED_KEY, String(collapsed));
  }
  applyPaneState();
  frontendLog("ui.pane_collapsed", {
    side,
    collapsed,
    left_collapsed: state.leftCollapsed,
    right_collapsed: state.rightCollapsed,
  });
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
  loadingNode.textContent = "正在读取知识卡片";
  elements.cardsList.append(loadingNode);
}

function markSelectedCard(cardId) {
  for (const button of elements.cardsList.querySelectorAll(".card-row")) {
    const selected = Boolean(cardId) && button.dataset.cardId === cardId;
    button.classList.toggle("is-selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  }
}

function scrollMessagesToBottom() {
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function isNearMessageBottom(threshold = appConstants.NEAR_MESSAGE_BOTTOM_THRESHOLD) {
  const distance = elements.messages.scrollHeight - elements.messages.clientHeight - elements.messages.scrollTop;
  return distance <= threshold;
}

function isMobileViewport() {
  return window.matchMedia(appConstants.MOBILE_MEDIA_QUERY).matches;
}

function addDetail(list, label, value, valueClass = "") {
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  if (valueClass) {
    description.className = valueClass;
  }
  description.textContent = value || "";
  list.append(term, description);
}

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.classList.add("icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#icon-${name}`);
  svg.append(use);
  return svg;
}

function appendEmptyWorkspace(message) {
  const empty = document.createElement("section");
  empty.className = "empty-workspace";
  const emptyIcon = icon("tray");
  emptyIcon.classList.add("empty-icon");
  const title = document.createElement("h2");
  title.textContent = "个人知识库问答助手";
  const body = document.createElement("p");
  body.textContent = message || "从右侧选择知识卡片查看详情，或在下方提问开始对话。";
  empty.append(emptyIcon, title, body);
  elements.messages.append(empty);
}

function appendKnowledgeText(container, label, text) {
  const title = document.createElement("div");
  title.className = "knowledge-label";
  title.textContent = label;
  const paragraph = document.createElement("p");
  paragraph.textContent = text || "暂无内容";
  container.append(title, paragraph);
}

function metaItem(label, value, variant = "") {
  const item = document.createElement("div");
  item.className = "knowledge-meta-item";
  const labelNode = document.createElement("span");
  labelNode.textContent = label;
  const valueNode = document.createElement("strong");
  if (variant) {
    valueNode.className = variant;
  }
  valueNode.textContent = value || "";
  item.append(labelNode, valueNode);
  return item;
}

function sourceRow(name, detail, score) {
  const row = document.createElement("div");
  row.className = "source-row";
  const fileIcon = document.createElement("span");
  fileIcon.className = "row-icon";
  fileIcon.append(icon("file"));
  const title = document.createElement("strong");
  title.textContent = name;
  const detailNode = document.createElement("span");
  detailNode.textContent = detail;
  const scoreNode = document.createElement("span");
  scoreNode.textContent = score;
  row.append(fileIcon, title, detailNode, scoreNode);
  return row;
}

function frontendLog(event, fields = {}) {
  console.info("[pka]", diagnosticEvent(event, fields));
}

function frontendError(event, fields = {}) {
  console.error("[pka]", diagnosticEvent(event, fields));
}

function diagnosticEvent(event, fields) {
  return {
    event,
    trace_id: FRONTEND_TRACE_ID,
    elapsed_ms: Math.round(performance.now() - FRONTEND_START_MS),
    ...fields,
  };
}

function elapsedSince(startedAt) {
  return Math.round(performance.now() - startedAt);
}

function errorMessage(error) {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function logResourceTiming(pattern) {
  const entries = performance
    .getEntriesByType("resource")
    .filter((entry) => entry.name.includes(pattern));
  const entry = entries[entries.length - 1];
  if (!entry) {
    frontendLog("resource.missing", { resource: pattern });
    return;
  }
  frontendLog("resource.timing", {
    resource: pattern,
    duration_ms: Math.round(entry.duration),
    transfer_size: Math.round(entry.transferSize || 0),
    encoded_size: Math.round(entry.encodedBodySize || 0),
    decoded_size: Math.round(entry.decodedBodySize || 0),
  });
}

function recordStreamEvent(message, event) {
  const stats = message._streamStats;
  if (!stats) return;
  stats.eventCount += 1;
  if (!stats.firstEvent) {
    stats.firstEvent = true;
    frontendLog("chat.stream.first_event", {
      session_id: state.activeSessionId || "",
      event_type: event.event_type || "",
      duration_ms: elapsedSince(stats.startedAt),
    });
  }
  if (event.event_type === appConstants.EVENT_ANSWER_DELTA && !stats.firstDelta) {
    stats.firstDelta = true;
    frontendLog("chat.stream.first_delta", {
      session_id: state.activeSessionId || "",
      duration_ms: elapsedSince(stats.startedAt),
    });
  }
  if (event.event_type === appConstants.EVENT_FINAL_ANSWER_GENERATED && !stats.finalAnswer) {
    stats.finalAnswer = true;
    frontendLog("chat.stream.final_answer", {
      session_id: state.activeSessionId || "",
      count: stats.eventCount,
      duration_ms: elapsedSince(stats.startedAt),
    });
  }
}

bootApp().catch((error) => {
  frontendError("boot.error", { message: errorMessage(error) });
  showLogin(String(error), "error");
});
