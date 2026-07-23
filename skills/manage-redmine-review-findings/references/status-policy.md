# Redmine status policy

Use the existing ticket status to select the action below.

| Existing status | Rediscovery action |
| --- | --- |
| 新規 | Keep status; update last detection and detection count |
| 確認中 | Keep status; update last detection and detection count |
| 対応対象 | Keep status; update last detection and detection count |
| 対応中 | Keep status; update last detection and detection count |
| 修正確認中 | Keep status; update last detection and detection count |
| 修正済み | Change to 確認中; update last detection, detection count, and recurrence count |
| 対応不要 | Keep status; update last detection and detection count |
| リスク受容 | Keep status; update last detection and detection count |
| 保留 | Keep status; update last detection only |
| 重複 | Apply this table to the source ticket in the Redmine duplicate relation |
| 取下げ | Keep status; update last detection and detection count |

Never reassess `対応不要`, `リスク受容`, `保留`, or `取下げ`.

Never modify a ticket whose review source is `有識者`. Return its issue number as a suppressed finding.

Use an exact Fingerprint match for automatic identity. If only Rule ID + File Path + Symbol match, record those issues as duplicate candidates. If any candidate is a human review, suppress the Codex finding without creating a ticket.
