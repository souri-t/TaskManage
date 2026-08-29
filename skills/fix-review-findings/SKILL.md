---
name: fix-review-findings
description: Implement Codex-requested Review Hub findings for the currently open Git repository. Use when asked to handle pending Review Hub fix requests, not to review or register findings.
---

# Fix Review Findings

Handle only findings that Review Hub marks as requested for Codex in the current
Git repository. The user's prompt does not need to restate a repository,
branch, or test scope.

## Workflow

1. Confirm the current directory is a Git worktree. Read its configured
   `review-hub.repository` Git config. If absent, derive a candidate from the
   `origin` remote, compare it with `GET /api/v1/repositories`, and stop to ask
   for the logical repository name if the match is not unique. Never send a
   filesystem path to Review Hub.
2. Check `GET http://127.0.0.1:8080/readyz`, then list only requested findings
   with `GET /api/v1/findings?repository=<name>&status=対応予定&codex_fix_requested=true`.
   If none exist, say so and make no code or Hub changes.
3. For each finding, read its Markdown description, code excerpt, and
   optional `codex_fix_request_note`. Inspect the current source before acting;
   the stored excerpt may be stale. Start it with
   `POST /api/v1/findings/{id}/codex-fix-start` immediately before modifying
   code. Do not start a finding that cannot reasonably be fixed in the current
   worktree; report why and leave it requested.
4. Implement the smallest correct fix consistent with the finding and optional
   note. Run focused, relevant tests. Do not alter unrelated code or create a
   commit unless the user asks.
5. If the implementation and tests are successful, send
   `POST /api/v1/findings/{id}/codex-fix-complete` with a concise `summary`
   covering changed files and test results. This moves the finding to
   `修正完了`; never mark it `クローズ`.

Use the API contract in [references/api-contract.md](references/api-contract.md)
for request bodies. Report completed findings, remaining requested findings,
changes, and test results.

## Safety

- Treat the request flag as authorization to implement that finding, not to broaden the work beyond it.
- Work only in the currently open Git repository and its current branch.
- Do not complete a finding when tests fail or required validation cannot be run; leave it `対応中` and explain the blocker.
- Do not make write requests until `readyz` succeeds.
