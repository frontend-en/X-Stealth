import React, { useEffect, useState } from "react";
import { AlertTriangle, ArrowUpRight, CalendarDays, CircleAlert, RadioTower, RefreshCw, Sparkles } from "lucide-react";
import { getLatestTrendReport, getTrendReports, runTrendRadar } from "../api/client";

function reportDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "long", year: "numeric" }).format(new Date(`${value}T12:00:00`));
}

function confidenceLabel(value) {
  return { high: "Высокая", medium: "Средняя", low: "Низкая" }[value] || "Низкая";
}

function sourceLabel(platform) {
  return { reddit: "Reddit", x: "X", web: "Веб" }[platform] || "Источник";
}

export default function TrendRadar() {
  const [latest, setLatest] = useState(null);
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const [current, history] = await Promise.all([getLatestTrendReport(), getTrendReports()]);
      setLatest(current);
      setReports(history.items || []);
    } catch (err) {
      setError(err.message || "Не удалось загрузить Радар трендов.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); }, []);

  async function runNow(focusQuery = "") {
    setRunning(true);
    setError("");
    try {
      const report = await runTrendRadar(focusQuery);
      setLatest(report);
      const history = await getTrendReports();
      setReports(history.items || []);
    } catch (err) {
      setError(err.message || "Не удалось запустить Радар трендов.");
    } finally {
      setRunning(false);
    }
  }

  function submitQuery(event) {
    event.preventDefault();
    runNow(query);
  }

  return (
    <section className="trend-radar-page" aria-label="Радар AI-возможностей">
      <header className="trend-radar-header">
        <div>
          <p className="eyebrow">Ежедневная разведка · 09:00 МСК</p>
          <h1>Радар AI-возможностей</h1>
          <p>Ищем подтверждённые модели заработка с ИИ для России и СНГ: кто платит, что предложить и как проверить спрос без рискованных обещаний.</p>
        </div>
        <div className="radar-mark" aria-hidden="true"><RadioTower size={31} /></div>
      </header>

      <div className="trend-radar-actions">
        <span><CalendarDays size={16} /> Анализ за последние 24 часа</span>
        <button type="button" className="ghost-button" onClick={() => runNow()} disabled={loading || running}><RefreshCw size={16} className={running ? "spin" : ""} /> {running ? "Радар ищет…" : "Обновить обзор"}</button>
      </div>

      <form className="trend-query" onSubmit={submitQuery}>
        <label htmlFor="trend-query-input"><span>Ваш запрос</span><small>Например: «AI‑ассистенты для риелторов» или «как автоматизировать подбор персонала»</small></label>
        <input id="trend-query-input" value={query} onChange={(event) => setQuery(event.target.value)} maxLength={600} placeholder="Какую тему или нишу проверить?" disabled={running} />
        <button type="submit" className="primary-button" disabled={loading || running || !query.trim()}>{running ? "Исследую…" : "Исследовать тему"}</button>
      </form>

      {error ? <div className="state-banner error"><AlertTriangle size={18} />{error}</div> : null}
      {loading ? <div className="state-banner">Загружаю сигналы и историю исследований…</div> : null}

      {!loading && latest ? (
        <>
          <article className={`trend-lead status-${latest.status}`}>
            <div className="trend-lead-signal"><span>Возможность дня</span><i aria-hidden="true" /><i aria-hidden="true" /><i aria-hidden="true" /></div>
            <div className="trend-lead-title">
              <p>{reportDate(latest.reportDate)}</p>
              <h2>{latest.topic || "Недостаточно подтверждённых сигналов"}</h2>
              <p>{latest.summary || "Следующий запланированный обзор соберёт публичные источники и X-сигналы."}</p>
              {latest.focusQuery ? <small className="focus-query">Запрос: {latest.focusQuery}</small> : null}
            </div>
            <div className="trend-confidence">
              <span>Уверенность</span>
              <strong>{confidenceLabel(latest.confidence)}</strong>
              <small>{latest.xSignal?.postsCount || 0} публикаций X · {latest.sources?.length || 0} источников</small>
            </div>
          </article>

          <article className="opportunity-card">
            <div className="opportunity-card-title"><p className="eyebrow">Модель монетизации</p><h2>Как проверить гипотезу</h2></div>
            <div><span>Кому</span><strong>{latest.opportunity?.audience || "Аудитория пока не подтверждена"}</strong></div>
            <div><span>Что предложить</span><strong>{latest.opportunity?.offer || "Нужны дополнительные источники"}</strong></div>
            <div><span>Как зарабатывать</span><strong>{latest.opportunity?.revenueModel || "Модель дохода пока не определена"}</strong></div>
            <div className="opportunity-steps"><span>Первый тест</span><ol>{(latest.opportunity?.validationSteps || []).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}{!latest.opportunity?.validationSteps?.length ? <li>Сначала подтвердите проблему и готовность платить у нескольких целевых клиентов.</li> : null}</ol></div>
            {latest.opportunity?.risks?.length ? <div className="opportunity-risks"><span>Риски</span><p>{latest.opportunity.risks.join(" · ")}</p></div> : null}
          </article>

          <div className="trend-insight-grid">
            <article className="trend-insight-card catalysts-card">
              <p className="eyebrow">Почему ускорился</p>
              <h2>Цепочка сигналов</h2>
              <ol>
                {(latest.precursors || []).concat(latest.whyItRose || []).slice(0, 5).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
                {!latest.precursors?.length && !latest.whyItRose?.length ? <li>Доказательств для объяснения пока недостаточно.</li> : null}
              </ol>
            </article>
            <article className="trend-insight-card mood-card">
              <p className="eyebrow">Настроение обсуждений</p>
              <h2>Не статистика населения</h2>
              <div className="mood-list">
                {(latest.moodClusters || []).map((cluster) => <div key={cluster.label}><strong>{cluster.label}</strong><span>{cluster.description}</span></div>)}
                {!latest.moodClusters?.length ? <p>Кластеры обсуждений появятся после достаточного числа источников.</p> : null}
              </div>
            </article>
          </div>

          <article className="source-ledger">
            <div><p className="eyebrow">Доказательная лента</p><h2>На чём основан вывод</h2></div>
            <div className="source-list">
              {(latest.sources || []).map((source) => <a href={source.url} target="_blank" rel="noreferrer" key={source.url}><span className={`source-platform ${source.platform}`}>{sourceLabel(source.platform)}</span><span><strong>{source.title}</strong><small>{source.summary || "Открыть первоисточник"}</small></span><ArrowUpRight size={16} /></a>)}
              {!latest.sources?.length ? <p>Источники не подтверждены.</p> : null}
            </div>
            {latest.warnings?.length ? <div className="trend-warnings"><CircleAlert size={17} />{latest.warnings.join(" ")}</div> : null}
          </article>
        </>
      ) : null}

      {!loading && !latest ? <div className="trend-empty"><Sparkles size={24} /><h2>Первая AI-возможность появится после утреннего запуска</h2><p>Радар сохранит проверяемую гипотезу заработка в этой ленте и передаст её в AI Studio как исследовательский контекст.</p></div> : null}

      <section className="trend-history">
        <div className="panel-header"><div><p className="eyebrow">Архив наблюдений</p><h2>Таблица AI-возможностей</h2></div></div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Дата</th><th>Возможность</th><th>Модель дохода</th><th>Почему выросла</th><th>Сигнал X</th><th>Уверенность</th></tr></thead>
            <tbody>
              {reports.map((report) => <tr key={report.id}><td>{reportDate(report.reportDate)}</td><td><strong>{report.topic || "Нет подтверждённой возможности"}</strong></td><td>{report.opportunity?.revenueModel || "—"}</td><td>{report.whyItRose?.[0] || report.summary || "—"}</td><td>{report.xSignal?.postsCount || 0} постов</td><td><span className={`trend-confidence-badge ${report.confidence}`}>{confidenceLabel(report.confidence)}</span></td></tr>)}
              {!reports.length ? <tr><td colSpan="6"><div className="empty-state">История будет собираться после первого запуска cron.</div></td></tr> : null}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
