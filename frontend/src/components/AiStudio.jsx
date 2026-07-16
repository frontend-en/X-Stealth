import React, { useCallback, useEffect, useRef, useState } from "react";
import { Bot, CheckCircle2, Circle, ExternalLink, LoaderCircle, MessageSquare, RefreshCw, Send, Sparkles, XCircle } from "lucide-react";
import {
  API_BASE_URL,
  createConversation,
  createPipelineDraft,
  getConversation,
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

export default function AiStudio({ onDraftCreated }) {
  const [conversation, setConversation] = useState(null);
  const [run, setRun] = useState(null);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [creatingDraft, setCreatingDraft] = useState("");
  const [error, setError] = useState("");
  const sourceRef = useRef(null);

  const loadConversation = useCallback(async (id) => {
    const data = await getConversation(id);
    setConversation(data);
    if (data.runs?.length) setRun(data.runs[0]);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function initialise() {
      try {
        const created = await createConversation();
        if (!cancelled) await loadConversation(created.id);
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
  }, [loadConversation]);

  const connect = useCallback((runId) => {
    sourceRef.current?.close();
    const source = new EventSource(`${API_BASE_URL}/api/v1/pipeline-runs/${runId}/events`);
    sourceRef.current = source;
    const update = (event) => {
      const payload = JSON.parse(event.data);
      const next = payload.run || payload;
      setRun(next);
    };
    ["snapshot", "run_started", "stage_started", "stage_completed", "stage_failed", "candidate_ready", "run_completed", "run_queued"].forEach((name) => source.addEventListener(name, update));
    source.onerror = async () => {
      try {
        const next = await getPipelineRun(runId);
        setRun(next);
        if (["completed", "failed", "interrupted"].includes(next.status)) source.close();
      } catch {
        // EventSource will reconnect by itself while the API is available.
      }
    };
  }, []);

  async function submit(event) {
    event.preventDefault();
    if (!text.trim() || !conversation || sending) return;
    setSending(true);
    setError("");
    try {
      const response = await sendChatMessage(conversation.id, text);
      setText("");
      const next = await getPipelineRun(response.pipelineRunId);
      setRun(next);
      await loadConversation(conversation.id);
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

  return (
    <section className="ai-studio" aria-label="AI Studio">
      <header className="studio-header">
        <div>
          <p className="eyebrow">AI Studio</p>
          <h1>Контент-пайплайн под контролем оператора</h1>
          <p>Исследование, редактура и проверка создают черновик. Публикация всегда остаётся отдельным ручным шагом.</p>
        </div>
        <Sparkles size={28} aria-hidden="true" />
      </header>

      {error ? <div className="state-banner error"><XCircle size={18} />{error}</div> : null}

      <div className="studio-grid">
        <article className="panel studio-chat">
          <div className="panel-header"><div><p className="eyebrow">Диалог</p><h2>Задача для главного агента</h2></div><MessageSquare size={20} /></div>
          <div className="chat-history">
            {conversation?.messages?.map((message) => (
              <div className={`chat-message ${message.role}`} key={message.id}>
                <strong>{message.role === "user" ? "Вы" : "Chief Agent"}</strong>
                <p>{message.content}</p>
              </div>
            ))}
            {!conversation?.messages?.length && !loading ? <div className="empty-state">Опишите идею, аудиторию или ссылку на исследование.</div> : null}
          </div>
          <form className="chat-compose" onSubmit={submit}>
            <textarea value={text} onChange={(event) => setText(event.target.value)} maxLength={4000} placeholder="Например: подготовь пост о типичной ошибке в B2B-воронке…" />
            <button className="primary-button" type="submit" disabled={sending || loading || !text.trim()}>
              <Send size={16} /> {sending ? "Запускаю" : "Запустить pipeline"}
            </button>
          </form>
        </article>

        <aside className="panel pipeline-panel">
          <div className="panel-header"><div><p className="eyebrow">Pipeline</p><h2>Агенты и прогресс</h2></div><Bot size={20} /></div>
          <div className="pipeline-progress"><span style={{ width: `${run?.progress || 0}%` }} /></div>
          <p className="progress-label">{run ? `${run.progress}% · ${run.status}` : "Ожидание задачи"}</p>
          <div className="agent-cards">
            {(run?.stages || defaultStages).map((stage) => (
              <details className={`agent-card ${stage.status}`} key={stage.id}>
                <summary><span className="agent-number">{stageIcons[stage.id]}</span><span><strong>{stage.name}</strong><small>{stage.role}</small></span><StageStatus status={stage.status} /></summary>
                {stage.summary ? <p>{stage.summary}</p> : null}
                {stage.error ? <p className="agent-error">{stage.error}</p> : null}
                {stage.artifacts?.map((artifact, index) => artifact.url ? <a key={`${artifact.url}-${index}`} href={artifact.url} target="_blank" rel="noreferrer"><ExternalLink size={13} />{artifact.title}</a> : <p key={`${artifact.title}-${index}`}>{artifact.title}</p>)}
              </details>
            ))}
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
    </section>
  );
}
