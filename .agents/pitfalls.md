# pitfalls

## Windows paths

- File links in plans must use `file:///C:/path/to/file.go#L82` format
- ❌ Raw Windows paths like `C:\path\to\file.go:82` won't work as clickable links in Cursor Plan UI
- `path_policy.py`'s `PATH_TOKEN_RE` matches both formats, but `GOOD_FILE_URI_RE` only accepts `file:///` + line anchor

## .spoon/ JSON files

- **Never hand-edit** `run-state.json`, `actions.json`, or `events.jsonl`
- Only mutate through `spoon run`, `spoon action complete/fail`
- Corrupt `actions.json` → Runner exits 21, does not silently clear
- Missing `actions.json` → Runner rebuilds from phase + deterministic ids + event log
- Completed action recovery requires matching `action_completed` event + current output file + digest

## Subprocess

- `git_util.py`'s `run_git()`: argument list, no `shell=True`
- `snapshot_cmd.py`'s `command_report()`: uses `shell=True` because `--test-cmd` and `--dependency-cmd` are user-provided command strings (trusted input)
- Everywhere else: argument arrays, no shell string concatenation
- Windows: bare names like `codex` often resolve to `codex.cmd`; `subprocess` without a shell cannot find them. Use `adapters.command_util.resolve_executable` (via `shutil.which`) before `run`/`Popen`

## Paths and directories

- Always resolve paths via `project_paths(repo)` → `ProjectPaths`, don't hand-roll path strings
- `ProjectPaths` is a frozen dataclass; field names are the contract
- Windows is case-insensitive → `_relative_windows_path` uses casefold comparison

## Review parsing

- `review_parser.py`'s `classify_review_text` relies on `- ` prefix to recognize items; lines without `- ` end up in `Unparsed` warnings
- `[CONFLICT]`, `[BLOCKING]`, `P1`/`P2`/`P3` tags override heading-based grouping
- Empty sections render as `_None._`, not blank — gates use this to distinguish "no findings" from "not yet reviewed"

## Runner phases

- `spoon run` advances at most one phase per call; don't expect a single invocation to run the full pipeline
- After implementation completes, Runner auto-snapshots; if snapshot fails, it stalls at `needs_host`
- Don't manually run `spoon snapshot` mid-Runner-flow — let the Runner manage snapshot timing

## Timestamps and determinism

- `utc_now_iso()` is microsecond-precision on purpose. `has_fresh_snapshot` compares snapshot vs. completion times with `>`; second-level resolution makes them collide on fast machines and stalls the Runner before `code_review`. Never truncate to seconds.
- Tests must be deterministic: no dependence on wall-clock resolution, execution speed, or OS. A timing race can pass on slow Windows and fail only on a fast ubuntu CI runner.
