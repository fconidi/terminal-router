import importlib.util
from pathlib import Path
import tempfile
import sys
import unittest

MODULE = Path(__file__).resolve().parents[1] / "build/usr/share/terminal-router/observer.py"
spec = importlib.util.spec_from_file_location("observer", MODULE)
observer = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(observer)


class ObserverTests(unittest.TestCase):
    def test_scheduler_groups_output_and_never_repeats_unchanged_data(self):
        schedule = observer.Schedule(interval=10, quiet=2, max_wait=5)
        self.assertFalse(schedule.ready("first", 0))
        self.assertFalse(schedule.ready("second", 1))
        self.assertTrue(schedule.ready("second", 3))
        schedule.sent("second", 3)
        self.assertFalse(schedule.ready("second", 100))
        self.assertFalse(schedule.ready("third", 101))
        self.assertTrue(schedule.ready("third", 103))

    def test_continuous_output_does_not_postpone_analysis_forever(self):
        schedule = observer.Schedule(interval=10, quiet=2, max_wait=5)
        for second in range(5):
            self.assertFalse(schedule.ready(str(second), second))
        self.assertTrue(schedule.ready("5", 5))
        schedule.sent("5", 5)
        self.assertFalse(schedule.ready("6", 6))
        self.assertFalse(schedule.ready("6", 14))
        self.assertTrue(schedule.ready("6", 15))

    def test_snapshot_is_bounded_and_strips_terminal_control_sequences(self):
        with tempfile.TemporaryDirectory() as directory:
            logs = Path(directory)
            state = logs / "workspace-test"
            state.mkdir()
            log = logs / "tmux-test.log"
            log.write_text("old line\n" * 10000 + "\x1b[31mLINK DOWN\x1b[0m\x1b]52;c;secret\x07\n")
            (state / "current").symlink_to(log)
            key, text = observer.read_snapshot(state)
            self.assertIsNotNone(key)
            self.assertLessEqual(len(text), 16384)
            self.assertLessEqual(len(text.splitlines()), 80)
            self.assertIn("LINK DOWN", text)
            self.assertNotIn("\x1b", text)
            self.assertNotIn("secret", text)

    def test_snapshot_rejects_a_link_outside_the_log_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "logs/workspace-test"
            state.mkdir(parents=True)
            other = root / "tmux-private.log"
            other.write_text("unrelated contents")
            (state / "current").symlink_to(other)
            self.assertEqual(observer.read_snapshot(state), (None, ""))

    def test_engine_receives_snapshot_on_stdin_and_returns_text_only(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            binary = state / "engine"
            # The model's output is literal text, not an executable command.
            binary.write_text("#!/bin/sh\ncat > received\nprintf '%s\\n' '$(touch NOT_EXECUTED)'\n")
            binary.chmod(0o755)
            job = observer.EngineJob("claude", str(binary), state, "router snapshot")
            try:
                job.process.wait(timeout=5)
                success, reply = job.result()
                self.assertTrue(success)
                self.assertIn("$(touch NOT_EXECUTED)", reply)
                self.assertEqual((state / "received").read_text(), "router snapshot")
                self.assertFalse((state / "NOT_EXECUTED").exists())
            finally:
                job.close()

    def test_failed_cli_exposes_error_and_cleanup_reaps_running_process(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            binary = state / "engine"
            binary.write_text('#!/bin/sh\necho "sign in required" >&2\nexit 7\n')
            binary.chmod(0o755)
            job = observer.EngineJob("codex", str(binary), state, "snapshot")
            try:
                job.process.wait(timeout=5)
                success, message = job.result()
                self.assertFalse(success)
                self.assertIn("sign in required", message)
            finally:
                job.close()
            binary.write_text('#!/bin/sh\nsleep 60\n')
            job = observer.EngineJob("claude", str(binary), state, "snapshot")
            job.close()
            self.assertIsNotNone(job.process.poll())


if __name__ == "__main__":
    unittest.main()
