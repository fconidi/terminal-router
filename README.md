# terminal-router

Opens two independent terminal widgets: **a router/switch shell on the left and
a Claude Code or Codex observer on the right**. Connect to the device from the router
terminal; the observer automatically reads its recorded output and
explains what changes. Ask questions there without opening another terminal or
telling the assistant which tmux log to read.

The typical use case is an interactive SSH session on a Cisco or Huawei
router: the assistant has no access to the device and never needs any. The
operator types, the assistant reads the log and suggests, the operator
decides what to run.

## How it works

```bash
terminal-router          # Claude if available, otherwise Codex
terminal-router claude   # explicitly choose Claude Code
terminal-router codex    # explicitly choose Codex
```

The router pane includes a serial-console hint for `tio`:

```bash
tio --list
tio --baudrate 9600 --databits 8 --parity none --stopbits 1 --flow none /dev/ttyUSB0
```

Depending on the adapter, use `/dev/ttyACM0` or the stable device path under
`/dev/serial/by-id/`. If the console uses tio's defaults (115200 8N1, no flow
control), `tio /dev/ttyUSB0` is sufficient. Press `Ctrl-t q` to exit tio.

The desktop entry opens this workspace directly in Terminator. The same command
may be launched from MATE Terminal, GNOME Terminal or Terminator; the parent
terminal does not affect the workspace. Router and
observer use two independent terminal widgets and two separate tmux sessions on
the workspace's private server. Only the router terminal is recorded, and the
observer follows a stable link specific to that workspace. Other workspaces and
resumed capture do not redirect the assistant to a different device or to its
own output. Both terminals stay visible; click either side to focus it. Native
selection, Shift-selection, copying and context menus stay inside that widget,
so they cannot include text from the adjacent terminal.

The observer follows the system locale automatically. Supported languages are
English, Italian, French, German and Spanish; unknown or `C` locales fall back
to English. To choose a language explicitly, set `TR_LANGUAGE` to `en`, `it`,
`fr`, `de` or `es`, for example `TR_LANGUAGE=it terminal-router`. Use
`TR_LANGUAGE=auto` to return to automatic selection.

- **F9 / F10:** pause/resume router recording, including while connected over SSH.
- In the AI pane, type a question or press Enter to analyse the current output.
- `:auto off` / `:auto on`: disable/enable automatic analysis. Turning it off
  cancels the active request and clears queued questions; new questions typed
  afterwards still work.
- `:config on` / `:config off`: enable/disable guarded router configuration mode.
- Ask the AI to apply or type the commands. It stages every proposed command,
  shows the complete ordered group, and waits for `:confirm <code>` before
  sending anything to the router pane. Up to 32 commands can be confirmed as
  one group. Use `:cancel` to discard it; `:apply <command>` remains a manual
  fallback for one command.
- `:quit`: close the observer; the router pane remains available.

Automatic analysis groups updates after two quiet seconds (at most five seconds
of continuous output), with at least ten seconds between automatic requests.
AI response time is additional. Unchanged output makes no new request. Each
request contains up to the latest 128 KiB of router output and the previous
exchange. This preserves the beginning of typical long command results without
sending an unbounded session history. AI errors stop automatic requests; fix
CLI login or configuration and use `:auto on` to retry.

Captured output is sent to the chosen AI provider through your authenticated
CLI, with normal account usage. Replies are advice: the observer never types
or executes commands in the router pane. Pausing capture prevents new automatic
requests; a request already sent can still finish.

Configuration mode is disabled by default and lasts only for the current
observer. AI proposals are treated as untrusted input: every line is validated,
the whole group is displayed, and nothing is sent until the operator enters the
one-time confirmation code. Commands are accepted only when `tio` or `ssh` is
the foreground transport; shell operators, control characters and newlines are
rejected. A group expires after 120 seconds; new AI analyses wait while it is
pending, and F9 blocks it while the router pane is paused.

The existing global recording mode remains available with `terminal-router install`:

- Every interactive terminal you open enters its own tmux session, via a
  marked block added to `~/.bashrc` (or `~/.zshrc`).
- tmux hooks in `~/.tmux.conf` intercept each new pane (session, window,
  split) and pipe its output to a logger script.
- `~/.claude-logs/pipe-logger.sh` writes a timestamped file per pane and
  keeps the symlink `~/.claude-logs/latest` pointing at the newest one.
- The assistant tails that symlink.

`terminal-router launch` is a lighter alternative: it starts one tmux
session with the logging hooks set directly on that session (no `-g`), so
they log only its own windows/splits and vanish when the session ends.
Nothing is written to `~/.bashrc`, `~/.zshrc` or `~/.tmux.conf` — every
other terminal, Terminator tabs included, stays unaffected.

Everything is per-user and confined to `$HOME`. Nothing is enabled at
install time — you opt in by opening a workspace, or using `install` or
`launch`, after acknowledging that the log captures whatever is printed
on screen. Never run these as root: they configure the calling user's
`$HOME`, and `sudo` would target `/root` instead.

## Commands

| Command | Effect |
|---|---|
| `terminal-router [claude\|codex]` | integrated router + AI workspace (also the default with no arguments) |
| `terminal-router workspace [claude\|codex]` | explicit workspace command |
| `terminal-router install` | set up the hooks for the current user (every terminal) |
| `terminal-router launch` | log a single session only, no dotfile edits |
| `terminal-router remove` | undo them (files backed up as `*.terminal-router.bak`) |
| `terminal-router status` | what's active, how much has been logged |
| `terminal-router doctor` | diagnose setup, permissions and live panes without changes |
| `terminal-router tail` | follow the newest pane log, switching when `latest` changes |
| `terminal-router pause` | suspend capture in the calling tmux pane |
| `terminal-router resume` | resume that pane into a new log |
| `terminal-router menu` | configuration menu and alternate launch options |

Inside a logged pane, use `terminal-router pause` before sensitive work and
`terminal-router resume` afterwards. These commands also work with `launch`.
After `install`, `logpause` and `logresume` are shell shortcuts.
Repeating `resume` while a pipe is active leaves it unchanged.
Detaching with **Ctrl+b d does not stop logging or the observer**; pause first
if needed. Workspace F9/F10 always target the original router pane.

`doctor` returns 1 when it finds a setup or permission error, and 0 otherwise.
Missing rotation or an idle tmux server are advisory warnings. A live pipe
does not prove that output is reaching disk; inspect the log when diagnosing
capture problems.

## Security

The log captures everything visible on screen. Passwords typed at an
interactive prompt (`sudo`, SSH password auth) are **not** captured — the
tty doesn't echo them, so tmux's pipe-pane never sees them. What **is**
captured includes:

- passwords passed as plaintext arguments, e.g. `mysql -pXXX`
- tokens in headers, e.g. `curl -H "Authorization: Bearer XXX"`
- `export TOKEN=...` typed in the clear
- the output of `cat` on a `.env` file or a private key

Mitigations applied automatically:

- `~/.claude-logs` is mode `0700`, log files `0600`, logger runs with
  `umask 077`
- nightly rotation (cron, 03:00) deletes logs older than 30 days
- `logpause` / `logresume` kill-switch for sensitive work
- the directory sits outside any cloud-synced folder

Not automated — worth doing yourself: prefer SSH key auth over passwords,
run `logpause` before typing a secret as a command-line argument, and
manually clean up with `rm ~/.claude-logs/tmux-*.log` when needed.

## Requirements

`bash`, `tmux >= 3.0`, `python3` (standard library only), `tio`, and `terminator`.
`cron` is recommended
for log rotation. Workspaces require a current, authenticated Claude Code or
Codex CLI, found on PATH, in `~/.local/bin`, or under nvm. Recording-only commands
still work without AI.

The observer disables shell tools and configured integrations and ignores project
configuration. Codex also runs read-only. Authentication is retained; optional
`TR_CLAUDE_MODEL` / `TR_CODEX_MODEL` select a model, otherwise the CLI default
is used. Older CLIs lacking these flags report an error rather than falling
back to more permissive execution.

## Install

### Debian / Ubuntu — build the .deb

```bash
git clone https://github.com/fconidi/terminal-router.git
cd terminal-router
bash build-deb.sh
sudo apt install ./terminal-router_1.3.8_all.deb
terminal-router           # as your normal user, not root
```

After upgrading from 1.0.x, re-run `terminal-router install` if you use the
global setup. It updates only marked blocks, saves `*.terminal-router.bak`,
and preserves surrounding settings. Existing tmux servers keep their loaded
hooks: reload your config with `tmux source-file ~/.tmux.conf` and use
`terminal-router pause` / `resume` in existing panes to replace old pipes.
For one-shot use, start a fresh `terminal-router launch` session instead.

### SysLinuxOS

Already packaged in the SysLinuxOS APT repo:

```bash
echo "deb https://fconidi.github.io/SysLinuxOS-Tools tirreno main" | sudo tee /etc/apt/sources.list.d/syslinuxos-tools.list
wget -qO- https://fconidi.github.io/SysLinuxOS-Tools/syslinuxos-archive-keyring.asc | sudo tee /usr/share/keyrings/syslinuxos-archive-keyring.asc > /dev/null
sudo apt update && sudo apt install terminal-router
```

## Syncing from syslinuxos-packages

Day-to-day fixes happen in the `syslinuxos-packages` monorepo (which also
builds and publishes the SysLinuxOS `.deb`). To pull those changes into
this repo with full commit history via `git subtree`:

```bash
scripts/sync-from-monorepo.sh [path-to-syslinuxos-packages]
```

The 1.1.x and 1.2.0 changes were developed in this standalone repository; reconcile them
with the monorepo before the next sync to avoid restoring older code.

## Development checks

Run as a normal user with Python 3 and tmux installed:

```bash
python3 -m unittest discover -s tests -v
bash build-deb.sh
```

Tests isolate HOME and tmux sockets under `/tmp`, use a fake crontab, and
simulate both AI CLIs. They exercise actual tmux capture, automatic analysis,
operator questions and F9/F10 through a pseudoterminal. No router or AI account
is contacted; live authentication/model quality still needs an operator test.

Hook arguments use tmux's shell-quoting modifier, as documented in the
[tmux formats reference](https://github.com/tmux/tmux/wiki/Formats).
The hook configuration syntax requires [tmux 3.0 or newer](https://github.com/tmux/tmux/blob/3.0/CHANGES).
Further ideas and their acceptance criteria are in [ROADMAP.md](ROADMAP.md).

## License

MIT — see [LICENSE](LICENSE).
