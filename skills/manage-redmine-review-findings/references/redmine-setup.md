# Redmine setup and data contract

## Local configuration

Copy `config/redmine.example.json` to `config/redmine.json` and edit it for the target Redmine instance.

```bash
cp config/redmine.example.json config/redmine.json
chmod 600 config/redmine.json
```

`config/redmine.json` is excluded from Git. It may contain an `api_key` property. The scripts reject an API-key file that is readable or writable by group or other users.

`REDMINE_API_KEY` remains available for CI and overrides `api_key` in the file.

Do not commit or print `config/redmine.json`.

## Configuration format

```json
{
  "redmine_url": "https://redmine.example.com",
  "api_key": "replace-with-the-local-api-key",
  "project": "review-project",
  "tracker": "コードレビュー",
  "custom_fields": {
    "rule_id": {"id": 1, "name": "ルールID"},
    "repository": {"id": 2, "name": "リポジトリ"},
    "base_branch": {"id": 3, "name": "ベースブランチ"},
    "target_branch": {"id": 4, "name": "ターゲットブランチ"},
    "commit_sha": {"id": 5, "name": "コミットSHA"},
    "file_path": {"id": 6, "name": "ファイルパス"},
    "symbol": {"id": 7, "name": "シンボル"},
    "line_number": {"id": 8, "name": "行番号"},
    "fingerprint": {"id": 9, "name": "Fingerprint"},
    "review_source": {"id": 10, "name": "レビュー生成元"},
    "first_detected_at": {"id": 11, "name": "初回検出日時"},
    "last_detected_at": {"id": 12, "name": "最終検出日時"},
    "last_detected_commit": {"id": 13, "name": "最終検出Commit"},
    "detection_count": {"id": 14, "name": "検出回数"},
    "recurrence_count": {"id": 15, "name": "再発回数"},
    "ai_confidence": {"id": 16, "name": "AI信頼度"}
  },
  "priority_map": {
    "Critical": "即時",
    "High": "高め",
    "Medium": "通常",
    "Low": "低め"
  }
}
```

IDs belong in local configuration, never in code. The setup checker verifies names when the Redmine API account can read custom-field metadata.

The default status names are:

`新規`, `確認中`, `対応対象`, `対応中`, `修正確認中`, `修正済み`, `対応不要`, `リスク受容`, `保留`, `重複`, `取下げ`.

Override them with a `status_names` object only when Redmine uses different names.

## Findings input

```json
{
  "repository": "example/repository",
  "base_branch": "main",
  "target_branch": "feature/example",
  "commit_sha": "0123456789abcdef",
  "reviewed_file_count": 2,
  "review_source": "Codex",
  "detected_at": "2026-07-24T12:00:00+09:00",
  "findings": [
    {
      "title": "Null dereference can occur",
      "description": "Explain the condition and impact.",
      "remediation": "Describe a concrete correction.",
      "severity": "High",
      "category": "Correctness",
      "rule_id": "CORRECTNESS-NULL-001",
      "file_path": "src/example.py",
      "symbol": "Example.run",
      "line_number": 42,
      "code_context": "value = lookup(key)\\nreturn value.name",
      "ai_confidence": 90
    }
  ]
}
```

All top-level fields and finding fields are required. `ai_confidence` is required for Codex reviews and may be omitted for static analysis. Use `<global>` when no symbol exists. Keep `code_context` limited to the smallest code fragment that identifies the finding.

The script writes the description and remediation into the Redmine description, generates the Fingerprint, and does not persist `code_context`.

## Required Redmine preparation

- Enable the REST API.
- Create the configured project and tracker.
- Create the statuses and allow the API user's workflow transitions.
- Create the configured issue custom fields and enable `Used as a filter` for Fingerprint, Rule ID, File Path, and Symbol.
- Create review-source options `Codex`, `有識者`, and `静的解析`.
- Grant the API user permission to view, create, edit, comment on, and relate issues.
- Configure issue priorities referenced by `priority_map`.

## Read-only prerequisite check

Run `scripts/check_redmine_setup.py` before every review reconciliation. The checker uses only GET requests and verifies:

- REST API connectivity and authentication
- Project and tracker availability
- Required statuses and their open/closed classification
- Priority names referenced by `priority_map`
- Required custom-field IDs, names, types, and project availability
- `Used as a filter` for Fingerprint, Rule ID, File Path, and Symbol
- Review-source values `Codex`, `有識者`, and `静的解析`

The checker does not create or change Redmine settings.

GET requests cannot prove permission to create or update issues or relations. Redmine may still reject a later write because of role or workflow permissions; treat that as an operation error.
