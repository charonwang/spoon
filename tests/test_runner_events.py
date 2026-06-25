import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spoon.commands.init_cmd import create_current_layout
from spoon.paths import project_paths
from spoon.runner.events import EventsCorruptError, append_event, load_events


class RunnerEventsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "init"], cwd=self.repo, check=True, capture_output=True)
        create_current_layout(self.repo)
        self.paths = project_paths(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_event_uses_append_mode(self):
        append_event(self.paths, "phase_changed", {"phase": "brief"})
        original = self.paths.events.read_text(encoding="utf-8")
        with patch("spoon.runner.events.read_text") as read_text:
            append_event(self.paths, "phase_changed", {"phase": "plan_review"})
            read_text.assert_not_called()
        combined = self.paths.events.read_text(encoding="utf-8")
        self.assertTrue(combined.startswith(original))
        self.assertIn("plan_review", combined)

    def test_load_events_rejects_non_object_line(self):
        self.paths.events.write_text('{"type":"ok"}\nnull\n', encoding="utf-8")
        with self.assertRaises(EventsCorruptError):
            load_events(self.paths)


if __name__ == "__main__":
    unittest.main()
