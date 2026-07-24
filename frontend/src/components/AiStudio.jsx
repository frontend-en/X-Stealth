import React, { useCallback, useEffect, useRef, useState } from "react";
import { Bot, CheckCircle2, Circle, ExternalLink, LoaderCircle, MessageSquare, Plus, RefreshCw, Send, Sparkles, Trash2, XCircle } from "lucide-react";
import {
  API_BASE_URL,
  createConversation,
  createPipelineDraft,
  deleteConversation,
  getConversationBySessionNumber,
  getConversations,
  getLatestTrendReport,
  getPipelineRun,
  retryPipelineRun,
  sendChatMessage
} from "../api/client";

const stageIcons = {
  trend_research: "01",
  strategy: "02",
  ghostwriter: "03",
  hook_editor: "04",
  brand_editor: "05",
  fact_policy: "06",
  chief: "07"
};

const agentProfiles = {
  trend_research: { russianName: "Аналитик трендов", tint: "#38a3c8", shade: "#d9f3fb" },
  strategy: { russianName: "Контент-стратег", tint: "#6674d9", shade: "#e6e9ff" },
  ghostwriter: { russianName: "Автор черновиков", tint: "#a36bd8", shade: "#f2e5ff" },
  hook_editor: { russianName: "Редактор первой строки", tint: "#ea8a4d", shade: "#fff0e0" },
  brand_editor: { russianName: "Редактор тона и ясности", tint: "#d55d83", shade: "#ffe6ee" },
  fact_policy: { russianName: "Проверяющий факты и правила", tint: "#2d9c78", shade: "#dff7ed" },
  chief: { russianName: "Главный редактор", tint: "#2e607f", shade: "#dcecf5" }
};

const defaultStages = [
  ["trend_research", "Trend Researcher", "Проверяет публичный контекст и источники"],
  ["strategy", "Content Strategist", "Определяет угол, аудиторию и CTA"],
  ["ghostwriter", "Ghostwriter", "Готовит три оригинальных варианта"],
  ["hook_editor", "Hook Editor", "Усиливает ясность первой строки"],
  ["brand_editor", "Brand & Clarity Editor", "Приводит текст к тону бренда"],
  ["fact_policy", "Fact & Policy Reviewer", "Проверяет факты и риски"],
  ["chief", "Chief Agent", "Собирает итог и рекомендации"]
].map(([id, name, role]) => ({ id, name, role, status: "pending" }));

function StageStatus({ status }) {
  if (status === "completed") return <CheckCircle2 size={17} aria-label="Готово" />;
  if (status === "failed") return <XCircle size={17} aria-label="Ошибка" />;
  if (status === "running") return <LoaderCircle size={17} className="spin" aria-label="Выполняется" />;
  return <Circle size={17} aria-label="Ожидание" />;
}

function formatSessionDate(value) {
  if (!value) return "";
  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function statusLabel(status) {
  return { queued: "в очереди", running: "в работе", completed: "завершена", failed: "ошибка", interrupted: "прервана" }[status] || "без запусков";
}

export default function AiStudio({ sessionNumber, onNavigateSession, onNavigateTrendRadar, onDraftCreated }) {
  const [sessions, setSessions] = useState([]);
  const [conversation, setConversation] = useState(null);
  const [run, setRun] = useState(null);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [creatingDraft, setCreatingDraft] = useState("");
  const [deletingSession, setDeletingSession] = useState("");
  const [error, setError] = useState("");
  const [trendReport, setTrendReport] = useState(null);
  const sourceRef = useRef(null);

  const refreshSessions = useCallback(async () => {
    const data = await getConversations();
    setSessions(data.items || []);
  }, []);

  const connect = useCallback((runId) => {
    sourceRef.current?.close();
    const source = new EventSource(`${API_BASE_URL}/api/v1/pipeline-runs/${runId}/events`, { withCredentials: true });
    sourceRef.current = source;
    const update = (event) => {
      const payload = JSON.parse(event.data);
      const next = payload.run || payload;
      setRun(next);
      if (["completed", "failed", "interrupted"].includes(next.status)) {
        refreshSessions().catch(() => undefined);
      }
    };
    ["snapshot", "run_started", "stage_started", "stage_completed", "stage_failed", "candidate_ready", "run_completed", "run_queued"].forEach((name) => source.addEventListener(name, update));
    source.onerror = async () => {
      try {
        const next = await getPipelineRun(runId);
        setRun(next);
        if (["completed", "failed", "interrupted"].includes(next.status)) {
          source.close();
          await refreshSessions();
        }
      } catch {
        // EventSource reconnects while the backend is available.
      }
    };
  }, [refreshSessions]);

  const loadSession = useCallback(async (number) => {
    const data = await getConversationBySessionNumber(number);
    setConversation(data);
    const latestRun = data.runs?.[0] || null;
    setRun(latestRun);
    if (latestRun && !["completed", "failed", "interrupted"].includes(latestRun.status)) connect(latestRun.id);
    return data;
  }, [connect]);

  useEffect(() => {
    let cancelled = false;
    sourceRef.current?.close();
    setLoading(true);
    setError("");
    setConversation(null);
    setRun(null);

    async function initialise() {
      try {
        await refreshSessions();
        if (sessionNumber) await loadSession(sessionNumber);
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    initialise();
    return () => {
      cancelled = true;
      sourceRef.current?.close();
    };
  }, [sessionNumber, loadSession, refreshSessions]);

  useEffect(() => {
    getLatestTrendReport().then(setTrendReport).catch(() => setTrendReport(null));
  }, []);

  async function submit(event) {
    event.preventDefault();
    if (!text.trim() || sending) return;
    setSending(true);
    setError("");
    try {
      let activeConversation = conversation;
      if (!activeConversation) {
        const created = await createConversation();
        activeConversation = { id: created.id, sessionNumber: created.sessionNumber, messages: [], runs: [] };
        setConversation(activeConversation);
        onNavigateSession?.(created.sessionNumber);
      }
      const response = await sendChatMessage(activeConversation.id, text.trim());
      setText("");
      const next = await getPipelineRun(response.pipelineRunId);
      setRun(next);
      await loadSession(activeConversation.sessionNumber);
      await refreshSessions();
      connect(response.pipelineRunId);
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  }

  async function retry() {
    if (!run) return;
    setError("");
    try {
      const next = await retryPipelineRun(run.id);
      setRun(next);
      connect(next.id);
    } catch (err) {
      setError(err.message);
    }
  }

  async function createDraft(candidateId) {
    if (!run) return;
    setCreatingDraft(candidateId);
    setError("");
    try {
      const created = await createPipelineDraft(run.id, candidateId);
      onDraftCreated?.(created.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setCreatingDraft("");
    }
  }

  function selectRun(runId) {
    const selected = conversation?.runs?.find((item) => item.id === runId);
    if (!selected) return;
    setRun(selected);
    if (!["completed", "failed", "interrupted"].includes(selected.status)) connect(selected.id);
  }

  async function removeSession(session) {
    const confirmed = window.confirm(`Удалить сессию №${session.sessionNumber}? Восстановить её будет нельзя.`);
    if (!confirmed) return;

    setDeletingSession(session.id);
    setError("");
    try {
      if (session.sessionNumber === sessionNumber) sourceRef.current?.close();
      await deleteConversation(session.id);
      await refreshSessions();
      if (session.sessionNumber === sessionNumber) {
        setConversation(null);
        setRun(null);
        onNavigateSession?.(null);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setDeletingSession("");
    }
  }

  return (
    <section className="ai-studio" aria-label="AI Studio">
      <header className="studio-header">
        <div>
          <p className="eyebrow">AI Studio</p>
          <h1>{conversation ? `Сессия №${conversation.sessionNumber}` : "Новая сессия"}</h1>
          <p>Исследование, редактура и проверка создают черновик. Публикация всегда остаётся отдельным ручным шагом.</p>
        </div>
        <Sparkles size={28} aria-hidden="true" />
      </header>

      {error ? <div className="state-banner error"><XCircle size={18} />{error}</div> : null}

      <div className="studio-workspace">
        <aside className="panel session-history" aria-label="История сессий">
          <div className="panel-header">
            <div><p className="eyebrow">История</p><h2>Сессии</h2></div>
            <button type="button" className="icon-button" aria-label="Новая сессия" title="Новая сессия" onClick={() => onNavigateSession?.(null)}><Plus size={18} /></button>
          </div>
          <button type="button" className="ghost-button session-new-button" onClick={() => onNavigateSession?.(null)}><Plus size={16} />Новая сессия</button>
          <div className="session-list">
            {sessions.map((session) => (
              <div className={`session-card ${session.sessionNumber === sessionNumber ? "active" : ""}`} key={session.sessionNumber}>
                <button type="button" className="session-card-open" onClick={() => onNavigateSession?.(session.sessionNumber)}>
                  <span>Сессия №{session.sessionNumber}</span>
                  <strong>{session.title}</strong>
                  <small>{formatSessionDate(session.updatedAt)} · {statusLabel(session.lastRunStatus)}</small>
                  {session.lastMessagePreview ? <em>{session.lastMessagePreview}</em> : null}
                </button>
                <button
                  type="button"
                  className="session-delete-button"
                  aria-label={`Удалить сессию №${session.sessionNumber}`}
                  title="Удалить сессию"
                  disabled={deletingSession === session.id}
                  onClick={() => removeSession(session)}
                ><Trash2 size={16} /></button>
              </div>
            ))}
            {!sessions.length && !loading ? <div className="empty-state">История появится после первой генерации.</div> : null}
          </div>
        </aside>

        <div className="studio-main">
          {sessionNumber && !conversation && !loading ? <div className="state-banner">Сессия №{sessionNumber} не найдена. Выберите существующую или начните новую.</div> : null}
          {trendReport?.status === "completed" ? <section className="studio-trend-context">
            <div><p className="eyebrow">Контекст Радара AI-возможностей</p><strong>{trendReport.topic}</strong><span>{trendReport.opportunity?.revenueModel || "Модель дохода уточняется"} · {trendReport.sources?.length || 0} источников</span></div>
            <button type="button" className="ghost-button" onClick={() => onNavigateTrendRadar?.()}>Открыть радар</button>
          </section> : null}
          <div className="studio-grid">
            <article className="panel studio-chat">
              <div className="panel-header"><div><p className="eyebrow">Диалог</p><h2>{conversation?.title || "Задача для главного агента"}</h2></div><MessageSquare size={20} /></div>
              <div className="chat-history">
                {conversation?.messages?.map((message) => {
                  const messageRun = message.role === "user" ? conversation.runs?.find((item) => item.messageId === message.id) : null;
                  return (
                    <div className={`chat-message ${message.role}`} key={message.id}>
                      <strong>{message.role === "user" ? "Вы" : "Chief Agent"}</strong>
                      <p>{message.content}</p>
                      {messageRun ? <button type="button" className="chat-run-link" onClick={() => selectRun(messageRun.id)}>Открыть генерацию</button> : null}
                    </div>
                  );
                })}
                {!conversation?.messages?.length && !loading ? <div className="empty-state">Опишите идею, аудиторию или ссылку на исследование. Первая отправка создаст новую сессию.</div> : null}
              </div>
              <form className="chat-compose" onSubmit={submit}>
                <textarea value={text} onChange={(event) => setText(event.target.value)} maxLength={4000} placeholder="Например: подготовь пост о типичной ошибке в B2B-воронке…" />
                <button className="primary-button" type="submit" disabled={sending || loading || !text.trim()}>
                  <Send size={16} /> {sending ? "Запускаю" : conversation ? "Запустить pipeline" : "Создать сессию и запустить"}
                </button>
              </form>
            </article>

            <aside className="panel pipeline-panel">
              <div className="panel-header"><div><p className="eyebrow">Pipeline</p><h2>Агенты и прогресс</h2></div><Bot size={20} /></div>
              {conversation?.runs?.length ? <label className="run-picker">Генерация<select value={run?.id || ""} onChange={(event) => selectRun(event.target.value)}>{conversation.runs.map((item) => <option key={item.id} value={item.id}>{formatSessionDate(item.createdAt)} · {statusLabel(item.status)}</option>)}</select></label> : null}
              <div className="pipeline-progress"><span style={{ width: `${run?.progress || 0}%` }} /></div>
              <p className="progress-label">{run ? `${run.progress}% · ${statusLabel(run.status)}` : "Ожидание задачи"}</p>
              <div className="agent-cards">
                {(run?.stages || defaultStages).map((stage) => {
                  const profile = agentProfiles[stage.id] || { russianName: "AI-агент", tint: "#64748b", shade: "#e7edf4" };
                  return (
                    <details className={`agent-card ${stage.status}`} key={stage.id}>
                      <summary>
                        <span className="agent-identity" aria-hidden="true">
                          <span className="agent-number">{stageIcons[stage.id]}</span>
                          <span className="agent-avatar" style={{ "--agent-tint": profile.tint, "--agent-shade": profile.shade }}>
                            <span className="agent-avatar-head" />
                            <span className="agent-avatar-body" />
                          </span>
                        </span>
                        <span className="agent-copy">
                          <strong>{stage.name}</strong>
                          <span className="agent-russian-name">{profile.russianName}</span>
                          <small>{stage.role}</small>
                        </span>
                        <span className="agent-status"><StageStatus status={stage.status} /></span>
                      </summary>
                    {stage.summary ? <p>{stage.summary}</p> : null}
                    {stage.error ? <p className="agent-error">{stage.error}</p> : null}
                    {stage.artifacts?.map((artifact, index) => artifact.url ? <a key={`${artifact.url}-${index}`} href={artifact.url} target="_blank" rel="noreferrer"><ExternalLink size={13} />{artifact.title}</a> : <p key={`${artifact.title}-${index}`}>{artifact.title}</p>)}
                    </details>
                  );
                })}
              </div>
              {run?.status === "failed" ? <button type="button" className="ghost-button" onClick={retry}><RefreshCw size={16} />Повторить упавший этап</button> : null}
            </aside>
          </div>

          <section className="panel candidates-panel">
            <div className="panel-header"><div><p className="eyebrow">Финальный результат</p><h2>Выберите вариант для черновика</h2></div></div>
            {run?.finalRecommendation ? <p className="chief-summary">{run.finalRecommendation}</p> : null}
            <div className="candidate-grid">
              {run?.candidates?.map((candidate, index) => (
                <article className="candidate" key={candidate.id}>
                  <span>Вариант {index + 1} · оценка {candidate.score}</span>
                  <p>{candidate.text}</p>
                  {candidate.rationale ? <small>{candidate.rationale}</small> : null}
                  {candidate.warnings?.length ? <small className="agent-error">{candidate.warnings.join(" ")}</small> : null}
                  <button className="primary-button" type="button" disabled={creatingDraft === candidate.id || run?.status !== "completed"} onClick={() => createDraft(candidate.id)}>
                    {creatingDraft === candidate.id ? "Создаю…" : "Создать черновик"}
                  </button>
                </article>
              ))}
              {!run?.candidates?.length ? <div className="empty-state">После работы Ghostwriter и Chief Agent здесь появятся варианты.</div> : null}
            </div>
          </section>
        </div>
      </div>
    </section>
  );
}
