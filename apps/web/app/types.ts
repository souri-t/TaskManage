export type Finding = {
  id: string;
  display_id: string;
  repository: string;
  title: string;
  description_markdown: string;
  severity: "Critical" | "High" | "Medium" | "Low";
  category: string;
  rule_id: string;
  file_path: string;
  symbol: string;
  line_number: number | null;
  fingerprint: string | null;
  status: string;
  review_source: string;
  code_excerpt: string | null;
  code_language: string | null;
  first_detected_at: string;
  last_detected_at: string;
  last_detected_commit: string;
  detection_count: number;
  recurrence_count: number;
  ai_confidence: number | null;
  non_remediation_reason: string | null;
  codex_fix_requested: boolean;
  codex_fix_requested_at: string | null;
  codex_fix_request_note: string | null;
};

export type TimelineEvent = {
  id: string;
  event_type: string;
  actor_label: string;
  reason: string | null;
  resulting_values: Record<string, unknown>;
  created_at: string;
};

export type ReviewRun = {
  id: string;
  repository: string;
  target_branch: string;
  commit_sha: string;
  review_source: string;
  detected_at: string;
  reviewed_file_count: number;
  status: string;
  summary: Record<string, number | string>;
  review_guideline: {
    id: string;
    display_id: string;
    title: string;
    version: number;
  } | null;
};

export type RepositoryOption = {
  id: string;
  name: string;
  display_name: string;
  finding_count: number;
};

export type ReviewGuideline = {
  id: string;
  display_id: string;
  title: string;
  content_markdown: string;
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};
