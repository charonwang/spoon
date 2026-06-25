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
  .github/
    workflows/validate-exports.yml
    scripts/validate_exports.py
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

- Replace the pip install URL in the workflow with your Spoon repository.
- Raw snapshot artifacts, session ids, and unresolved local paths are blocking.
- `snapshot-summary.json` must keep `raw_snapshots_exported: false`.
