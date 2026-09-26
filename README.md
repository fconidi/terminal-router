# terminal-router

[![Release](https://img.shields.io/github/v/release/fconidi/terminal-router)](https://github.com/fconidi/terminal-router/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Opens two independent terminal widgets: **a router/switch shell on the left and
a Claude Code or Codex observer on the right**. Connect to the device from the router
terminal; the observer automatically reads its recorded output and
explains what changes. Ask questions there without opening another terminal or
telling the assistant which tmux log to read.

The typical use case is an interactive SSH session on a Cisco or Huawei
router: the assistant has no access to the device and never needs any. The
operator types, the assistant reads the log and suggests, the operator
decides what to run.

## Contents

- [Quick start](#quick-start)
- [Connecting to a device](#connecting-to-a-device)
- [Workspace and mouse behavior](#workspace-and-mouse-behavior)
- [Assistant controls](#assistant-controls)
- [Guarded configuration](#guarded-configuration)
- [Recording-only modes](#recording-only-modes)
- [Commands](#commands)
- [Security and privacy](#security-and-privacy)
- [Requirements](#requirements)
- [Installation and upgrades](#installation-and-upgrades)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

## Quick start

```bash
terminal-router          # Claude if available, otherwise Codex
terminal-router claude   # explicitly choose Claude Code
terminal-router codex    # explicitly choose Codex
```

On the first run, terminal-router asks you to acknowledge that router output is
recorded and sent to the selected AI provider. The desktop launcher opens a
small terminal for this one-time consent, then future launches open the
workspace directly.

The left side is the only terminal connected to the device. The right side
reads the left-side log, accepts questions and displays advice. If both AI CLIs
are installed, automatic selection prefers Claude Code and then Codex. Use the
explicit commands above whenever you want a specific provider.

## Connecting to a device

### SSH

Run SSH from the left terminal:

```bash
ssh admin@192.168.1.1
```

Host-key and password prompts remain interactive in that terminal. Once the
device starts producing output, the observer analyses it automatically.

### Serial console

The router pane includes serial-console hints for `tio`, `screen` and
`picocom` (`tio` is the recommended default):

```bash
tio --list
tio --baudrate 9600 --databits 8 --parity none --stopbits 1 --flow none /dev/ttyUSB0
screen /dev/ttyUSB0 9600
picocom --baud 9600 --databits 8 --parity n --stopbits 1 --flow n /dev/ttyUSB0
```

Depending on the adapter, use `/dev/ttyACM0` or the stable device path under
`/dev/serial/by-id/`. If the console uses tio's defaults (115200 8N1, no flow
control), `tio /dev/ttyUSB0` is sufficient. Press `Ctrl-t q` to exit tio.

`tio` is installed as a mandatory dependency. `screen` and `picocom` are
optional alternatives and must be installed separately. They work normally
for manual sessions and their output is recorded, but guarded AI command
delivery currently requires `tio` or `ssh` to be the active foreground
program.

## Workspace and mouse behavior

The desktop entry opens this workspace directly in Terminator. The same command
may be launched from MATE Terminal, GNOME Terminal or Terminator; the parent
terminal does not affect the workspace. Router and
observer use two independent terminal widgets and two separate tmux sessions on
the workspace's private server. Only the router terminal is recorded, and the
observer follows a stable link specific to that workspace. Other workspaces and
resumed capture do not redirect the assistant to a different device or to its
own output. Both terminals stay visible; click either side to focus it. Native
selection, Shift-selection, copying and context menus stay inside that widget,
so they cannot include text from the adjacent terminal. In the assistant
widget, use the mouse wheel to browse up to 50,000 lines of tmux history and
Shift-drag for native text selection. Scrolling no longer enters arrow-key
escape sequences in the assistant prompt.

Mouse behavior differs intentionally between the two widgets:

| Widget | Scroll | Select and copy | Context menu |
|---|---|---|---|
| Router, left | Terminal-native | Drag normally | Normal terminal menu |
| Assistant, right | Mouse wheel browses tmux history | Hold Shift and drag | Opens on button release; touchpad two-finger tap is supported |

The assistant retains up to 50,000 displayed lines. This scrollback is separate
from the bounded snapshot sent to the AI provider.

### Language

The observer follows the system locale automatically. Supported languages are
English, Italian, French, German and Spanish; unknown or `C` locales fall back
to English. To choose a language explicitly, set `TR_LANGUAGE` to `en`, `it`,
`fr`, `de` or `es`, for example `TR_LANGUAGE=it terminal-router`. Use
`TR_LANGUAGE=auto` to return to automatic selection.

## Assistant controls

| Input | Effect |
|---|---|
| A question followed by Enter | Analyse the current router state and answer the question |
| Empty Enter | Analyse the current router state immediately |
| `:auto off` | Stop automatic analysis, cancel the active request and clear queued automatic work |
| `:auto on` | Resume automatic analysis after it was disabled or stopped by an error |
| `:config on` | Enable guarded configuration for the current observer |
| `:config off` | Disable guarded configuration and discard pending commands |
| `:apply <command>` | Manually stage one command for confirmation |
| `:confirm <code>` | Send the displayed pending command group once |
| `:cancel` | Discard the pending command group |
| `:quit` | Close the observer while leaving the router terminal available |
| `F9` / `F10` | Pause/resume router recording, including inside SSH or tio |

### Analysis cadence and context

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

## Guarded configuration

Configuration mode is disabled by default and lasts only for the current
observer. AI proposals are treated as untrusted input: every line is validated,
the whole group is displayed, and nothing is sent until the operator enters the
one-time confirmation code. Commands are accepted only when `tio` or `ssh` is
the foreground transport; shell operators, control characters and newlines are
rejected. A group expires after 120 seconds; new AI analyses wait while it is
pending, and F9 blocks it while the router pane is paused.

Typical flow:

```text
:config on
Configure interface Gi0/1 with description UPLINK and enable it

Pending router commands:
  1. configure terminal
  2. interface Gi0/1
  3. description UPLINK
  4. no shutdown
  5. end
Type :confirm A1B2C3D4E5F6 within 120 seconds to send them, or :cancel.
```

Review every line before confirming. Confirmation authorizes exactly the shown
group once; it does not give the assistant continuing control of the terminal.

## Recording-only modes

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

## Security and privacy

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

## Installation and upgrades

### Install the GitHub release

Download the packaged release and let APT install its dependencies:

```bash
wget https://github.com/fconidi/terminal-router/releases/download/v1.1.0/terminal-router_1.1.0_all.deb
sudo apt install ./terminal-router_1.1.0_all.deb
terminal-router
```

The release page also publishes the SHA-256 checksum. Download it beside the
package and verify the file before installing:

```bash
wget https://github.com/fconidi/terminal-router/releases/download/v1.1.0/terminal-router_1.1.0_all.deb.sha256
sha256sum -c terminal-router_1.1.0_all.deb.sha256
```

### Debian / Ubuntu — build the .deb

```bash
git clone https://github.com/fconidi/terminal-router.git
cd terminal-router
bash build-deb.sh
sudo apt install ./terminal-router_1.1.0_all.deb
terminal-router           # as your normal user, not root
```

### Upgrade notes

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

## Troubleshooting

### The workspace says Claude or Codex is missing

Install and authenticate at least one supported CLI, then verify it as your
normal user:

```bash
command -v claude || command -v codex
claude --version    # or: codex --version
```

terminal-router also checks `~/.local/bin` and nvm installations when launched
from the desktop menu.

### The serial device cannot be opened

List devices and permissions:

```bash
tio --list
ls -l /dev/ttyUSB0 /dev/ttyACM0 2>/dev/null
groups
```

On Debian-family systems, serial ports commonly belong to the `dialout` group.
If required, add your user and then log out and back in:

```bash
sudo usermod -aG dialout "$USER"
```

### The observer does not receive new output

Run the read-only diagnostic and inspect the current log:

```bash
terminal-router doctor
terminal-router tail
```

Check that recording was not paused with F9 and that the device command runs in
the left widget. The right widget is deliberately excluded from capture.

### Automatic analysis stopped

The provider CLI may have expired authentication, returned an error or exceeded
the 120-second timeout. Check the visible error, sign in to the selected CLI if
needed, then enter `:auto on`.

### Terminator prints warnings in the launching terminal

Messages about `hide_window`, `match_remove` or a window missing from the
registered list originate from Terminator when another instance owns a global
shortcut or when the independent layout closes. If both widgets open and work,
these warnings do not indicate lost router output. Use `terminal-router doctor`
to diagnose the capture path itself.

### Remove terminal-router configuration

```bash
terminal-router remove
```

This removes only managed shell/tmux blocks, preserving backups and unrelated
configuration. APT package removal is separate: `sudo apt remove
terminal-router`.


## Development

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
