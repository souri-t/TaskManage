---
name: manage-review-findings
description: Review requested source code, structure findings, preview reconciliation against a local Review Hub, and apply approved results through its REST API. Use when code review findings must be registered, updated, reopened, suppressed by human findings, or checked against prior Review Hub history.
---

# Manage Review Findings

Use Review Hub as the source of truth for review history. Codex performs the
review; Review Hub only validates, reconciles, and stores structured findings.

## Workflow

1. Read the repository instructions and the user's requested review scope and
   viewpoints. Do not invent or persist a fixed review scope.
2. Inspect the requested code and produce only actionable findings supported by
   concrete evidence. Include every required field from
   [references/api-contract.md](references/api-contract.md).
3. Check `GET http://127.0.0.1:8080/readyz`. Stop without applying when it is not
   ready.
4. Send the complete payload to
   `POST /api/v1/reconciliations/dry-run`. This call is mandatory and must occur
   immediately before apply.
5. Inspect every dry-run result. Report validation errors, skips, human
   suppressions, and duplicate candidates. Do not override a human finding.
6. If the user asked to register the results and dry-run is acceptable, send the
   identical payload to `POST /api/v1/reconciliations` with an
   `Idempotency-Key` of
   `<repository>:<commit-sha>:<review-source>`.
7. Compare the applied result with the dry-run and report created, updated,
   reopened, suppressed, skipped, and failed findings.

## Safety Rules

- Never send a write request before a successful ready check and dry-run.
- Reuse the same idempotency key for retries of the same review.
- Do not log or persist the unredacted request body. The API redacts and limits
  `code_context` after calculating its fingerprint.
- Treat `partial_error` as incomplete registration and list each failed item.
- Do not alter descriptions or remediation text of an existing automatic
  finding during rediscovery; Review Hub preserves them.
- Do not resolve semantic duplicate candidates automatically.
- Use the Review Hub API directly for all reconciliation and registration.

## Output

Lead with review findings, ordered by severity and location. Then give the
registration summary and identify human suppressions, duplicate candidates, or
partial errors. If there are no findings, still report the reviewed scope and
that no API apply was necessary.
