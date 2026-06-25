# spoon-history template

Copy this directory into a separate **spoon-history** repository to validate
human-approved Spoon exports before push.

## Layout

```text
spoon-history/
  tasks/
    <project-alias>/
      <task-id>/
        brief.md
        plan.md
        review-board.md
        handoff.md
        index.json
        snapshot-summary.json
        export-report.md
  scripts/
    validate_exports.py
  .github/
    workflows/validate-exports.yml
```

## Validation

The workflow installs Spoon and runs the shared validator from
`spoon.export_policy.scan_export_tree`, keeping CI rules aligned with
`spoon export-github`.

Local check from a Spoon checkout:

```powershell
python github/history-template/scripts/validate_exports.py --root tasks
```

Pass a single task directory to validate one export only:

```powershell
python github/history-template/scripts/validate_exports.py --root tasks/demo/task-id
```

## Notes

- **Required after copy:** edit `.github/workflows/validate-exports.yml` and replace `YOUR_GITHUB_USER` in the `pip install` line with the GitHub user or org that hosts your Spoon fork (for example `charonwang`).
- Raw snapshot artifacts, session ids, and unresolved local paths are blocking.
- `snapshot-summary.json` must keep `raw_snapshots_exported: false`.
