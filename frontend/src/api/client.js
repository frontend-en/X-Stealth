const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

async function request(path, options = {}) {
  const headers = {
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(options.headers || {})
  };

  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers,
    ...options
  });

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    const apiError = payload?.detail?.error || payload?.error;
    const message = apiError?.message || response.statusText || "Запрос не выполнен";
    throw new Error(message);
  }

  return payload;
}

export function getHealth() {
  return request("/api/v1/health");
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
