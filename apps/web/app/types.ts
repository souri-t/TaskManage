export type Finding = {
  id: string;
  display_id: string;
  repository: string;
  title: string;
  description_markdown: string;
  remediation_markdown: string;
  severity: "Critical" | "High" | "Medium" | "Low";
  category: string;
  rule_id: string;
  file_path: string;
  symbol: string;
  line_number: number;
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
};

