# Codex Fix Request API

All URLs are relative to `http://127.0.0.1:8080`.

## List requested findings

```text
GET /api/v1/findings?repository=<logical-name>&status=対応対象&codex_fix_requested=true
```

The response has an `items` array. Each item includes the normal finding fields
plus `codex_fix_request_note` and `codex_fix_requested_at`.

## Start work

```text
POST /api/v1/findings/{finding_id}/codex-fix-start
```

The request has no body. It succeeds only when the finding is both `対応対象`
and requested for Codex, and transitions it to `対応中`.

## Complete work

```json
POST /api/v1/findings/{finding_id}/codex-fix-complete
{
  "summary": "src/example.py を修正。pytest tests/test_example.py: passed"
}
```

Completion clears the request flag and transitions `対応中` to `修正確認中`.
