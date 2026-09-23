"""Integration tests: temporary HOME, fake crontab, private real tmux server."""
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "build/usr/share/terminal-router/install.sh"
FRONTEND = ROOT / "build/usr/bin/terminal-router"
TMUX = shutil.which("tmux")


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="terminal-router-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home = self.base / "home with spaces"
        self.home.mkdir()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.env = dict(os.environ, HOME=str(self.home), SHELL="/bin/bash",
                        PATH=f"{self.bin}:{os.environ['PATH']}",
                        TEST_SOCKET=str(self.base / "tmux.sock"),
                        TEST_CRON=str(self.base / "crontab"))
        self.env.pop("TMUX", None)
        self.env.pop("TMUX_PANE", None)
        self.script("crontab", 'case "$1" in\n-l) cat "$TEST_CRON" 2>/dev/null ;;\n-) cat > "$TEST_CRON" ;;\nesac\n')
        self.script("tmux", f'if [ "$1" = attach ]; then exit 0; fi\nexec {shlex.quote(TMUX)} -S "$TEST_SOCKET" -f "$HOME/.tmux.conf" "$@"\n')
        self.addCleanup(self.stop_tmux)
        self.cli = self.bin / "terminal-router"
        self.cli.write_text(FRONTEND.read_text().replace(
            'INSTALLER="/usr/share/terminal-router/install.sh"',
            f"INSTALLER={shlex.quote(str(INSTALLER))}").replace(
                'source /usr/share/terminal-router/common.sh',
                f'source {shlex.quote(str(INSTALLER.parent / "common.sh"))}'))
        self.cli.chmod(0o755)
        (self.home / ".tmux.conf").write_text(
            "set -g base-index 1\nset -g renumber-windows on\n"
            "set -g default-shell /bin/bash\n"
            "set -g default-command 'bash --noprofile --norc'\n")

    def script(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/bash\n" + body)
        path.chmod(0o755)
        return path

    def run_cmd(self, *args, check=True, input=None, env=None):
        result = subprocess.run(args, env=env or self.env, input=input,
                                text=True, capture_output=True, timeout=15)
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def stop_tmux(self):
        subprocess.run([TMUX, "-S", self.env["TEST_SOCKET"], "kill-server"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def install(self, mode="logdir-only"):
        return self.run_cmd("bash", str(INSTALLER), mode)

    def consent(self):
        path = self.home / ".config/terminal-router/consent"
        path.parent.mkdir(parents=True)
        path.write_text("accepted for test\n")

    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail("timed out waiting for observable result")

    def test_installer_failure_reaches_cli(self):
        broken = self.script("broken-installer", "exit 23\n")
        self.cli.write_text(self.cli.read_text().replace(
            shlex.quote(str(INSTALLER)), shlex.quote(str(broken))))
        self.consent()
        for command in ("install", "launch"):
            with self.subTest(command=command):
                result = self.run_cmd(str(self.cli), command, check=False)
                self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.base / "tmux.sock").exists())

    def test_launch_respects_base_index_and_logs_only_its_session(self):
        self.consent()
        original_config = (self.home / ".tmux.conf").read_bytes()
        self.run_cmd(str(self.cli), "launch")
        windows = self.run_cmd("tmux", "list-windows", "-a", "-F", "#{pane_id} #{pane_pipe}").stdout.splitlines()
        self.assertEqual(len(windows), 1, windows)
        self.assertTrue(windows[0].endswith(" 1"), windows)
        self.run_cmd("tmux", "split-window", "-d")
        panes = self.run_cmd("tmux", "list-panes", "-F", "#{pane_pipe}").stdout.splitlines()
        self.assertEqual(panes, ["1", "1"])
        self.run_cmd("tmux", "new-session", "-d", "-s", "unrelated")
        self.assertEqual(self.run_cmd("tmux", "display-message", "-p", "-t", "unrelated", "#{pane_pipe}").stdout.strip(), "0")
        self.assertEqual((self.home / ".tmux.conf").read_bytes(), original_config)
        self.assertFalse((self.home / ".bashrc").exists())

    def test_logger_creates_unique_private_files_for_fast_restarts(self):
        self.install()
        logger = self.home / ".claude-logs/pipe-logger.sh"
        for _ in range(4):
            self.run_cmd(str(logger), "router / lab", "1", "0", input="router output\n")
        logs = list(logger.parent.glob("tmux-*.log"))
        self.assertEqual(len(logs), 4)
        for log in logs:
            self.assertEqual(log.stat().st_mode & 0o777, 0o600)
            self.assertEqual(log.read_text(), "router output\n")
        self.assertEqual(logger.parent.stat().st_mode & 0o777, 0o700)
        self.assertTrue((logger.parent / "latest").resolve().is_file())

    def test_hook_treats_session_name_as_data(self):
        self.install("full")
        marker = self.base / "injected"
        name = f'router $(touch {marker})'
        self.run_cmd("tmux", "new-session", "-d", "-s", name)
        self.run_cmd("tmux", "send-keys", "-l", "echo ROUTER_OUTPUT")
        self.run_cmd("tmux", "send-keys", "Enter")
        logs = self.home / ".claude-logs"
        try:
            self.wait_for(lambda: any("ROUTER_OUTPUT" in p.read_text() for p in logs.glob("tmux-*.log")))
        except AssertionError:
            self.fail(str(list(logs.iterdir())) + "\n" +
                      self.run_cmd("tmux", "show-hooks", "-g").stdout + "\n" +
                      self.run_cmd("tmux", "capture-pane", "-p").stdout)
        self.assertFalse(marker.exists(), "session name executed as shell code")

    def test_reinstall_updates_owned_blocks_and_preserves_user_settings(self):
        rc = self.home / ".bashrc"
        rc.write_text("# user setting\n# >>> claude-terminal-log >>>\n# stale block\n# <<< claude-terminal-log <<<\n# keep this too\n")
        self.install("full")
        first = rc.read_text()
        self.assertNotIn("stale block", first)
        self.assertIn("# user setting", first)
        self.assertIn("# keep this too", first)
        self.assertTrue(Path(str(rc) + ".terminal-router.bak").exists())
        self.install("full")
        self.assertEqual(rc.read_text(), first)
        self.assertEqual(first.count("# >>> claude-terminal-log >>>"), 1)

    def test_malformed_markers_fail_without_changing_dotfiles(self):
        rc = self.home / ".bashrc"
        original = "# >>> claude-terminal-log >>>\n# user data without end marker\n"
        rc.write_text(original)
        result = self.run_cmd("bash", str(INSTALLER), "full", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(rc.read_text(), original)

    def test_reinstall_backs_up_contents_of_symlinked_shell_config(self):
        target = self.home / "managed-bashrc"
        original = "# user settings\n# >>> claude-terminal-log >>>\n# old setup\n# <<< claude-terminal-log <<<\n"
        target.write_text(original)
        rc = self.home / ".bashrc"
        rc.symlink_to(target)
        self.install("full")
        self.assertTrue(rc.is_symlink())
        self.assertEqual((self.home / ".bashrc.terminal-router.bak").read_text(), original)
        self.assertNotIn("old setup", target.read_text())

    def test_rotation_preserves_unrelated_cron_jobs_and_handles_spaces(self):
        cron = self.base / "crontab"
        unrelated = f'10 4 * * * du -sh "{self.home}/.claude-logs"\n'
        cron.write_text(unrelated)
        self.install()
        lines = cron.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        logs = self.home / ".claude-logs"
        old = logs / "tmux-old.log"
        old.write_text("old\n")
        os.utime(old, (time.time() - 40 * 86400,) * 2)
        fresh = logs / "tmux-fresh.log"
        fresh.write_text("fresh\n")
        self.run_cmd("sh", "-c", lines[1].split(maxsplit=5)[5])
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())
        self.install()
        self.assertEqual(len(cron.read_text().splitlines()), 2)
        self.run_cmd(str(self.cli), "remove", input="n\n")
        self.assertEqual(cron.read_text(), unrelated)

    def test_legacy_rotation_is_replaced_without_duplicates(self):
        cron = self.base / "crontab"
        cron.write_text(f"0 3 * * * find {self.home}/.claude-logs -maxdepth 1 -name 'tmux-*.log' -mtime +30 -delete\n")
        self.install()
        self.assertEqual(len(cron.read_text().splitlines()), 1)
        self.assertIn("# terminal-router:rotation", cron.read_text())

    def test_pause_resume_targets_calling_pane_and_requires_consent(self):
        self.consent()
        self.run_cmd(str(self.cli), "launch")
        pane = self.run_cmd("tmux", "display-message", "-p", "#{pane_id}").stdout.strip()
        self.run_cmd("tmux", "split-window")
        other = self.run_cmd("tmux", "display-message", "-p", "#{pane_id}").stdout.strip()
        env = dict(self.env, TMUX="test", TMUX_PANE=pane)
        self.run_cmd(str(self.cli), "pause", env=env)
        self.assertEqual(self.run_cmd("tmux", "display-message", "-p", "-t", pane, "#{pane_pipe}").stdout.strip(), "0")
        self.assertEqual(self.run_cmd("tmux", "display-message", "-p", "-t", other, "#{pane_pipe}").stdout.strip(), "1")
        self.run_cmd(str(self.cli), "resume", env=env)
        self.assertEqual(self.run_cmd("tmux", "display-message", "-p", "-t", pane, "#{pane_pipe}").stdout.strip(), "1")
        self.run_cmd("tmux", "send-keys", "-t", pane, "-l", "echo RESUMED_OUTPUT")
        self.run_cmd("tmux", "send-keys", "-t", pane, "Enter")
        logs = self.home / ".claude-logs"
        self.wait_for(lambda: any("RESUMED_OUTPUT" in p.read_text() for p in logs.glob("tmux-*.log")))
        self.run_cmd(str(self.cli), "pause", env=env)
        (self.home / ".config/terminal-router/consent").unlink()
        self.assertNotEqual(self.run_cmd(str(self.cli), "resume", env=env, check=False).returncode, 0)

    def test_pause_outside_tmux_has_actionable_error(self):
        result = self.run_cmd(str(self.cli), "pause", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("inside a tmux pane", result.stderr)

    def test_doctor_checks_permissions_without_mutating_them(self):
        self.assertNotEqual(self.run_cmd(str(self.cli), "doctor", check=False).returncode, 0)
        self.consent()
        self.install()
        self.run_cmd(str(self.cli), "doctor")
        logs = self.home / ".claude-logs"
        logs.chmod(0o755)
        result = self.run_cmd(str(self.cli), "doctor", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("0700", result.stdout)
        self.assertEqual(logs.stat().st_mode & 0o777, 0o755)

    def test_launch_failure_removes_only_the_session_it_created(self):
        self.consent()
        self.run_cmd("tmux", "new-session", "-d", "-s", "keep-me")
        wrapper = (self.bin / "tmux").read_text()
        (self.bin / "tmux").write_text(wrapper.replace(
            '#!/bin/bash\n', '#!/bin/bash\n[ "$1" = set-hook ] && exit 7\n'))
        result = self.run_cmd(str(self.cli), "launch", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.run_cmd("tmux", "list-sessions", "-F", "#{session_name}").stdout.strip(), "keep-me")

    def test_remove_cleans_both_shells_and_refuses_malformed_blocks(self):
        block = "# >>> claude-terminal-log >>>\n# managed\n# <<< claude-terminal-log <<<\n"
        bashrc, zshrc = self.home / ".bashrc", self.home / ".zshrc"
        bashrc.write_text("# bash settings\n" + block)
        zshrc.write_text("# zsh settings\n# >>> claude-terminal-log >>>\n")
        result = self.run_cmd(str(self.cli), "remove", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(block, bashrc.read_text())
        zshrc.write_text("# zsh settings\n" + block)
        self.run_cmd(str(self.cli), "remove")
        self.assertEqual(bashrc.read_text(), "# bash settings\n")
        self.assertEqual(zshrc.read_text(), "# zsh settings\n")

    def test_tail_switches_to_new_latest(self):
        self.install()
        logger = self.home / ".claude-logs/pipe-logger.sh"
        self.run_cmd(str(logger), "first", "1", "0", input="FIRST_LOG\n")
        output = self.base / "tail-output"
        with output.open("w") as out:
            proc = subprocess.Popen([str(self.cli), "tail"], env=self.env,
                                    stdout=out, stderr=subprocess.DEVNULL,
                                    start_new_session=True)
            try:
                self.wait_for(lambda: "FIRST_LOG" in output.read_text())
                self.run_cmd(str(logger), "second", "1", "0", input="SECOND_LOG\n")
                self.wait_for(lambda: "SECOND_LOG" in output.read_text())
            finally:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
