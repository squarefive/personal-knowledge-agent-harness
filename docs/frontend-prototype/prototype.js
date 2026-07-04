const prototypeData = window.PKA_MOCK_DATA;
const prototypeScenarios = window.PKA_SCENARIOS;

const prototypeParams = new URLSearchParams(window.location.search);
const requestedScenario = prototypeParams.get("scenario") || window.location.hash.replace(/^#/, "");
const initialScenarioId = prototypeScenarios[requestedScenario] ? requestedScenario : "loggedOut";

const prototypeState = {
  scenarioId: initialScenarioId,
  scenario: structuredClone(prototypeScenarios[initialScenarioId]),
  authenticated: prototypeScenarios[initialScenarioId].auth === "authenticated",
  sessions: structuredClone(prototypeScenarios[initialScenarioId].sessions || []),
  cards: structuredClone(prototypeScenarios[initialScenarioId].cards || []),
  selectedCardId: prototypeScenarios[initialScenarioId].selectedCardId || null,
  streamControllers: new Map(),
};

installPrototypeControls();
installMockFetch();
installScenarioAutomation();

function applyScenarioState(scenarioId) {
  const scenario = prototypeScenarios[scenarioId];
  if (!scenario) return;
  prototypeState.scenarioId = scenarioId;
  prototypeState.scenario = structuredClone(scenario);
  prototypeState.authenticated = scenario.auth === "authenticated";
  prototypeState.sessions = structuredClone(scenario.sessions || []);
  prototypeState.cards = structuredClone(scenario.cards || []);
  prototypeState.selectedCardId = scenario.selectedCardId || null;
}

function installPrototypeControls() {
  window.addEventListener("DOMContentLoaded", () => {
    const panel = document.querySelector("#prototypePanel");
    const select = document.querySelector("#scenarioSelect");
    if (!panel || !select) return;
    panel.hidden = prototypeParams.get("controls") !== "1";
    for (const [id, scenario] of Object.entries(prototypeScenarios)) {
      const option = document.createElement("option");
      option.value = id;
      option.textContent = scenario.label;
      select.append(option);
    }
    select.value = prototypeState.scenarioId;
    select.addEventListener("change", () => {
      const next = new URL(window.location.href);
      next.searchParams.set("scenario", select.value);
      next.searchParams.set("controls", "1");
      window.location.href = next.href;
    });
  });
}

function installMockFetch() {
  const realFetch = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    const requestUrl = typeof input === "string" ? input : input.url;
    const url = new URL(requestUrl, window.location.origin);
    if (!url.pathname.startsWith("/api/")) {
      return realFetch(input, init);
    }
    return routeMockApi(url, init);
  };
}

async function routeMockApi(url, init) {
  const method = (init.method || "GET").toUpperCase();
  const pathname = url.pathname;

  if (pathname === "/api/auth/me" && method === "GET") {
    return jsonResponse(
      prototypeState.authenticated
        ? { ok: true, user: prototypeState.scenario.user || prototypeData.users.primary }
        : { ok: false, error_code: "not_authenticated" },
    );
  }
  if (pathname === "/api/auth/request-code" && method === "POST") {
    return jsonResponse({ ok: true });
  }
  if (pathname === "/api/auth/verify-code" && method === "POST") {
    applyScenarioState("chatWithSources");
    return jsonResponse({ ok: true, user: prototypeData.users.primary });
  }
  if (pathname === "/api/auth/logout" && method === "POST") {
    applyScenarioState("loggedOut");
    return jsonResponse({ ok: true });
  }

  if (pathname === "/api/sessions" && method === "GET") {
    return jsonResponse({ ok: true, sessions: prototypeState.sessions });
  }
  if (pathname === "/api/sessions" && method === "POST") {
    const session = {
      session_id: `sess_mock_${Date.now().toString(36)}`,
      title: "新的知识库对话",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      prompt_usage_ratio: 0.02,
      context_percent: 2,
    };
    prototypeState.sessions = [session, ...prototypeState.sessions];
    prototypeData.messagesBySession[session.session_id] = [];
    return jsonResponse({ ok: true, session });
  }

  const sessionPatchMatch = pathname.match(/^\/api\/sessions\/([^/]+)$/);
  if (sessionPatchMatch && method === "PATCH") {
    const sessionId = decodeURIComponent(sessionPatchMatch[1]);
    const body = parseJsonBody(init);
    const session = prototypeState.sessions.find((item) => item.session_id === sessionId);
    if (session) {
      session.title = body.title || session.title;
      session.updated_at = new Date().toISOString();
    }
    return jsonResponse({ ok: true, session });
  }

  const sessionMessagesMatch = pathname.match(/^\/api\/sessions\/([^/]+)\/messages$/);
  if (sessionMessagesMatch && method === "GET") {
    const sessionId = decodeURIComponent(sessionMessagesMatch[1]);
    const session = prototypeState.sessions.find((item) => item.session_id === sessionId);
    return jsonResponse({
      ok: true,
      session: normalizeSession(session),
      messages: historyMessagesForSession(sessionId),
    });
  }

  if (pathname === "/api/cards/recent" && method === "GET") {
    return jsonResponse({ ok: true, cards: prototypeState.cards });
  }
  if (pathname === "/api/cards/search" && method === "GET") {
    const query = url.searchParams.get("q") || "";
    const cards =
      !query || query.includes("报销") || query.includes("发票")
        ? [prototypeData.cards.travel, prototypeData.cards.medical]
        : [];
    return jsonResponse({ ok: true, cards });
  }

  const cardMatch = pathname.match(/^\/api\/cards\/(.+)$/);
  if (cardMatch && method === "GET") {
    const cardId = decodeURIComponent(cardMatch[1]);
    const card = [...prototypeState.cards, ...Object.values(prototypeData.cards)].find((item) => item.card_id === cardId);
    return jsonResponse(card ? { ok: true, card } : { ok: false, message: "读取卡片详情失败。" });
  }

  if (pathname === "/api/chat/stream" && method === "POST") {
    const body = parseJsonBody(init);
    return shouldTriggerSaveApproval(body.message)
      ? streamApprovalResponse(body)
      : streamNormalAnswerResponse(body);
  }

  const approvalMatch = pathname.match(/^\/api\/approvals\/(.+)$/);
  if (approvalMatch && method === "POST") {
    const approvalId = decodeURIComponent(approvalMatch[1]);
    const body = parseJsonBody(init);
    resolveMockApproval(approvalId, body.decision === "approve" ? "approved" : "denied");
    return jsonResponse({ ok: true });
  }

  return jsonResponse({ ok: false, message: `Unhandled mock endpoint: ${method} ${pathname}` }, 404);
}

function historyMessagesForSession(sessionId) {
  const rawMessages = prototypeData.messagesBySession[sessionId] || prototypeState.scenario.messages || [];
  return rawMessages.map((message) => {
    if (message.role === "user") {
      return { role: "user", content: message.text || message.content || "" };
    }
    if (message.role === "agent") {
      return {
        role: "assistant_run",
        steps: message.steps || [],
        answer: message.text || message.answer || "",
      };
    }
    return { role: "assistant", content: message.text || message.content || "" };
  });
}

function streamNormalAnswerResponse(body) {
  const answer = prototypeData.normalAnswer;
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      const events = [
        { event_type: "user_input_received" },
        { event_type: "llm_call_started" },
        { event_type: "llm_call_finished", content: "" },
        { event_type: "prompt_usage_updated", prompt_usage_ratio: 0.45 },
        {
          event_type: "tool_call_started",
          tool_name: "hybrid_search_qa_cards",
          tool_args: { question: body.message || answer.userText },
        },
        {
          event_type: "tool_call_finished",
          tool_name: "hybrid_search_qa_cards",
          output: { ok: true, card_ids: ["qa_medical_reimburse_001", "qa_identity_docs_002"] },
        },
        { event_type: "evidence_checked", source_count: answer.sourceCount },
        { event_type: "answer_delta", turn: 0, text: answer.answer },
        { event_type: "final_answer_generated", answer: answer.answer },
      ];
      for (const event of events) {
        enqueueSse(controller, encoder, event);
      }
      rememberMockConversation(body.message || answer.userText, answer.answer, answer.steps);
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream; charset=utf-8" },
  });
}

function streamApprovalResponse(body) {
  const approval = prototypeData.approvals.pendingSave;
  const approvalId = approval.approval_id;
  const encoder = new TextEncoder();
  let controllerRef;
  const stream = new ReadableStream({
    start(controller) {
      controllerRef = controller;
      prototypeState.streamControllers.set(approvalId, controller);
      const events = [
        { event_type: "user_input_received" },
        { event_type: "llm_call_started" },
        { event_type: "llm_call_finished", content: "" },
        { event_type: "prompt_usage_updated", prompt_usage_ratio: 0.42 },
        {
          event_type: "tool_call_started",
          tool_name: "save_qa_card",
          tool_args: { question: body.message || prototypeData.generatedAnswer.userText },
        },
        {
          event_type: "permission_requested",
          approval_id: approvalId,
          timeout_seconds: 300,
          summary: {
            title: approval.title,
            tool_name: approval.toolName,
            tool_label: approval.toolLabel,
            target_label: approval.targetLabel,
            target: approval.target,
            changes: approval.changes,
            preview: approval.preview,
            risk: approval.risk,
          },
        },
      ];
      for (const event of events) {
        enqueueSse(controller, encoder, event);
      }
    },
    cancel() {
      prototypeState.streamControllers.delete(approvalId);
    },
  });
  stream._mockEncoder = encoder;
  stream._mockController = controllerRef;
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream; charset=utf-8" },
  });
}

function resolveMockApproval(approvalId, status) {
  const controller = prototypeState.streamControllers.get(approvalId);
  if (!controller) return;
  const encoder = new TextEncoder();
  enqueueSse(controller, encoder, { event_type: "permission_resolved", approval_id: approvalId, status });
  if (status === "approved") {
    addSavedInvoiceCard();
    enqueueSse(controller, encoder, {
      event_type: "tool_call_finished",
      tool_name: "save_qa_card",
      output: { ok: true, card_id: "qa_e_invoice_print_008" },
    });
    enqueueSse(controller, encoder, { event_type: "evidence_checked", source_count: 1 });
    enqueueSse(controller, encoder, {
      event_type: "final_answer_generated",
      answer: "已允许执行，我会继续完成保存流程。",
    });
    rememberMockConversation(
      prototypeData.generatedAnswer.userText,
      "已允许执行，我会继续完成保存流程。",
      ["识别保存意图", "等待用户审批", "保存 Q&A 卡片", "刷新知识卡片列表"],
    );
  } else {
    enqueueSse(controller, encoder, {
      event_type: "tool_call_finished",
      tool_name: "save_qa_card",
      output: { ok: false, error_code: "permission_denied" },
    });
    enqueueSse(controller, encoder, {
      event_type: "final_answer_generated",
      answer: "已拒绝高风险操作，操作未执行。",
    });
    rememberMockConversation(
      prototypeData.generatedAnswer.userText,
      "已拒绝高风险操作，操作未执行。",
      ["识别保存意图", "等待用户审批", "用户拒绝保存"],
    );
  }
  controller.close();
  prototypeState.streamControllers.delete(approvalId);
}

function shouldTriggerSaveApproval(message = "") {
  const normalizedMessage = String(message).toLowerCase();
  return ["保存", "写入", "q&a", "卡片"].some((keyword) => normalizedMessage.includes(keyword));
}

function addSavedInvoiceCard() {
  const savedCard = structuredClone(prototypeData.cards.savedInvoice);
  if (prototypeState.cards.some((card) => card.card_id === savedCard.card_id)) return;
  prototypeState.cards = [savedCard, ...prototypeState.cards];
}

function rememberMockConversation(userText, answerText, steps) {
  const sessionId = prototypeState.sessions[0]?.session_id || prototypeState.scenario.activeSessionId;
  if (!sessionId) return;
  const messages = prototypeData.messagesBySession[sessionId] || [];
  messages.push({ role: "user", author: "你", text: userText });
  messages.push({ role: "agent", author: "Agent", text: answerText, steps, sources: [] });
  prototypeData.messagesBySession[sessionId] = messages;
  const session = prototypeState.sessions.find((item) => item.session_id === sessionId);
  if (session) {
    session.updated_at = new Date().toISOString();
    session.context_percent = Math.max(session.context_percent || 0, 45);
    session.prompt_usage_ratio = (session.context_percent || 0) / 100;
  }
}

function enqueueSse(controller, encoder, event) {
  controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
}

function installScenarioAutomation() {
  if (!["toolApprovalPending", "toolApprovalDenied"].includes(prototypeState.scenarioId)) return;
  window.addEventListener("load", async () => {
    await delay(400);
    const textarea = document.querySelector("#messageInput");
    const form = document.querySelector("#chatForm");
    if (!textarea || !form) return;
    textarea.value = prototypeData.generatedAnswer.userText;
    form.requestSubmit();
    if (prototypeState.scenarioId === "toolApprovalDenied") {
      await delay(500);
      document.querySelector(".approval-deny")?.click();
    }
  });
}

function normalizeSession(session) {
  if (!session) return null;
  return {
    ...session,
    prompt_usage_ratio: session.prompt_usage_ratio ?? (session.context_percent || 0) / 100,
  };
}

function parseJsonBody(init) {
  if (!init.body) return {};
  try {
    return JSON.parse(init.body);
  } catch {
    return {};
  }
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}
