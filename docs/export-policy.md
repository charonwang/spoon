# Spoon GitHub Export Policy

`spoon export-github` produces a redacted candidate directory that a human may review and commit elsewhere. It never pushes to GitHub and never exports raw workflow evidence.

This document is the export policy contract for `spoon export-github`.

## Output Shape

The command writes:

```text
<destination>/tasks/<project-alias>/<task-id>/
```

The destination must not already exist. Project aliases and task ids must be path-safe slugs.

## Allowed Files

Only these files may be included:

```text
brief.md
plan.md
review-board.md
handoff.md
index.json
snapshot-summary.json
export-report.md
```

No raw files under `.spoon/current/snapshots/` are exported.

## Blocked Content

The exporter and history-template validator must reject or remove:

- `diff.patch`
- `status.txt`
- `diff-stat.txt`
- `test-output.txt`
- `dependency-check.txt`
- `sensitive-scan.txt`
- agent transcripts or chat logs
- `session_id`, `thread_id`, `conversation_id`
- unresolved local file paths
- fenced code blocks longer than 60 lines
- path traversal in destination names

The scanner is deterministic. It does not claim to detect every secret or business-sensitive detail.

## Local Path Rewrite

Before scanning, exported Markdown is rewritten with `path_policy`.

| Source | Export |
| --- | --- |
| `file:///D:/repo/pkg/file.go#L82` inside repo | `repo://<alias>/pkg/file.go#L82` |
| bare Windows path inside repo | `repo://<alias>/<relative>#Lnn` and warning |
| outside-repo path | `<local-path>` and warning |
| UNC or user-home path | `<local-path>` and warning |

After rewrite, any remaining local path token is blocking.

Line anchors are required. Whole-file `file:///...` links without `#Lnn` remain invalid because Cursor jump behavior is less consistent.

## `snapshot-summary.json`

Only these fields are allowed:

```json
{
  "captured_at": "2026-06-25T12:00:00+08:00",
  "changed_file_count": 0,
  "test_status": "passed|failed|not_run|unknown",
  "dependency_check": "passed|failed|not_run|unknown",
  "sensitive_scan": "passed|failed|not_run|unknown",
  "raw_snapshots_exported": false
}
```

`raw_snapshots_exported` is always `false`. It is a CI safety assertion, not a feature flag.

The summary must not contain:

- file names
- diffs
- command output
- absolute repo paths
- environment variables

## Findings

`ExportFinding` uses:

```text
severity: blocking | warning
source: file or rule name
message: human-readable explanation
```

Blocking findings prevent creating the final output directory. Warnings are written to `export-report.md` and require human review before commit.

`brief.md` and `plan.md` always receive a warning that business semantics require manual review.

## History Template

`github/history-template/` provides a separate CI template for an optional `spoon-history` repository. The template must share blocklist rules with `export_policy.py` tests so export and validation do not drift.

