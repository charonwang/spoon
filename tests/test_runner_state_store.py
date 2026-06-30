import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from spoon.commands.init_cmd import create_current_layout
from spoon.paths import project_paths
from spoon.runner.model import RunPhase, RunState, RunStatus
from spoon.runner.state_store import (
    load_implementation,
    load_run_state,
    save_implementation,
    save_run_state,
)


class RunnerStateStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "init"], cwd=self.repo, check=True, capture_output=True)
        create_current_layout(self.repo)
        self.paths = project_paths(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_state_returns_initial_state(self):
        state = load_run_state(self.paths)
        self.assertEqual(state.phase, RunPhase.BRIEF)
        self.assertEqual(state.status, RunStatus.READY)

    def test_save_and_load_round_trip(self):
        state = RunState.new("run-001")
        save_run_state(self.paths, state)
        self.assertEqual(load_run_state(self.paths), state)

    def test_project_paths_include_runner_files(self):
        self.assertEqual(self.paths.run_state, self.paths.current / "run-state.json")
        self.assertEqual(self.paths.actions, self.paths.current / "actions.json")
        self.assertEqual(self.paths.events, self.paths.current / "events.jsonl")
        self.assertEqual(self.paths.implementation, self.paths.current / "implementation.json")
        self.assertEqual(self.paths.implementation_base, self.paths.current / "implementation-base.txt")
        self.assertEqual(self.paths.config, self.paths.spoon / "config.json")

    def test_atomic_write_preserves_old_file_on_failure(self):
        from unittest.mock import patch

        state = RunState.new("run-001")
        save_run_state(self.paths, state)
        original = self.paths.run_state.read_text(encoding="utf-8")
        with patch("spoon.runner.state_store.write_json_atomic", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                save_run_state(self.paths, RunState.new("run-002"))
        self.assertEqual(self.paths.run_state.read_text(encoding="utf-8"), original)

    def test_implementation_round_trip(self):
        from spoon.runner.model import ImplementationRecord

        record = ImplementationRecord(
            schema_version=1,
            status="reported_complete",
            action_id="abc",
            completed_at="2026-06-19T00:00:00+00:00",
            summary_path=".spoon/current/implementation-summary.md",
            base_sha="base-sha",
        )
        save_implementation(self.paths, record)
        self.assertEqual(load_implementation(self.paths), record)
        payload = json.loads(self.paths.implementation.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
