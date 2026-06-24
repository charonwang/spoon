import unittest
from argparse import Namespace
from unittest.mock import patch

from spoon.cli import build_parser, main


class CliTests(unittest.TestCase):
    def test_known_commands_bind_callable_handler_and_main_returns_zero(self):
        parser = build_parser()
        cases = [
            (["init"], "init"),
            (["snapshot"], "snapshot"),
            (["adopt-plan", "--source", "plan.md"], "adopt-plan"),
            (["prompts"], "prompts"),
            (["board"], "board"),
            (["handoff"], "handoff"),
            (["archive", "--archive-root", "archives", "--project", "proj", "--task", "task"], "archive"),
        ]
        for argv, command in cases:
            with self.subTest(command=command):
                args = parser.parse_args(argv)
                self.assertEqual(args.command, command)
                self.assertTrue(callable(getattr(args, "handler", None)))

    def test_main_returns_handler_result_from_dispatched_namespace(self):
        fake_handler = unittest.mock.Mock(return_value=7)

        class FakeParser:
            def parse_args(self, argv):
                self.argv = argv
                return Namespace(handler=fake_handler)

        parser = FakeParser()
        with patch("spoon.cli.build_parser", return_value=parser):
            self.assertEqual(main(["init"]), 7)

        fake_handler.assert_called_once()
        self.assertEqual(parser.argv, ["init"])

    def test_missing_command_returns_error(self):
        self.assertEqual(main([]), 2)

    def test_missing_required_source_returns_error(self):
        self.assertEqual(main(["adopt-plan"]), 2)

    def test_missing_required_archive_args_returns_error(self):
        self.assertEqual(main(["archive"]), 2)

    def test_missing_required_archive_root_returns_error(self):
        self.assertEqual(main(["archive", "--project", "proj", "--task", "task"]), 2)


if __name__ == "__main__":
    unittest.main()
