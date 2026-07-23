const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
let unauthorizedHandler = null;

export class AuthenticationError extends Error {
  constructor(message, code) {
    super(message);
    this.name = "AuthenticationError";
    this.code = code;
  }
}

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler;
}

async function request(path, options = {}) {
  const headers = {
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(options.headers || {})
  };

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    credentials: "include"
  });

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    const apiError = payload?.detail?.error || payload?.error;
    const message = apiError?.message || response.statusText || "Запрос не выполнен";
    if (["AUTH_REQUIRED", "SESSION_EXPIRED"].includes(apiError?.code)) {
      unauthorizedHandler?.();
      throw new AuthenticationError(message, apiError.code);
    }
    throw new Error(message);
  }

  return payload;
}

export function getHealth() {
  return request("/api/v1/health");
}

export function getAuthSession() {
  return request("/api/v1/auth/session");
}

export function login(password) {
  return request("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ password })
  });
}

export function logout() {
  return request("/api/v1/auth/logout", { method: "POST" });
}

export function getSettings() {
  return request("/api/v1/settings");
}

export function getQueue() {
  return request("/api/v1/queue");
}

export function getRuns() {
  return request("/api/v1/runs");
}

export function getArtifacts() {
  return request("/api/v1/artifacts");
}

export function startDryRun(queueItemId) {
  return request("/api/v1/runs/dry-run", {
    method: "POST",
    body: JSON.stringify({ queueItemId })
  });
}

export function startPublish(queueItemId, confirm = false) {
  return request("/api/v1/runs/publish", {
    method: "POST",
    body: JSON.stringify({ queueItemId, confirm })
  });
}

export function approveQueueItem(queueItemId) {
  return request(`/api/v1/queue/${queueItemId}/approve`, {
    method: "POST"
  });
}

export function skipQueueItem(queueItemId) {
  return request(`/api/v1/queue/${queueItemId}/skip`, {
    method: "POST"
  });
}

export function rejectQueueItem(queueItemId) {
  return request(`/api/v1/queue/${queueItemId}/reject`, {
    method: "POST"
  });
}

export function getAgentCapabilities() {
  return request("/api/v1/agent/capabilities");
}

export function proposeAgentPost(text, sourcePrompt = "") {
  return request("/api/v1/agent/proposals", {
    method: "POST",
    body: JSON.stringify({ text, sourcePrompt })
  });
}

export function createAgentDraft(text, sourcePrompt = "", reviewRequired = true) {
  return request("/api/v1/agent/drafts", {
    method: "POST",
    body: JSON.stringify({ text, sourcePrompt, reviewRequired })
  });
}

export function startAgentDryRun(queueItemId) {
  return request("/api/v1/agent/runs/dry-run", {
    method: "POST",
    body: JSON.stringify({ queueItemId })
  });
}

export function requestAgentPublish(queueItemId, confirm = false, approvalNote = "") {
  return request("/api/v1/agent/runs/publish-request", {
    method: "POST",
    body: JSON.stringify({ queueItemId, confirm, approvalNote })
  });
}

export { API_BASE_URL };

export function createConversation(title = "Новый AI-диалог") {
  return request("/api/v1/conversations", {
    method: "POST",
    body: JSON.stringify({ title })
  });
}

export function getConversation(conversationId) {
  return request(`/api/v1/conversations/${conversationId}`);
}

export function getConversations(limit = 50, offset = 0) {
  return request(`/api/v1/conversations?limit=${limit}&offset=${offset}`);
}

export function getConversationBySessionNumber(sessionNumber) {
  return request(`/api/v1/conversations/sessions/${sessionNumber}`);
}

export function deleteConversation(conversationId) {
  return request(`/api/v1/conversations/${conversationId}`, { method: "DELETE" });
}

export function sendChatMessage(conversationId, content) {
  return request(`/api/v1/conversations/${conversationId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content })
  });
}

export function getPipelineRun(runId) {
  return request(`/api/v1/pipeline-runs/${runId}`);
}

export function retryPipelineRun(runId) {
  return request(`/api/v1/pipeline-runs/${runId}/retry`, { method: "POST" });
}

export function createPipelineDraft(runId, candidateId) {
  return request(`/api/v1/pipeline-runs/${runId}/create-draft`, {
    method: "POST",
    body: JSON.stringify({ candidateId })
  });
}
