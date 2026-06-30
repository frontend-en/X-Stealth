import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import {
  AlertTriangle,
  Archive,
  BarChart3,
  CalendarClock,
  Check,
  CheckCircle2,
  Clock3,
  FileText,
  Gauge,
  Layers3,
  Play,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  TerminalSquare,
  XCircle
} from "lucide-react";
import {
  approveQueueItem,
  getArtifacts,
  getQueue,
  getRuns,
  getSettings,
  getHealth,
  rejectQueueItem,
  skipQueueItem,
  startDryRun,
  startPublish
} from "./api/client";
import "./styles.css";

const statusLabels = {
  queued: "В очереди",
  draft: "Черновик",
  blocked: "Заблокировано",
  posted: "Опубликовано",
  failed: "Ошибка",
  dry_run_completed: "Пробный запуск успешен",
  running: "Выполняется",
  completed: "Завершено",
  cancelled: "Отменено"
};

Object.assign(statusLabels, {
  dry_run_passed: "Dry-run passed",
  approved: "Approved",
  skipped: "Skipped",
  rejected: "Rejected"
});

const modeLabels = {
  dry_run: "Пробный запуск",
  publish: "Публикация"
};

const riskLabels = {
  low: "низкий",
  medium: "средний",
  high: "высокий"
};

const pillarLabels = {
  cases: "Cases",
  errors: "Errors",
  breakdowns: "Breakdowns",
  mini_guides: "Mini guides",
  personal_experience: "Personal"
};

const ctaLabels = {
  checklist: "Checklist",
  audit: "Audit",
  consultation: "Consult",
  template: "Template",
  case_study: "Case study",
  newsletter: "Newsletter",
  none: "None"
};

const artifactTypeLabels = {
  log: "лог",
  screenshot: "скриншот",
  trace: "трейс"
};

const knownRunMessages = {
  "Dry run completed. Publishing was skipped.": "Пробный запуск завершен. Публикация пропущена.",
  "Queue item was not found.": "Пост в очереди не найден.",
  "Publish run queued.": "Запуск публикации поставлен в очередь.",
  "Publish run started.": "Публикация началась.",
  "Publish run completed.": "Публикация завершена."
};

const queueColors = {
  queued: "#2563eb",
  blocked: "#dc2626",
  posted: "#16a34a",
  failed: "#dc2626",
  dry_run_completed: "#0f766e",
  draft: "#f59e0b"
};

Object.assign(queueColors, {
  dry_run_passed: "#0f766e",
  approved: "#16a34a",
  skipped: "#64748b",
  rejected: "#dc2626"
});

function formatNumber(value) {
  return new Intl.NumberFormat("ru-RU").format(value);
}

function translateRunMessage(message) {
  return knownRunMessages[message] || message || "Без сообщения";
}

function statusTone(status) {
  if (status === "posted" || status === "completed" || status === "dry_run_completed") return "success";
  if (status === "approved" || status === "dry_run_passed") return "success";
  if (status === "queued" || status === "running") return "info";
  if (status === "blocked" || status === "failed" || status === "rejected") return "warning";
  return "draft";
}

function StatusBadge({ status }) {
  return <span className={`badge ${statusTone(status)}`}>{statusLabels[status] || status}</span>;
}

function MetricCard({ icon: Icon, label, value, trend, tone }) {
  return (
    <section className="metric-card">
      <div className={`metric-icon ${tone}`}>
        <Icon size={20} aria-hidden="true" />
      </div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
        <span>{trend}</span>
      </div>
    </section>
  );
}

function buildQueueMix(items) {
  const counts = items.reduce((acc, item) => {
    acc[item.status] = (acc[item.status] || 0) + 1;
    return acc;
  }, {});

  return Object.entries(counts).map(([name, value]) => ({
    name: statusLabels[name] || name,
    value,
    color: queueColors[name] || "#64748b"
  }));
}

function buildRunChart(runs) {
  const counts = runs.reduce((acc, run) => {
    acc[run.status] = (acc[run.status] || 0) + 1;
    return acc;
  }, {});

  return Object.entries(counts).map(([status, count]) => ({
    status: statusLabels[status] || status,
    count
  }));
}

function App() {
  const [settings, setSettings] = useState(null);
  const [queue, setQueue] = useState([]);
  const [runs, setRuns] = useState([]);
  const [artifacts, setArtifacts] = useState([]);
  const [health, setHealth] = useState(null);
  const [query, setQuery] = useState("");
  const [pillarFilter, setPillarFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [runningAction, setRunningAction] = useState("");

  const refresh = useCallback(async () => {
    setError("");
    const [healthData, settingsData, queueData, runsData, artifactsData] = await Promise.all([
      getHealth(),
      getSettings(),
      getQueue(),
      getRuns(),
      getArtifacts()
    ]);

    setHealth(healthData);
    setSettings(settingsData);
    setQueue(queueData.items || []);
    setRuns(runsData.items || []);
    setArtifacts(artifactsData.items || []);
  }, []);

  useEffect(() => {
    refresh()
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [refresh]);

  const filteredQueue = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return queue.filter((item) => {
      const matchesPillar = pillarFilter === "all" || item.pillar === pillarFilter;
      const matchesQuery = !normalized || item.text.toLowerCase().includes(normalized) || item.id.includes(normalized);
      return matchesPillar && matchesQuery;
    });
  }, [queue, query, pillarFilter]);

  const queueMix = useMemo(() => buildQueueMix(queue), [queue]);
  const runChart = useMemo(() => buildRunChart(runs), [runs]);
  const blockedCount = queue.filter((item) => item.status === "blocked").length;
  const approvedCount = queue.filter((item) => item.status === "approved").length;
  const latestRun = runs[0];

  async function handleDryRun(itemId) {
    setRunningAction(`dry-${itemId}`);
    setError("");
    try {
      await startDryRun(itemId);
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setRunningAction("");
    }
  }

  async function handleQueueAction(itemId, action) {
    setRunningAction(`${action}-${itemId}`);
    setError("");
    const calls = {
      approve: approveQueueItem,
      skip: skipQueueItem,
      reject: rejectQueueItem
    };
    try {
      await calls[action](itemId);
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setRunningAction("");
    }
  }

  async function handlePublish(itemId) {
    setRunningAction(`publish-${itemId}`);
    setError("");
    try {
      await startPublish(itemId, true);
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setRunningAction("");
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Навигация панели">
        <div className="brand">
          <div className="brand-mark">
            <ShieldCheck size={24} aria-hidden="true" />
          </div>
          <div>
            <strong>X Stealth</strong>
            <span>AutoPoster</span>
          </div>
        </div>

        <nav>
          <a className="active" href="#overview">
            <BarChart3 size={18} aria-hidden="true" />
            Обзор
          </a>
          <a href="#queue">
            <CalendarClock size={18} aria-hidden="true" />
            Очередь
          </a>
          <a href="#runs">
            <TerminalSquare size={18} aria-hidden="true" />
            Запуски
          </a>
          <a href="#artifacts">
            <Archive size={18} aria-hidden="true" />
            Артефакты
          </a>
        </nav>
      </aside>

      <section className="content" id="overview">
        <header className="topbar">
          <div>
            <p className="eyebrow">Живая панель</p>
            <h1>Очередь, пробные запуски и состояние бэкенда</h1>
          </div>
          <div className="topbar-actions">
            <label className="search-box">
              <Search size={18} aria-hidden="true" />
              <input
                type="search"
                placeholder="Поиск по очереди"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <label className="select-box">
              <select value={pillarFilter} onChange={(event) => setPillarFilter(event.target.value)}>
                <option value="all">All pillars</option>
                {Object.entries(pillarLabels).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="icon-button"
              aria-label="Обновить данные"
              onClick={() => refresh().catch((err) => setError(err.message))}
            >
              <RefreshCw size={18} aria-hidden="true" />
            </button>
          </div>
        </header>

        {error ? (
          <section className="state-banner error">
            <AlertTriangle size={18} aria-hidden="true" />
            <span>{error}</span>
          </section>
        ) : null}

        {loading ? (
          <section className="state-banner">
            <Clock3 size={18} aria-hidden="true" />
            <span>Загружаю данные backend...</span>
          </section>
        ) : null}

        <section className="metrics-grid" aria-label="Ключевые метрики">
          <MetricCard
            icon={FileText}
            label="Постов в очереди"
            value={formatNumber(queue.length)}
            trend={`${blockedCount} заблокировано валидацией`}
            tone="blue"
          />
          <MetricCard
            icon={Gauge}
            label="Пробный режим"
            value={settings?.dryRun ? "Вкл" : "Выкл"}
            trend={settings?.postingEnabled ? "Публикация включена" : "Публикация выключена"}
            tone={settings?.dryRun ? "green" : "amber"}
          />
          <MetricCard
            icon={TerminalSquare}
            label="Запуски"
            value={formatNumber(runs.length)}
            trend={latestRun ? `Последний: ${statusLabels[latestRun.status] || latestRun.status}` : "Запусков пока нет"}
            tone="amber"
          />
          <MetricCard
            icon={Archive}
            label="Артефакты"
            value={formatNumber(artifacts.length)}
            trend={health ? `API: ${health.status === "ok" ? "работает" : health.status}` : "API не загружен"}
            tone="rose"
          />
        </section>

        <section className="dashboard-grid">
          <article className="panel chart-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">История запусков</p>
                <h2>Запуски по статусам</h2>
              </div>
            </div>
            <div className="chart-box">
              {runChart.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={runChart} margin={{ top: 12, right: 16, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke="#dbe3ef" strokeDasharray="4 4" vertical={false} />
                    <XAxis dataKey="status" axisLine={false} tickLine={false} />
                    <YAxis allowDecimals={false} axisLine={false} tickLine={false} width={46} />
                    <Tooltip />
                    <Bar dataKey="count" name="Запуски" fill="#0f766e" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="empty-state">Запусков пока нет. Запустите пробный запуск из очереди.</div>
              )}
            </div>
          </article>

          <article className="panel compact-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Состав очереди</p>
                <h2>Статусы</h2>
              </div>
            </div>
            <div className="donut-wrap">
              {queueMix.length ? (
                <>
                  <ResponsiveContainer width="100%" height={210}>
                    <PieChart>
                      <Pie data={queueMix} dataKey="value" nameKey="name" innerRadius={54} outerRadius={78} paddingAngle={4}>
                        {queueMix.map((entry) => (
                          <Cell key={entry.name} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="legend-list">
                    {queueMix.map((entry) => (
                      <span key={entry.name}>
                        <i style={{ background: entry.color }} />
                        {entry.name}
                      </span>
                    ))}
                  </div>
                </>
              ) : (
                <div className="empty-state">В очереди пока нет постов.</div>
              )}
            </div>
          </article>

          <article className="panel compact-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Состояние бэкенда</p>
                <h2>Ограничители запуска</h2>
              </div>
            </div>
            <div className="settings-list">
              <span>Авторизация: <strong>{settings?.hasAuthState ? "найдена" : "не найдена"}</strong></span>
              <span>Без окна браузера: <strong>{settings?.headless ? "включено" : "выключено"}</strong></span>
              <span>Прокси: <strong>{settings?.hasProxyConfigured ? "настроен" : "не настроен"}</strong></span>
              <span>Мин. интервал: <strong>{settings?.minPostIntervalMinutes ?? "-"} мин</strong></span>
            </div>
          </article>
        </section>

        <section className="panel table-panel" id="queue">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Очередь</p>
              <h2>Посты из источника данных бэкенда</h2>
            </div>
            <div className="table-actions">
              <button type="button" className="ghost-button" onClick={() => refresh().catch((err) => setError(err.message))}>
                <RefreshCw size={16} aria-hidden="true" />
                Обновить
              </button>
            </div>
          </div>

          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Pillar</th>
                  <th>CTA</th>
                  <th>Quality</th>
                  <th>UTM</th>
                  <th>Текст</th>
                  <th>Статус</th>
                  <th>Длина</th>
                  <th>Риск</th>
                  <th>Источник</th>
                  <th>Действие</th>
                </tr>
              </thead>
              <tbody>
                {filteredQueue.map((item) => (
                  <tr key={item.id}>
                    <td>{item.id}</td>
                    <td>{pillarLabels[item.pillar] || item.pillar || "-"}</td>
                    <td>{ctaLabels[item.ctaType] || item.ctaType || "-"}</td>
                    <td>{item.qualityScore ?? "-"}</td>
                    <td>
                      {item.utmUrl ? (
                        <a className="utm-link" href={item.utmUrl} target="_blank" rel="noreferrer">Preview</a>
                      ) : (
                        "-"
                      )}
                    </td>
                    <td>
                      <div className="post-title">
                        <strong>{item.text}</strong>
                      </div>
                    </td>
                    <td>
                      <StatusBadge status={item.status} />
                    </td>
                    <td>{item.textLength}</td>
                    <td>
                      <span className={`risk ${item.risk === "low" ? "low" : "medium"}`}>
                        {item.risk === "low" ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
                        {riskLabels[item.risk] || item.risk}
                      </span>
                    </td>
                    <td>{item.source}</td>
                    <td>
                      <button
                        type="button"
                        className="row-button"
                        disabled={runningAction === `dry-${item.id}` || item.status === "rejected" || item.status === "skipped"}
                        onClick={() => handleDryRun(item.id)}
                      >
                        <Play size={15} aria-hidden="true" />
                        Dry-run
                      </button>
                      <div className="row-actions">
                        <button
                          type="button"
                          className="row-button success"
                          disabled={runningAction === `approve-${item.id}` || item.status !== "dry_run_passed"}
                          onClick={() => handleQueueAction(item.id, "approve")}
                          title="Approve after dry-run"
                        >
                          <Check size={15} aria-hidden="true" />
                        </button>
                        <button
                          type="button"
                          className="row-button"
                          disabled={runningAction === `skip-${item.id}` || item.status === "posted"}
                          onClick={() => handleQueueAction(item.id, "skip")}
                          title="Skip"
                        >
                          Skip
                        </button>
                        <button
                          type="button"
                          className="row-button warning"
                          disabled={runningAction === `reject-${item.id}` || item.status === "posted"}
                          onClick={() => handleQueueAction(item.id, "reject")}
                          title="Reject"
                        >
                          <XCircle size={15} aria-hidden="true" />
                        </button>
                        <button
                          type="button"
                          className="row-button publish"
                          disabled={runningAction === `publish-${item.id}` || item.status !== "approved" || settings?.dryRun || !settings?.postingEnabled}
                          onClick={() => handlePublish(item.id)}
                          title="Publish approved post"
                        >
                          <Send size={15} aria-hidden="true" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!filteredQueue.length ? (
                  <tr>
                    <td colSpan="7">
                      <div className="empty-state">По текущему фильтру постов нет.</div>
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>

        <section className="insights-row" id="runs">
          {runs.slice(0, 3).map((run) => (
            <article className="insight" key={run.id}>
              <Layers3 size={20} aria-hidden="true" />
              <div>
                <strong>{run.id}</strong>
                <span>
                  {modeLabels[run.mode] || run.mode} / {statusLabels[run.status] || run.status}:{" "}
                  {translateRunMessage(run.message)}
                </span>
              </div>
            </article>
          ))}
          {!runs.length ? (
            <article className="insight">
              <Layers3 size={20} aria-hidden="true" />
              <div>
                <strong>Запусков пока нет</strong>
                <span>Результаты пробного запуска появятся здесь после первого действия в очереди.</span>
              </div>
            </article>
          ) : null}
        </section>

        <section className="panel table-panel" id="artifacts">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Артефакты</p>
              <h2>Безопасный индекс runtime-артефактов</h2>
            </div>
          </div>
          <div className="artifact-list">
            {artifacts.slice(0, 8).map((artifact) => (
              <a key={artifact.id} href={`${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}${artifact.downloadUrl}`}>
                <FileText size={16} aria-hidden="true" />
                <span>{artifact.name}</span>
                <small>{artifactTypeLabels[artifact.type] || artifact.type} / {formatNumber(artifact.sizeBytes)} байт</small>
              </a>
            ))}
            {!artifacts.length ? <div className="empty-state">Артефактов пока нет.</div> : null}
          </div>
        </section>
      </section>
    </main>
  );
}

const rootElement = document.getElementById("root");
const root = globalThis.__xStealthRoot || createRoot(rootElement);
globalThis.__xStealthRoot = root;
root.render(<App />);
