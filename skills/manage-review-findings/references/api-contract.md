# Review Hub API Contract

The default base URL is `http://127.0.0.1:8080`.

## Reconciliation payload

Send JSON with these top-level fields:

| Field | Type | Requirement |
| --- | --- | --- |
| `repository` | string | Stable repository name |
| `base_branch` | string | Compared base branch |
| `target_branch` | string | Reviewed branch |
| `commit_sha` | string | Reviewed commit |
| `reviewed_file_count` | integer | Non-negative |
| `review_source` | string | Normally `Codex` |
| `review_guideline_id` | string | Active guideline display ID, such as `RVG-000001` |
| `detected_at` | ISO 8601 datetime | Include timezone |
| `findings` | array | May be empty |

Each finding requires `title`, `description`, `remediation`, `severity`,
`category`, `rule_id`, `file_path`, `symbol`, `code_context`, and
`ai_confidence`. `line_number` and `code_language` are optional. When present,
`line_number` is only the location at detection time; do not use it to identify
the finding.

`severity` is one of `Critical`, `High`, `Medium`, or `Low`.
`ai_confidence` is an integer from 0 through 100. Use repository-relative,
normalized paths. Markdown, including fenced code blocks, is accepted in
`description` and `remediation`.

```json
{
  "repository": "example/repository",
  "base_branch": "main",
  "target_branch": "feature/example",
  "commit_sha": "0123456789abcdef",
  "reviewed_file_count": 1,
  "review_source": "Codex",
  "review_guideline_id": "RVG-000001",
  "detected_at": "2026-07-25T12:00:00+09:00",
  "findings": [
    {
      "title": "Null dereference can occur",
      "description": "The lookup result is used without checking for null.",
      "remediation": "Handle the missing value before accessing `name`.",
      "severity": "High",
      "category": "Correctness",
      "rule_id": "CORRECTNESS-NULL-001",
      "file_path": "src/example.py",
      "symbol": "Example.run",
      "line_number": 42,
      "code_context": "value = lookup(key)\nreturn value.name",
      "code_language": "python",
      "ai_confidence": 90
    }
  ]
}
```

## Requests

Retrieve the guideline before reviewing. A `200` response with `is_active: true`
is required; otherwise do not review or register findings.

```bash
curl --fail --silent \
  http://127.0.0.1:8080/api/v1/review-guidelines/RVG-000001
```

Check readiness:

```bash
curl --fail --silent http://127.0.0.1:8080/readyz
```

Preview without changing the database:

```bash
curl --fail-with-body \
  -H 'Content-Type: application/json' \
  --data-binary @review-findings.json \
  http://127.0.0.1:8080/api/v1/reconciliations/dry-run
```

Apply the exact same file:

```bash
curl --fail-with-body \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: example/repository:0123456789abcdef:Codex' \
  --data-binary @review-findings.json \
  http://127.0.0.1:8080/api/v1/reconciliations
```

Dry-run actions are `would_create`, `would_update`, `would_reopen`,
`suppressed_human`, `skipped`, and `error`. Apply actions are `created`,
`updated`, `reopened`, `suppressed_human`, `skipped`, and `error`. An apply
response has overall status `ok` or `partial_error`. A retried idempotency key
returns the saved result.
