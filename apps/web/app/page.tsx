"use client";

import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  FileCode2,
  Gauge,
  ListChecks,
  Plus,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { MarkdownView } from "./markdown-view";
import type { Finding, ReviewRun, TimelineEvent } from "./types";

type View = "dashboard" | "findings" | "runs";
type Dashboard = {
  open: number;
  critical_high: number;
  recurring: number;
  verification: number;
  by_status: Record<string, number>;
};

const statusOptions = [
  "新規",
  "確認中",
  "対応対象",
  "対応中",
  "修正確認中",
  "保留",
  "修正済み",
  "対応不要",
  "リスク受容",
  "取下げ",
];

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("ja-JP", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function SeverityBadge({ severity }: { severity: string }) {
  return <span className={`badge severity-${severity.toLowerCase()}`}>{severity}</span>;
}

function Stat({
  label,
  value,
  icon,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
}) {
  return (
    <div className="stat-card">
      <div className="stat-icon">{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

export default function Home() {
  const [view, setView] = useState<View>("findings");
  const [findings, setFindings] = useState<Finding[]>([]);
  const [selected, setSelected] = useState<Finding | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [runs, setRuns] = useState<ReviewRun[]>([]);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [manualOpen, setManualOpen] = useState(false);

  const loadFindings = useCallback(async () => {
    const params = new URLSearchParams({ per_page: "100" });
    if (search) params.set("search", search);
    if (statusFilter) params.set("status", statusFilter);
    if (severityFilter) params.set("severity", severityFilter);
    const payload = await api<{ items: Finding[] }>(
      `/api/v1/findings?${params.toString()}`,
    );
    setFindings(payload.items);
    setSelected((current) => {
      if (current) {
        return payload.items.find((item) => item.id === current.id) || payload.items[0] || null;
      }
      return payload.items[0] || null;
    });
  }, [search, statusFilter, severityFilter]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [summary, runPayload] = await Promise.all([
        api<Dashboard>("/api/v1/dashboard/summary"),
        api<{ items: ReviewRun[] }>("/api/v1/review-runs?per_page=25"),
        loadFindings(),
      ]);
      setDashboard(summary);
      setRuns(runPayload.items);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "読み込みに失敗しました");
    } finally {
      setLoading(false);
    }
  }, [loadFindings]);

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  useEffect(() => {
    if (!selected) {
      return;
    }
    api<{ items: TimelineEvent[] }>(`/api/v1/findings/${selected.id}/timeline`)
      .then((payload) => setTimeline(payload.items))
      .catch(() => setTimeline([]));
  }, [selected]);

  const transition = async (status: string) => {
    if (!selected || status === selected.status) return;
    const reason = window.prompt("変更理由を入力してください");
    if (!reason) return;
    try {
      const updated = await api<Finding>(
        `/api/v1/findings/${selected.id}/transitions`,
        { method: "POST", body: JSON.stringify({ status, reason }) },
      );
      setSelected(updated);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "状態変更に失敗しました");
    }
  };

  const markDuplicate = async (targetFindingId: string) => {
    if (!selected || !targetFindingId) return;
    const reason = window.prompt("重複と判断した理由を入力してください");
    if (!reason) return;
    try {
      await api(`/api/v1/findings/${selected.id}/duplicate`, {
        method: "POST",
        body: JSON.stringify({
          target_finding_id: targetFindingId,
          reason,
        }),
      });
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "重複元の設定に失敗しました");
    }
  };

  const title = {
    dashboard: "ダッシュボード",
    findings: "指摘一覧",
    runs: "レビュー実行",
  }[view];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">R</span>
          <span>Review Hub</span>
        </div>
        <span className="nav-caption">ワークスペース</span>
        <button className={view === "dashboard" ? "nav active" : "nav"} onClick={() => setView("dashboard")}>
          <Gauge size={17} />ダッシュボード
        </button>
        <button className={view === "findings" ? "nav active" : "nav"} onClick={() => setView("findings")}>
          <ListChecks size={17} />指摘一覧
        </button>
        <button className={view === "runs" ? "nav active" : "nav"} onClick={() => setView("runs")}>
          <RefreshCw size={17} />レビュー実行
        </button>
        <div className="sidebar-spacer" />
        <div className="local-note">
          <CircleDot size={14} />
          localhost
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <h1>{title}</h1>
            <p>Codex review findings</p>
          </div>
          <div className="top-actions">
            <button className="icon-button" onClick={() => void refresh()} aria-label="更新">
              <RefreshCw size={17} />
            </button>
            <button className="primary-button" onClick={() => setManualOpen(true)}>
              <Plus size={17} />有識者指摘
            </button>
          </div>
        </header>

        {error && <div className="error-banner">{error}</div>}
        {loading && <div className="loading-bar" />}

        {view === "dashboard" && (
          <DashboardView dashboard={dashboard} runs={runs} onOpenRuns={() => setView("runs")} />
        )}
        {view === "findings" && (
          <FindingsView
            findings={findings}
            selected={selected}
            timeline={timeline}
            search={search}
            statusFilter={statusFilter}
            severityFilter={severityFilter}
            onSearch={setSearch}
            onStatusFilter={setStatusFilter}
            onSeverityFilter={setSeverityFilter}
            onSelect={setSelected}
            onTransition={transition}
            onDuplicate={markDuplicate}
          />
        )}
        {view === "runs" && <RunsView runs={runs} />}
      </main>

      {manualOpen && (
        <ManualFindingModal
          onClose={() => setManualOpen(false)}
          onCreated={async () => {
            setManualOpen(false);
            await refresh();
            setView("findings");
          }}
        />
      )}
    </div>
  );
}

function DashboardView({
  dashboard,
  runs,
  onOpenRuns,
}: {
  dashboard: Dashboard | null;
  runs: ReviewRun[];
  onOpenRuns: () => void;
}) {
  const stats = dashboard || {
    open: 0,
    critical_high: 0,
    recurring: 0,
    verification: 0,
    by_status: {},
  };
  const max = Math.max(...Object.values(stats.by_status), 1);
  return (
    <section className="content">
      <div className="stats-grid">
        <Stat label="未対応" value={stats.open} icon={<Activity size={19} />} />
        <Stat label="Critical / High" value={stats.critical_high} icon={<AlertTriangle size={19} />} />
        <Stat label="再発" value={stats.recurring} icon={<RefreshCw size={19} />} />
        <Stat label="修正確認中" value={stats.verification} icon={<CheckCircle2 size={19} />} />
      </div>
      <div className="dashboard-grid">
        <article className="panel">
          <div className="panel-heading"><h2>状態別の指摘</h2></div>
          <div className="bar-chart">
            {Object.entries(stats.by_status).map(([status, count]) => (
              <div className="bar-row" key={status}>
                <span>{status}</span>
                <div className="bar-track"><i style={{ width: `${Math.max((count / max) * 100, 3)}%` }} /></div>
                <strong>{count}</strong>
              </div>
            ))}
            {!Object.keys(stats.by_status).length && <p className="empty">指摘はまだありません。</p>}
          </div>
        </article>
        <article className="panel">
          <div className="panel-heading">
            <h2>最近のレビュー</h2>
            <button className="text-button" onClick={onOpenRuns}>すべて見る</button>
          </div>
          <div className="recent-list">
            {runs.slice(0, 5).map((run) => (
              <div className="recent-item" key={run.id}>
                <div><strong>{run.target_branch}</strong><span>{run.repository} · {run.reviewed_file_count} files</span></div>
                <span className="badge">{run.status}</span>
              </div>
            ))}
            {!runs.length && <p className="empty">レビュー実行はまだありません。</p>}
          </div>
        </article>
      </div>
    </section>
  );
}

function FindingsView({
  findings,
  selected,
  timeline,
  search,
  statusFilter,
  severityFilter,
  onSearch,
  onStatusFilter,
  onSeverityFilter,
  onSelect,
  onTransition,
  onDuplicate,
}: {
  findings: Finding[];
  selected: Finding | null;
  timeline: TimelineEvent[];
  search: string;
  statusFilter: string;
  severityFilter: string;
  onSearch: (value: string) => void;
  onStatusFilter: (value: string) => void;
  onSeverityFilter: (value: string) => void;
  onSelect: (finding: Finding) => void;
  onTransition: (status: string) => Promise<void>;
  onDuplicate: (targetFindingId: string) => Promise<void>;
}) {
  return (
    <section className="content findings-content">
      <div className="filters">
        <label className="search-field">
          <Search size={16} />
          <input value={search} onChange={(event) => onSearch(event.target.value)} placeholder="タイトル、ファイル、Rule ID" />
        </label>
        <select value={statusFilter} onChange={(event) => onStatusFilter(event.target.value)}>
          <option value="">すべての状態</option>
          {statusOptions.map((status) => <option key={status}>{status}</option>)}
        </select>
        <select value={severityFilter} onChange={(event) => onSeverityFilter(event.target.value)}>
          <option value="">すべての重要度</option>
          {["Critical", "High", "Medium", "Low"].map((severity) => <option key={severity}>{severity}</option>)}
        </select>
      </div>

      <div className="findings-grid">
        <div className="finding-list">
          <div className="list-head"><span>{findings.length}件</span><span>最終検出順</span></div>
          {findings.map((finding) => (
            <button
              key={finding.id}
              className={selected?.id === finding.id ? "finding-row selected" : "finding-row"}
              onClick={() => onSelect(finding)}
            >
              <div className="finding-main">
                <span className="finding-id">{finding.display_id}</span>
                <strong>{finding.title}</strong>
                <span className="file-path"><FileCode2 size={13} />{finding.file_path}:{finding.line_number}</span>
              </div>
              <div className="finding-aside">
                <span className="badge">{finding.status}</span>
                <SeverityBadge severity={finding.severity} />
                <ChevronRight size={15} />
              </div>
            </button>
          ))}
          {!findings.length && <p className="empty">条件に一致する指摘はありません。</p>}
        </div>

        <FindingDetailView
          key={selected?.id || "empty"}
          finding={selected}
          findings={findings}
          timeline={timeline}
          onTransition={onTransition}
          onDuplicate={onDuplicate}
        />
      </div>
    </section>
  );
}

function FindingDetailView({
  finding,
  findings,
  timeline,
  onTransition,
  onDuplicate,
}: {
  finding: Finding | null;
  findings: Finding[];
  timeline: TimelineEvent[];
  onTransition: (status: string) => Promise<void>;
  onDuplicate: (targetFindingId: string) => Promise<void>;
}) {
  const [showMarkdown, setShowMarkdown] = useState(false);
  const [duplicateTarget, setDuplicateTarget] = useState("");
  if (!finding) return <article className="detail-panel empty-detail">指摘を選択してください。</article>;
  return (
    <article className="detail-panel">
      <div className="detail-header">
        <div>
          <span className="finding-id">{finding.display_id} · {finding.review_source}</span>
          <h2>{finding.title}</h2>
        </div>
        <SeverityBadge severity={finding.severity} />
      </div>

      <div className="metadata">
        <div><span>状態</span><select value={finding.status} onChange={(event) => void onTransition(event.target.value)}>{statusOptions.map((status) => <option key={status}>{status}</option>)}</select></div>
        <div><span>Repository</span><strong>{finding.repository}</strong></div>
        <div><span>ファイル</span><strong>{finding.file_path}:{finding.line_number}</strong></div>
        <div><span>シンボル</span><strong>{finding.symbol}</strong></div>
        <div><span>Rule</span><strong>{finding.rule_id}</strong></div>
        <div><span>検出</span><strong>{finding.detection_count}回 / 再発{finding.recurrence_count}回</strong></div>
      </div>

      {finding.status !== "重複" && (
        <div className="duplicate-control">
          <select
            aria-label="重複元"
            value={duplicateTarget}
            onChange={(event) => setDuplicateTarget(event.target.value)}
          >
            <option value="">重複元を選択</option>
            {findings
              .filter(
                (candidate) =>
                  candidate.id !== finding.id &&
                  candidate.repository === finding.repository &&
                  candidate.status !== "重複",
              )
              .map((candidate) => (
                <option key={candidate.id} value={candidate.id}>
                  {candidate.display_id} · {candidate.title}
                </option>
              ))}
          </select>
          <button
            type="button"
            className="secondary-button"
            disabled={!duplicateTarget}
            onClick={() => void onDuplicate(duplicateTarget)}
          >
            重複元に設定
          </button>
        </div>
      )}

      <div className="detail-section">
        <div className="section-title"><h3>問題</h3><button className="text-button" onClick={() => setShowMarkdown(!showMarkdown)}>{showMarkdown ? "プレビュー" : "Markdown"}</button></div>
        {showMarkdown ? <pre className="markdown-source">{finding.description_markdown}</pre> : <MarkdownView value={finding.description_markdown} />}
      </div>

      {finding.code_excerpt && (
        <div className="detail-section">
          <h3>コードコンテキスト</h3>
          <MarkdownView value={`\`\`\`${finding.code_language || "text"}\n${finding.code_excerpt}\n\`\`\``} />
        </div>
      )}

      <div className="detail-section">
        <h3>修正案</h3>
        {showMarkdown ? <pre className="markdown-source">{finding.remediation_markdown}</pre> : <MarkdownView value={finding.remediation_markdown} />}
      </div>

      <div className="detail-section">
        <h3>タイムライン</h3>
        <div className="timeline">
          {timeline.map((event) => (
            <div className="timeline-item" key={event.id}>
              <span className="timeline-dot" />
              <div><strong>{event.event_type}</strong><p>{event.reason || `${event.actor_label}による更新`}</p><time>{formatDate(event.created_at)} · {event.actor_label}</time></div>
            </div>
          ))}
        </div>
      </div>
    </article>
  );
}

function RunsView({ runs }: { runs: ReviewRun[] }) {
  return (
    <section className="content">
      <article className="panel runs-panel">
        <div className="panel-heading"><h2>API登録履歴</h2><span>{runs.length}件</span></div>
        <div className="runs-table-wrap">
          <table className="runs-table">
            <thead><tr><th>対象</th><th>Commit</th><th>生成元</th><th>ファイル</th><th>検出</th><th>結果</th></tr></thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td><strong>{run.target_branch}</strong><span>{run.repository}</span></td>
                  <td><code>{run.commit_sha.slice(0, 10)}</code></td>
                  <td>{run.review_source}</td>
                  <td>{run.reviewed_file_count}</td>
                  <td>{String(run.summary.detected || 0)}</td>
                  <td><span className="badge">{run.status}</span><time>{formatDate(run.detected_at)}</time></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!runs.length && <p className="empty">レビュー実行はまだありません。</p>}
        </div>
      </article>
    </section>
  );
}

function ManualFindingModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => Promise<void>;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    repository: "",
    title: "",
    description: "",
    remediation: "",
    severity: "Medium",
    category: "Correctness",
    rule_id: "",
    file_path: "",
    symbol: "<global>",
    line_number: 1,
    code_context: "該当コードを入力してください",
    code_language: "",
  });
  const update = (key: string, value: string | number) => setForm((current) => ({ ...current, [key]: value }));
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await api("/api/v1/findings", {
        method: "POST",
        body: JSON.stringify({ ...form, ai_confidence: null }),
      });
      await onCreated();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登録に失敗しました");
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <div className="modal-backdrop" role="presentation">
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="manual-title">
        <div className="modal-header"><div><span>有識者レビュー</span><h2 id="manual-title">指摘を登録</h2></div><button className="icon-button" onClick={onClose} aria-label="閉じる"><X size={18} /></button></div>
        <form onSubmit={submit}>
          <div className="form-grid">
            <label><span>Repository</span><input required value={form.repository} onChange={(e) => update("repository", e.target.value)} placeholder="example/repository" /></label>
            <label><span>重要度</span><select value={form.severity} onChange={(e) => update("severity", e.target.value)}>{["Critical", "High", "Medium", "Low"].map((item) => <option key={item}>{item}</option>)}</select></label>
            <label className="wide"><span>タイトル</span><input required value={form.title} onChange={(e) => update("title", e.target.value)} /></label>
            <label><span>Rule ID</span><input required value={form.rule_id} onChange={(e) => update("rule_id", e.target.value)} /></label>
            <label><span>カテゴリ</span><input required value={form.category} onChange={(e) => update("category", e.target.value)} /></label>
            <label className="wide"><span>ファイルパス</span><input required value={form.file_path} onChange={(e) => update("file_path", e.target.value)} placeholder="src/example.py" /></label>
            <label><span>シンボル</span><input required value={form.symbol} onChange={(e) => update("symbol", e.target.value)} /></label>
            <label><span>行番号</span><input type="number" min="1" required value={form.line_number} onChange={(e) => update("line_number", Number(e.target.value))} /></label>
            <label className="wide"><span>問題（Markdown）</span><textarea required rows={5} value={form.description} onChange={(e) => update("description", e.target.value)} /></label>
            <label className="wide"><span>修正案（Markdown）</span><textarea required rows={4} value={form.remediation} onChange={(e) => update("remediation", e.target.value)} /></label>
            <label className="wide"><span>コードコンテキスト</span><textarea required rows={4} value={form.code_context} onChange={(e) => update("code_context", e.target.value)} /></label>
          </div>
          {error && <div className="form-error">{error}</div>}
          <div className="modal-actions"><button type="button" className="secondary-button" onClick={onClose}>キャンセル</button><button className="primary-button" disabled={submitting}>{submitting ? "登録中…" : "登録"}</button></div>
        </form>
      </div>
    </div>
  );
}
