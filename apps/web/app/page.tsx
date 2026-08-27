"use client";

import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  ClipboardList,
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
import type { Finding, RepositoryOption, ReviewGuideline, ReviewRun, TimelineEvent } from "./types";

type View = "dashboard" | "findings" | "runs" | "guidelines";
type Dashboard = {
  open: number;
  critical_high: number;
  recurring: number;
  verification: number;
  by_status: Record<string, number>;
};

const statusOptions = [
  "新規",
  "対応予定",
  "対応中",
  "修正完了",
  "保留",
  "クローズ",
  "対応不要",
  "重複",
];

const transitionOptions: Record<string, string[]> = {
  "新規": ["対応予定", "対応不要", "保留"],
  "対応予定": ["対応中", "保留"],
  "対応中": ["修正完了", "保留"],
  "修正完了": ["クローズ", "対応中"],
  "保留": ["新規", "対応予定"],
  "クローズ": ["新規"],
  "対応不要": ["新規"],
  "重複": [],
};

const nonRemediationReasons = [
  "リスク受容",
  "指摘の誤り（取下げ）",
  "要件外",
  "他の修正で解消済み",
  "今回対応しない",
  "その他",
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

function formatLocation(filePath: string, lineNumber: number | null) {
  return lineNumber ? `${filePath}（検出時: ${lineNumber}行目）` : filePath;
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
  const [repositories, setRepositories] = useState<RepositoryOption[]>([]);
  const [guidelines, setGuidelines] = useState<ReviewGuideline[]>([]);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [search, setSearch] = useState("");
  const [repositoryFilter, setRepositoryFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [manualOpen, setManualOpen] = useState(false);
  const [guidelineOpen, setGuidelineOpen] = useState(false);
  const [editingGuideline, setEditingGuideline] = useState<ReviewGuideline | null>(null);

  const loadFindings = useCallback(async () => {
    const params = new URLSearchParams({ per_page: "100" });
    if (search) params.set("search", search);
    if (repositoryFilter) params.set("repository", repositoryFilter);
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
  }, [repositoryFilter, search, statusFilter, severityFilter]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [summary, runPayload, repositoryPayload, guidelinePayload] = await Promise.all([
        api<Dashboard>("/api/v1/dashboard/summary"),
        api<{ items: ReviewRun[] }>("/api/v1/review-runs?per_page=25"),
        api<{ items: RepositoryOption[] }>("/api/v1/repositories"),
        api<{ items: ReviewGuideline[] }>("/api/v1/review-guidelines?include_inactive=true"),
        loadFindings(),
      ]);
      setDashboard(summary);
      setRuns(runPayload.items);
      setRepositories(repositoryPayload.items);
      setGuidelines(guidelinePayload.items);
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

  const transition = async (status: string, nonRemediationReason?: string) => {
    if (!selected || status === selected.status) return;
    try {
      const updated = await api<Finding>(
        `/api/v1/findings/${selected.id}/transitions`,
        { method: "POST", body: JSON.stringify({ status, non_remediation_reason: nonRemediationReason }) },
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

  const requestCodexFix = async (note: string | null) => {
    if (!selected) return;
    try {
      const updated = await api<Finding>(
        `/api/v1/findings/${selected.id}/codex-fix-request`,
        { method: "POST", body: JSON.stringify({ note }) },
      );
      setSelected(updated);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Codex修正依頼に失敗しました");
    }
  };

  const cancelCodexFix = async () => {
    if (!selected) return;
    try {
      const updated = await api<Finding>(`/api/v1/findings/${selected.id}/codex-fix-request`, { method: "DELETE" });
      setSelected(updated);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Codex修正依頼の解除に失敗しました");
    }
  };

  const title = {
    dashboard: "ダッシュボード",
    findings: "指摘一覧",
    runs: "レビュー履歴",
    guidelines: "レビュー観点",
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
          <RefreshCw size={17} />レビュー履歴
        </button>
        <button className={view === "guidelines" ? "nav active" : "nav"} onClick={() => setView("guidelines")}>
          <ClipboardList size={17} />レビュー観点
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
            <button className="primary-button" onClick={() => {
              if (view === "guidelines") {
                setEditingGuideline(null);
                setGuidelineOpen(true);
              } else {
                setManualOpen(true);
              }
            }}>
              <Plus size={17} />{view === "guidelines" ? "観点を追加" : "有識者指摘"}
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
            repositories={repositories}
            selected={selected}
            timeline={timeline}
            search={search}
            repositoryFilter={repositoryFilter}
            statusFilter={statusFilter}
            severityFilter={severityFilter}
            onSearch={setSearch}
            onRepositoryFilter={setRepositoryFilter}
            onStatusFilter={setStatusFilter}
            onSeverityFilter={setSeverityFilter}
            onSelect={setSelected}
            onTransition={transition}
            onDuplicate={markDuplicate}
            onRequestCodexFix={requestCodexFix}
            onCancelCodexFix={cancelCodexFix}
          />
        )}
        {view === "runs" && <RunsView runs={runs} />}
        {view === "guidelines" && (
          <GuidelinesView guidelines={guidelines} onEdit={(guideline) => {
            setEditingGuideline(guideline);
            setGuidelineOpen(true);
          }} />
        )}
      </main>

      {manualOpen && (
        <ManualFindingModal
          repositories={repositories}
          onClose={() => setManualOpen(false)}
          onCreated={async () => {
            setManualOpen(false);
            await refresh();
            setView("findings");
          }}
        />
      )}
      {guidelineOpen && (
        <GuidelineModal
          guideline={editingGuideline}
          onClose={() => setGuidelineOpen(false)}
          onSaved={async () => {
            setGuidelineOpen(false);
            await refresh();
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
        <Stat label="修正完了" value={stats.verification} icon={<CheckCircle2 size={19} />} />
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
            {!runs.length && <p className="empty">レビュー履歴はまだありません。</p>}
          </div>
        </article>
      </div>
    </section>
  );
}

function FindingsView({
  findings,
  repositories,
  selected,
  timeline,
  search,
  repositoryFilter,
  statusFilter,
  severityFilter,
  onSearch,
  onRepositoryFilter,
  onStatusFilter,
  onSeverityFilter,
  onSelect,
  onTransition,
  onDuplicate,
  onRequestCodexFix,
  onCancelCodexFix,
}: {
  findings: Finding[];
  repositories: RepositoryOption[];
  selected: Finding | null;
  timeline: TimelineEvent[];
  search: string;
  repositoryFilter: string;
  statusFilter: string;
  severityFilter: string;
  onSearch: (value: string) => void;
  onRepositoryFilter: (value: string) => void;
  onStatusFilter: (value: string) => void;
  onSeverityFilter: (value: string) => void;
  onSelect: (finding: Finding) => void;
  onTransition: (status: string, nonRemediationReason?: string) => Promise<void>;
  onDuplicate: (targetFindingId: string) => Promise<void>;
  onRequestCodexFix: (note: string | null) => Promise<void>;
  onCancelCodexFix: () => Promise<void>;
}) {
  return (
    <section className="content findings-content">
      <div className="filters">
        <label className="search-field">
          <Search size={16} />
          <input value={search} onChange={(event) => onSearch(event.target.value)} placeholder="タイトル、ファイル、Rule ID" />
        </label>
        <select
          aria-label="リポジトリ"
          value={repositoryFilter}
          onChange={(event) => onRepositoryFilter(event.target.value)}
        >
          <option value="">すべてのリポジトリ</option>
          {repositories.map((repository) => (
            <option key={repository.id} value={repository.name}>
              {repository.display_name} ({repository.finding_count})
            </option>
          ))}
        </select>
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
                <span className="file-path"><FileCode2 size={13} />{formatLocation(finding.file_path, finding.line_number)}</span>
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
          onRequestCodexFix={onRequestCodexFix}
          onCancelCodexFix={onCancelCodexFix}
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
  onRequestCodexFix,
  onCancelCodexFix,
}: {
  finding: Finding | null;
  findings: Finding[];
  timeline: TimelineEvent[];
  onTransition: (status: string, nonRemediationReason?: string) => Promise<void>;
  onDuplicate: (targetFindingId: string) => Promise<void>;
  onRequestCodexFix: (note: string | null) => Promise<void>;
  onCancelCodexFix: () => Promise<void>;
}) {
  const [showMarkdown, setShowMarkdown] = useState(false);
  const [duplicateTarget, setDuplicateTarget] = useState("");
  const [fixNote, setFixNote] = useState("");
  const [nonRemediationReason, setNonRemediationReason] = useState("");
  const [selectingNonRemediation, setSelectingNonRemediation] = useState(false);
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
        <div><span>状態</span><select value={finding.status} onChange={(event) => {
          if (event.target.value === "対応不要") {
            setSelectingNonRemediation(true);
            return;
          }
          void onTransition(event.target.value);
        }}>{statusOptions.map((status) => <option key={status} disabled={status !== finding.status && !(transitionOptions[finding.status] || []).includes(status)}>{status}</option>)}</select></div>
        <div><span>Repository</span><strong>{finding.repository}</strong></div>
        <div><span>ファイル</span><strong>{formatLocation(finding.file_path, finding.line_number)}</strong></div>
        <div><span>シンボル</span><strong>{finding.symbol}</strong></div>
        <div><span>Rule</span><strong>{finding.rule_id}</strong></div>
        <div><span>検出</span><strong>{finding.detection_count}回 / 再発{finding.recurrence_count}回</strong></div>
      </div>

      {(selectingNonRemediation || finding.status === "対応不要") && (
        <div className="detail-section non-remediation-control">
          <h3>対応不要の理由</h3>
          {finding.status === "対応不要" ? (
            <p>{finding.non_remediation_reason || "未設定"}</p>
          ) : (
            <>
              <select value={nonRemediationReason} onChange={(event) => setNonRemediationReason(event.target.value)}>
                <option value="">選択してください</option>
                {nonRemediationReasons.map((reason) => <option key={reason}>{reason}</option>)}
              </select>
              <button type="button" disabled={!nonRemediationReason} onClick={() => {
                void onTransition("対応不要", nonRemediationReason);
                setSelectingNonRemediation(false);
              }}>対応不要にする</button>
            </>
          )}
        </div>
      )}

      {finding.status !== "重複" && findings.some(
        (candidate) => candidate.id !== finding.id && candidate.repository === finding.repository && candidate.status !== "重複",
      ) && (
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

      {finding.status === "対応予定" && (
        <div className="detail-section">
          <h3>Codexへの修正依頼</h3>
          {finding.codex_fix_requested ? (
            <>
              <p>Codexへの修正を依頼済みです。</p>
              {finding.codex_fix_request_note && <MarkdownView value={finding.codex_fix_request_note} />}
              <button type="button" className="secondary-button" onClick={() => void onCancelCodexFix()}>依頼を解除</button>
            </>
          ) : (
            <div className="codex-fix-form">
              <label><span>依頼事項（任意）</span><textarea rows={3} value={fixNote} onChange={(event) => setFixNote(event.target.value)} placeholder="空欄の場合は、指摘内容と修正案に基づいて対応します。" /></label>
              <button type="button" onClick={() => void onRequestCodexFix(fixNote || null)}>Codexに修正を依頼</button>
            </div>
          )}
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
        <div className="panel-heading"><h2>レビュー履歴</h2><span>{runs.length}件</span></div>
        <div className="runs-table-wrap">
          <table className="runs-table">
            <thead><tr><th>対象</th><th>Commit</th><th>観点</th><th>生成元</th><th>ファイル</th><th>検出</th><th>結果</th></tr></thead>
            <tbody>
              {runs.map((run) => (
              <tr key={run.id}>
              <td><strong>{run.target_branch}</strong><span>{run.repository}</span></td>
              <td><code>{run.commit_sha.slice(0, 10)}</code></td>
              <td>{run.review_guideline ? <><strong>{run.review_guideline.display_id}</strong><span>{run.review_guideline.title} v{run.review_guideline.version}</span></> : "未設定"}</td>
              <td>{run.review_source}</td>
                  <td>{run.reviewed_file_count}</td>
                  <td>{String(run.summary.detected || 0)}</td>
                  <td><span className="badge">{run.status}</span><time>{formatDate(run.detected_at)}</time></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!runs.length && <p className="empty">レビュー履歴はまだありません。</p>}
        </div>
      </article>
    </section>
  );
}

function GuidelinesView({ guidelines, onEdit }: { guidelines: ReviewGuideline[]; onEdit: (guideline: ReviewGuideline) => void }) {
  return (
    <section className="content">
      <article className="panel guidelines-panel">
        <div className="panel-heading"><div><h2>レビュー観点</h2><p>Codexへ指定するIDと、実際に使用するMarkdownの観点を管理します。</p></div><span>{guidelines.length}件</span></div>
        <div className="guideline-list">
          {guidelines.map((guideline) => (
            <button className="guideline-row" key={guideline.id} onClick={() => onEdit(guideline)}>
              <div><span className="finding-id">{guideline.display_id} · v{guideline.version}</span><strong>{guideline.title}</strong><p>{guideline.content_markdown.slice(0, 180)}</p></div>
              <span className={guideline.is_active ? "badge guideline-active" : "badge"}>{guideline.is_active ? "有効" : "無効"}</span>
            </button>
          ))}
          {!guidelines.length && <p className="empty">レビュー観点はまだありません。右上から追加してください。</p>}
        </div>
      </article>
    </section>
  );
}

function GuidelineModal({ guideline, onClose, onSaved }: { guideline: ReviewGuideline | null; onClose: () => void; onSaved: () => Promise<void> }) {
  const [title, setTitle] = useState(guideline?.title || "");
  const [content, setContent] = useState(guideline?.content_markdown || "");
  const [active, setActive] = useState(guideline?.is_active ?? true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await api(guideline ? `/api/v1/review-guidelines/${guideline.display_id}` : "/api/v1/review-guidelines", {
        method: guideline ? "PATCH" : "POST",
        body: JSON.stringify({ title, content_markdown: content, is_active: active }),
      });
      await onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存に失敗しました");
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <div className="modal-backdrop" role="presentation"><div className="modal" role="dialog" aria-modal="true" aria-labelledby="guideline-title">
      <div className="modal-header"><div><span>{guideline ? guideline.display_id : "レビュー観点"}</span><h2 id="guideline-title">{guideline ? "レビュー観点を編集" : "レビュー観点を追加"}</h2></div><button className="icon-button" onClick={onClose} aria-label="閉じる"><X size={18} /></button></div>
      <form onSubmit={submit}><div className="form-grid">
        <label className="wide"><span>名称</span><input required value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例: バックエンド標準レビュー" /></label>
        <label className="wide"><span>観点（Markdown）</span><textarea required rows={14} value={content} onChange={(event) => setContent(event.target.value)} placeholder={"## 必須観点\n\n- 認可・認証\n- 例外処理\n- 回帰リスク"} /></label>
        <label><span>状態</span><select value={active ? "active" : "inactive"} onChange={(event) => setActive(event.target.value === "active")}><option value="active">有効</option><option value="inactive">無効</option></select></label>
      </div>{error && <div className="form-error">{error}</div>}<div className="modal-actions"><button type="button" className="secondary-button" onClick={onClose}>キャンセル</button><button className="primary-button" disabled={submitting}>{submitting ? "保存中…" : "保存"}</button></div></form>
    </div></div>
  );
}

function ManualFindingModal({
  repositories,
  onClose,
  onCreated,
}: {
  repositories: RepositoryOption[];
  onClose: () => void;
  onCreated: () => Promise<void>;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [symbolOptions, setSymbolOptions] = useState<string[]>([]);
  const [form, setForm] = useState({
    repository: "",
    title: "",
    description: "",
    remediation: "",
    severity: "Medium",
    file_path: "",
    symbol: "<global>",
    code_context: "該当コードを入力してください",
    code_language: "",
  });

  useEffect(() => {
    if (!form.repository) {
      return;
    }
    const params = new URLSearchParams({ repository: form.repository });
    if (form.file_path) params.set("file_path", form.file_path);
    api<{ items: string[] }>(`/api/v1/symbols?${params.toString()}`)
      .then((payload) => setSymbolOptions(payload.items))
      .catch(() => setSymbolOptions([]));
  }, [form.file_path, form.repository]);
  const update = (key: string, value: string | number) => setForm((current) => ({ ...current, [key]: value }));
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await api("/api/v1/findings", {
        method: "POST",
        body: JSON.stringify({
          ...form, ai_confidence: null,
        }),
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
            <label><span>Repository</span><select required value={form.repository} onChange={(e) => update("repository", e.target.value)}><option value="">選択してください</option>{repositories.map((repository) => <option key={repository.id} value={repository.name}>{repository.display_name}</option>)}</select></label>
            <label><span>重要度</span><select value={form.severity} onChange={(e) => update("severity", e.target.value)}>{["Critical", "High", "Medium", "Low"].map((item) => <option key={item}>{item}</option>)}</select></label>
            <label className="wide"><span>タイトル</span><input required value={form.title} onChange={(e) => update("title", e.target.value)} /></label>
            <label className="wide"><span>ファイルパス</span><input required value={form.file_path} onChange={(e) => update("file_path", e.target.value)} placeholder="src/example.py" /></label>
            <label><span>シンボル</span><input required list="manual-symbol-options" value={form.symbol} onChange={(e) => update("symbol", e.target.value)} /><datalist id="manual-symbol-options">{form.repository && symbolOptions.map((symbol) => <option key={symbol} value={symbol} />)}</datalist></label>
            <label className="wide"><span>問題（Markdown）</span><textarea required rows={5} value={form.description} onChange={(e) => update("description", e.target.value)} /></label>
            <label className="wide"><span>コードコンテキスト</span><textarea required rows={4} value={form.code_context} onChange={(e) => update("code_context", e.target.value)} /></label>
            <label className="wide"><span>修正案（Markdown）</span><textarea required rows={4} value={form.remediation} onChange={(e) => update("remediation", e.target.value)} /></label>
          </div>
          {error && <div className="form-error">{error}</div>}
          <div className="modal-actions"><button type="button" className="secondary-button" onClick={onClose}>キャンセル</button><button className="primary-button" disabled={submitting}>{submitting ? "登録中…" : "登録"}</button></div>
        </form>
      </div>
    </div>
  );
}
