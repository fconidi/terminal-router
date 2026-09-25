"""Integration tests: temporary HOME, fake crontab, private real tmux server."""
import os
import json
import pty
from pathlib import Path
import re
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
                        PATH=f"{self.bin}:{os.defpath}",
                        TEST_SOCKET=str(self.base / "tmux.sock"),
                        TEST_CRON=str(self.base / "crontab"))
        self.env.pop("TMUX", None)
        self.env.pop("TMUX_PANE", None)
        self.script("crontab", 'case "$1" in\n-l) cat "$TEST_CRON" 2>/dev/null ;;\n-) cat > "$TEST_CRON" ;;\nesac\n')
        self.script("tmux", f'''socket="${{TMUX%%,*}}"
socket="${{socket:-$TEST_SOCKET}}"
config="$HOME/.tmux.conf"
if [ "$1" = -S ]; then socket="$2"; shift 2; fi
if [ "$1" = -f ]; then config="$2"; shift 2; fi
if [ "$1" = attach ]; then exit 0; fi
exec {shlex.quote(TMUX)} -S "$socket" -f "$config" "$@"
''')
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
        sockets = [self.env["TEST_SOCKET"], *self.home.glob(".claude-logs/workspace-*/tmux.sock")]
        for socket in sockets:
            subprocess.run([TMUX, "-S", str(socket), "kill-server"],
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

    def test_workspace_log_link_survives_other_panes_and_resumes(self):
        self.install()
        logs = self.home / ".claude-logs"
        (logs / "workspace-test").mkdir(mode=0o700)
        logger = logs / "pipe-logger.sh"
        self.run_cmd(str(logger), "router", "0", "0", "workspace-test", input="FIRST\n")
        current = logs / "workspace-test/current"
        self.assertEqual(current.read_text(), "FIRST\n")
        first = current.resolve()
        self.run_cmd(str(logger), "other", "0", "0", input="UNRELATED\n")
        self.assertEqual(current.resolve(), first)
        self.run_cmd(str(logger), "router", "0", "0", "workspace-test", input="RESUMED\n")
        self.assertNotEqual(current.resolve(), first)
        self.assertEqual(current.read_text(), "RESUMED\n")

    def test_workspace_shows_two_panes_and_confines_mouse_selection(self):
        self.consent()
        self.script("claude", 'cat >/dev/null\nprintf "AI_STUB_REPLY\\n"\n')
        original = (self.home / ".tmux.conf").read_bytes()
        self.run_cmd(str(self.cli), "claude")
        state, = (self.home / ".claude-logs").glob("workspace-*")
        socket = str(state / "tmux.sock")
        panes = self.run_cmd(
            "tmux", "-S", socket, "list-panes", "-F",
            "#{pane_id} #{pane_left} #{pane_pipe} #{@terminal_router_role}").stdout.splitlines()
        self.assertEqual(len(panes), 2, panes)
        left, right = (line.split() for line in panes)
        self.assertEqual(left[1:], ["0", "1", "router"])
        self.assertGreater(int(right[1]), 0)
        self.assertEqual(right[2:], ["0", "assistant"])
        self.assertEqual(
            self.run_cmd("tmux", "-S", socket, "show-options", "-v", "-t", left[0], "mouse").stdout.strip(),
            "on")
        self.assertIn("assistant", self.run_cmd(str(self.cli), "doctor").stdout)
        self.assertEqual(self.run_cmd("tmux", "-S", socket, "display-message", "-p", "#{pane_id}").stdout.strip(), left[0])
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", left[0], "-l", "echo ROUTER_WORKSPACE_OUTPUT")
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", left[0], "Enter")
        self.wait_for(lambda: (state / "current").exists() and "ROUTER_WORKSPACE_OUTPUT" in (state / "current").read_text())
        self.wait_for(lambda: "Router observer" in self.run_cmd("tmux", "-S", socket, "capture-pane", "-p", "-t", right[0]).stdout)
        self.wait_for(lambda: "AI_STUB_REPLY" in self.run_cmd("tmux", "-S", socket, "capture-pane", "-p", "-t", right[0]).stdout)
        self.assertNotIn("Router observer", (state / "current").read_text())
        env = dict(self.env, TMUX=f"{socket},0,0", TMUX_PANE=left[0])
        previous = (state / "current").resolve()
        self.run_cmd(str(self.cli), "pause", env=env)
        self.run_cmd(str(self.cli), "resume", env=env)
        self.wait_for(lambda: (state / "current").resolve() != previous)
        env["TMUX_PANE"] = right[0]
        self.assertNotEqual(self.run_cmd(str(self.cli), "resume", env=env, check=False).returncode, 0)
        self.assertEqual((self.home / ".tmux.conf").read_bytes(), original)
        self.assertFalse((self.home / ".bashrc").exists())

    def test_codex_workspace_automatically_reads_router_and_answers_questions(self):
        self.consent()
        self.script("codex", '''exec python3 -c 'import json,sys
from pathlib import Path
with Path("requests.jsonl").open("a") as output:
    output.write(json.dumps({"args":sys.argv[1:], "prompt":sys.stdin.read()})+"\\n")
print("CODEX_STUB_REPLY")' "$@"
''')
        self.run_cmd(str(self.cli))
        state, = (self.home / ".claude-logs").glob("workspace-*")
        socket = str(state / "tmux.sock")
        left, right = self.run_cmd("tmux", "-S", socket, "list-panes", "-a", "-F", "#{window_name} #{pane_id}").stdout.splitlines()
        left = left.split()[1]
        right = right.split()[1]
        for pane, command in ((left, "echo ROUTER_INTERFACE_DOWN"),):
            self.run_cmd("tmux", "-S", socket, "send-keys", "-t", pane, "-l", command)
            self.run_cmd("tmux", "-S", socket, "send-keys", "-t", pane, "Enter")
        requests = state / "requests.jsonl"
        self.wait_for(lambda: requests.exists())
        first = json.loads(requests.read_text().splitlines()[0])
        self.assertIn("ROUTER_INTERFACE_DOWN", first["prompt"])
        self.assertIn("read-only", first["args"])
        self.assertIn("--ignore-user-config", first["args"])
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "-l", "Perche la porta e down?")
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "Enter")
        self.wait_for(lambda: len(requests.read_text().splitlines()) >= 2)
        second = json.loads(requests.read_text().splitlines()[1])
        self.assertIn("Perche la porta e down?", second["prompt"])
        self.assertNotIn("CODEX_STUB_REPLY", (state / "current").read_text())

    def test_auto_off_cancels_running_analysis_and_clears_queued_questions(self):
        self.consent()
        self.script("claude", '''exec python3 -c 'import signal,sys,time
from pathlib import Path
with Path("request-count").open("a") as output:
    output.write("request\\n")
def stop(*unused):
    Path("cancelled").write_text("yes")
    raise SystemExit(0)
signal.signal(signal.SIGTERM, stop)
sys.stdin.read()
while True:
    time.sleep(1)' "$@"
''')
        self.run_cmd(str(self.cli), "claude")
        state, = (self.home / ".claude-logs").glob("workspace-*")
        socket = str(state / "tmux.sock")
        panes = self.run_cmd(
            "tmux", "-S", socket, "list-panes", "-F",
            "#{@terminal_router_role} #{pane_id}").stdout.splitlines()
        right = next(line.split()[1] for line in panes if line.startswith("assistant "))
        self.wait_for(lambda: (state / "request-count").exists())
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "-l", "queued question")
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "Enter")
        self.wait_for(lambda: "question queued" in self.run_cmd(
            "tmux", "-S", socket, "capture-pane", "-p", "-t", right).stdout)
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "-l", ":auto off")
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "Enter")
        self.wait_for(lambda: (state / "cancelled").exists())
        time.sleep(1)
        self.assertEqual((state / "request-count").read_text().splitlines(), ["request"])
        output = self.run_cmd("tmux", "-S", socket, "capture-pane", "-p", "-t", right).stdout
        self.assertIn("running request canceled and queue cleared", output)

    def test_configuration_mode_requires_confirmation_before_sending_command(self):
        self.consent()
        self.script("tio", 'exec -a tio bash -c \'while IFS= read -r line; do printf "TIO_RX:%s\\n" "$line"; done\'\n')
        self.script("claude", 'cat >/dev/null\nprintf "AI_STUB_REPLY\\n"\n')
        self.run_cmd(str(self.cli), "claude")
        state, = (self.home / ".claude-logs").glob("workspace-*")
        socket = str(state / "tmux.sock")
        left, right = self.run_cmd("tmux", "-S", socket, "list-panes", "-a", "-F", "#{window_name} #{pane_id}").stdout.splitlines()
        left = left.split()[1]
        right = right.split()[1]
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", left, "-l", "tio /dev/ttyUSB0")
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", left, "Enter")
        self.wait_for(lambda: self.run_cmd(
            "tmux", "-S", socket, "display-message", "-p", "-t", left,
            "#{pane_current_command}").stdout.strip() == "tio")
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "-l", ":auto off")
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "Enter")
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "-l", ":config on")
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "Enter")
        self.wait_for(lambda: "configuration mode enabled" in self.run_cmd(
            "tmux", "-S", socket, "capture-pane", "-p", "-t", right).stdout)
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "-l", ":apply echo CONFIG_SENT")
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "Enter")
        self.wait_for(lambda: "Pending router commands:" in self.run_cmd(
            "tmux", "-S", socket, "capture-pane", "-p", "-t", right).stdout)
        output = self.run_cmd("tmux", "-S", socket, "capture-pane", "-p", "-t", right).stdout
        match = re.search(r":confirm ([A-F0-9]{12})", output)
        self.assertIsNotNone(match, output)
        self.assertNotIn("TIO_RX:echo CONFIG_SENT", (state / "current").read_text())
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "-l", f":confirm {match.group(1)}")
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "Enter")
        self.wait_for(lambda: "TIO_RX:echo CONFIG_SENT" in (state / "current").read_text())

    def test_ai_proposal_is_staged_automatically_but_sent_only_after_confirmation(self):
        self.consent()
        self.script("tio", 'exec -a tio bash -c \'while IFS= read -r line; do printf "TIO_RX:%s\\n" "$line"; done\'\n')
        self.script(
            "claude",
            'cat >/dev/null\nprintf "Proposed commands.\\nTERMINAL_ROUTER_COMMAND: echo AI_CONFIG_ONE\\nTERMINAL_ROUTER_COMMAND: echo AI_CONFIG_TWO\\n"\n')
        self.run_cmd(str(self.cli), "claude")
        state, = (self.home / ".claude-logs").glob("workspace-*")
        socket = str(state / "tmux.sock")
        left, right = self.run_cmd(
            "tmux", "-S", socket, "list-panes", "-a", "-F",
            "#{window_name} #{pane_id}").stdout.splitlines()
        left = left.split()[1]
        right = right.split()[1]
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", left, "-l", "tio /dev/ttyUSB0")
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", left, "Enter")
        self.wait_for(lambda: self.run_cmd(
            "tmux", "-S", socket, "display-message", "-p", "-t", left,
            "#{pane_current_command}").stdout.strip() == "tio")
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "-l", ":auto off")
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "Enter")
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "-l", ":config on")
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "Enter")
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "-l", "scrivi tu il comando")
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "Enter")
        self.wait_for(lambda: "Pending router commands:" in self.run_cmd(
            "tmux", "-S", socket, "capture-pane", "-p", "-t", right).stdout)
        output = self.run_cmd("tmux", "-S", socket, "capture-pane", "-p", "-t", right).stdout
        match = re.search(r":confirm ([A-F0-9]{12})", output)
        self.assertIsNotNone(match, output)
        self.assertNotIn("TERMINAL_ROUTER_COMMAND:", output)
        self.assertIn("within 120 seconds", output)
        self.assertNotIn("TIO_RX:echo AI_CONFIG_ONE", (state / "current").read_text())
        self.assertNotIn("TIO_RX:echo AI_CONFIG_TWO", (state / "current").read_text())
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "-l", f":confirm {match.group(1)}")
        self.run_cmd("tmux", "-S", socket, "send-keys", "-t", right, "Enter")
        self.wait_for(lambda: all(command in (state / "current").read_text() for command in (
            "TIO_RX:echo AI_CONFIG_ONE", "TIO_RX:echo AI_CONFIG_TWO")))
        router_output = (state / "current").read_text()
        self.assertLess(router_output.index("TIO_RX:echo AI_CONFIG_ONE"),
                        router_output.index("TIO_RX:echo AI_CONFIG_TWO"))

    def test_missing_requested_engine_fails_before_creating_workspace(self):
        self.script("claude", 'exit 99\n')
        result = self.run_cmd(str(self.cli), "codex", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("codex not found", result.stderr)
        self.assertFalse((self.home / ".claude-logs").exists())

    def test_workspace_function_keys_pause_and_resume_without_router_commands(self):
        self.consent()
        self.script("claude", 'cat >/dev/null\necho AI_REPLY\n')
        self.run_cmd(str(self.cli), "claude")
        state, = (self.home / ".claude-logs").glob("workspace-*")
        socket = str(state / "tmux.sock")
        left = self.run_cmd("tmux", "-S", socket, "display-message", "-p", "#{pane_id}").stdout.strip()
        master, slave = pty.openpty()
        client = subprocess.Popen([TMUX, "-S", socket, "attach"], stdin=slave, stdout=slave,
                                  stderr=slave, env=dict(self.env, TERM="xterm"), start_new_session=True)
        os.close(slave)
        try:
            self.wait_for(lambda: bool(self.run_cmd("tmux", "-S", socket, "list-clients").stdout.strip()))
            self.wait_for(lambda: (state / "current").exists())
            previous = (state / "current").resolve()
            os.write(master, b"\x1b[20~")  # xterm F9
            self.wait_for(lambda: self.run_cmd("tmux", "-S", socket, "display-message", "-p", "-t", left, "#{pane_pipe}").stdout.strip() == "0")
            self.assertEqual(self.run_cmd("tmux", "-S", socket, "display-message", "-p", "-t", left, "#{@terminal_router_config_blocked}").stdout.strip(), "1")
            os.write(master, b"\x1b[21~")  # xterm F10
            self.wait_for(lambda: self.run_cmd("tmux", "-S", socket, "display-message", "-p", "-t", left, "#{pane_pipe}").stdout.strip() == "1")
            self.assertEqual(self.run_cmd("tmux", "-S", socket, "display-message", "-p", "-t", left, "#{@terminal_router_config_blocked}").stdout.strip(), "0")
            self.wait_for(lambda: (state / "current").resolve() != previous)
        finally:
            client.terminate()
            client.wait(timeout=5)
            os.close(master)

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
        env = dict(self.env, TMUX=f"{self.env['TEST_SOCKET']},0,0", TMUX_PANE=pane)
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


class PackagingTests(unittest.TestCase):
    def test_tio_is_a_mandatory_dependency(self):
        control = (ROOT / "build/DEBIAN/control").read_text()
        depends = next(line.split(":", 1)[1] for line in control.splitlines()
                       if line.startswith("Depends:"))
        self.assertRegex(depends, r"(^|, )tio(?:,|$)")

    def test_workspace_shows_tio_connection_hint(self):
        script = ROOT / "build/usr/share/terminal-router/workspace.sh"
        result = subprocess.run(
            ["bash", "-c", f"source {shlex.quote(str(script))}; show_connection_hint"],
            capture_output=True, text=True, check=True)
        self.assertIn(
            "tio --baudrate 9600 --databits 8 --parity none --stopbits 1 --flow none /dev/ttyUSB0",
            result.stdout,
        )
        self.assertIn("tio --list", result.stdout)
        self.assertIn("/dev/serial/by-id/", result.stdout)

    def test_installation_banner_uses_configured_package_version(self):
        with tempfile.TemporaryDirectory(prefix="terminal-router-postinst-") as directory:
            query = Path(directory) / "dpkg-query"
            query.write_text("#!/bin/sh\nprintf '%s\\n' \"$TEST_PACKAGE_VERSION\"\n")
            query.chmod(0o755)
            for version in ("1.1.0", "9.8.7"):
                with self.subTest(version=version):
                    env = dict(os.environ, PATH=f"{directory}:{os.environ['PATH']}",
                               TEST_PACKAGE_VERSION=version,
                               DPKG_MAINTSCRIPT_PACKAGE="terminal-router")
                    result = subprocess.run(
                        ["bash", str(ROOT / "build/DEBIAN/postinst"), "configure"],
                        env=env, capture_output=True, text=True, check=True)
                    self.assertIn(f"Terminal Router {version} installed", result.stdout)


if __name__ == "__main__":
    unittest.main()
