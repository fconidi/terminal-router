import importlib.util
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "build/usr/share/terminal-router/observer.py"
spec = importlib.util.spec_from_file_location("observer", MODULE)
observer = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(observer)


class ObserverTests(unittest.TestCase):
    def test_language_defaults_to_english_and_follows_locale(self):
        with patch.dict(os.environ, {"LC_ALL": "C", "LANG": "it_IT.UTF-8"}, clear=True):
            self.assertEqual(observer.language_from_environment(), "en")
        with patch.dict(os.environ, {"LANG": "fr_FR.UTF-8"}, clear=True):
            self.assertEqual(observer.language_from_environment(), "fr")

    def test_explicit_language_override_wins_over_system_locale(self):
        with patch.dict(os.environ, {"TR_LANGUAGE": "de", "LANG": "en_US.UTF-8"}, clear=True):
            self.assertEqual(observer.language_from_environment(), "de")

    def test_supported_languages_localize_observer_messages_and_prompt(self):
        for language, marker, prompt_marker in (
                ("en", "Automatic analysis", "English"),
                ("it", "Analisi automatica", "Italian"),
                ("fr", "Analyse automatique", "French"),
                ("de", "Automatische Analyse", "German"),
                ("es", "Análisis automático", "Spanish")):
            with self.subTest(language=language):
                self.assertIn(marker, observer.localized(language, "intro"))
                self.assertIn(prompt_marker, observer.instructions_for(language))
                self.assertTrue(observer.localized(language, "config_enabled"))

    def test_configuration_prompt_requests_structured_proposals_behind_confirmation(self):
        instructions = observer.instructions_for("en", configuration=True)
        self.assertIn("TERMINAL_ROUTER_COMMAND:", instructions)
        self.assertIn("must never send", instructions)
        self.assertIn("explicitly asks", instructions)

    def test_structured_ai_command_is_extracted_but_still_validated_as_untrusted(self):
        reply, commands = observer.extract_proposed_commands(
            "Enter privileged mode.\nTERMINAL_ROUTER_COMMAND: enable")
        self.assertEqual(reply, "Enter privileged mode.")
        self.assertEqual(commands, ["enable"])
        self.assertEqual(observer.validate_router_commands(commands), (["enable"], None))

        reply, commands = observer.extract_proposed_commands(
            "Unsafe proposal.\nTERMINAL_ROUTER_COMMAND: reload; y")
        self.assertEqual(commands, ["reload; y"])
        self.assertIsNotNone(observer.validate_router_commands(commands)[1])

        reply, commands = observer.extract_proposed_commands(
            "Inspect the router.\nTERMINAL_ROUTER_COMMAND: show version\n"
            "TERMINAL_ROUTER_COMMAND: show ip interface brief")
        self.assertEqual(reply, "Inspect the router.")
        self.assertEqual(commands, ["show version", "show ip interface brief"])
        self.assertIsNotNone(observer.validate_router_commands(["show clock"] * 33)[1])

    def test_pending_command_group_pauses_new_ai_requests_for_two_minutes(self):
        self.assertEqual(observer.COMMAND_CONFIRMATION_SECONDS, 120)
        self.assertFalse(observer.should_start_request(
            {"commands": ["show version"]}, ["queued question"], True, True, True, "output"))
        self.assertTrue(observer.should_start_request(
            None, ["queued question"], False, True, False, ""))

    def test_router_command_guard_rejects_shell_injection_and_control_input(self):
        self.assertEqual(observer.validate_router_command("interface Gi0/1"), ("interface Gi0/1", None))
        for command in ("", "show run | include hostname", "reload; y", "show run\nreload", "echo $HOME"):
            with self.subTest(command=command):
                value, error = observer.validate_router_command(command)
                self.assertIsNone(value)
                self.assertTrue(error)

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

    def test_snapshot_keeps_long_command_output_and_strips_terminal_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            logs = Path(directory)
            state = logs / "workspace-test"
            state.mkdir()
            log = logs / "tmux-test.log"
            log.write_text("COMMAND_START\n" + "configuration line\n" * 600
                           + "\x1b[31mLINK DOWN\x1b[0m\x1b]52;c;secret\x07\n")
            (state / "current").symlink_to(log)
            key, text = observer.read_snapshot(state)
            self.assertIsNotNone(key)
            self.assertIn("COMMAND_START", text)
            self.assertGreater(len(text.splitlines()), 80)
            self.assertIn("LINK DOWN", text)
            self.assertNotIn("\x1b", text)
            self.assertNotIn("secret", text)

    def test_snapshot_remains_bounded_for_very_large_output(self):
        with tempfile.TemporaryDirectory() as directory:
            logs = Path(directory)
            state = logs / "workspace-test"
            state.mkdir()
            log = logs / "tmux-test.log"
            log.write_text("discarded old output\n" * 10000 + "LATEST_OUTPUT\n")
            (state / "current").symlink_to(log)
            key, text = observer.read_snapshot(state)
            self.assertIsNotNone(key)
            self.assertLessEqual(len(text.encode()), observer.MAX_SNAPSHOT_BYTES)
            self.assertIn("LATEST_OUTPUT", text)

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
