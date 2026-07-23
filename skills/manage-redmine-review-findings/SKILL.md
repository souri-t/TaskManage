---
name: manage-redmine-review-findings
description: Review code with Codex and reconcile structured findings with Redmine. Use when a code-review request must create, update, reopen, suppress, or report Redmine review findings while preserving human reviews and avoiding exact duplicate tickets.
---

# Manage Redmine Review Findings

## Workflow

1. Read the repository instructions and the user's review scope and viewpoints.
2. Review only the requested code and produce findings with every field required by `references/redmine-setup.md`.
3. Generate the input JSON accepted by `scripts/manage_findings.py`.
4. Run the read-only `scripts/check_redmine_setup.py` before every reconciliation. Stop if any prerequisite is missing or cannot be verified.
5. Run `scripts/manage_findings.py --dry-run` and inspect every proposed action.
6. If the request authorizes Redmine reflection and the dry run is valid, run the same command without `--dry-run`.
7. Return the summary emitted by the script together with any review findings that could not be processed.

Do not define the review scope or viewpoints inside this skill. Take them from the active request and repository instructions.

## Required behavior

- Treat Redmine as the sole source of truth for review history.
- Use the bundled scripts for Fingerprint generation, Redmine lookup, state handling, and writes.
- Consider only an exact Fingerprint match to be the same finding automatically.
- Treat Rule ID + File Path + Symbol matches as duplicate candidates.
- Never create or modify a ticket when the matching ticket or candidate is a human review.
- Reopen a rediscovered `修正済み` ticket as `確認中`.
- Preserve `対応不要`, `リスク受容`, `保留`, and `取下げ`; do not reassess their validity.
- Never print or persist the Redmine API key.
- Stop before writes when setup validation fails.
- Keep setup validation read-only. Do not create or modify Redmine administration settings.

Read `references/status-policy.md` when interpreting or changing an existing ticket.
Read `references/redmine-setup.md` when preparing Redmine or constructing configuration and input files.

## Commands

```bash
python3 scripts/check_redmine_setup.py

python3 scripts/manage_findings.py \
  --input /path/to/findings.json \
  --dry-run

python3 scripts/manage_findings.py \
  --input /path/to/findings.json
```

Resolve script paths relative to this `SKILL.md`, not relative to the reviewed repository.
By default, scripts read `config/redmine.json` relative to this `SKILL.md`. Use `--config` only to override that location.

## Failure handling

- Report configuration, authentication, and permission failures without attempting writes.
- Continue with other findings when one finding fails.
- Keep error output free of source-code context and credentials.
- If a duplicate ticket cannot resolve its source ticket, skip it and report the ticket number for human correction.
