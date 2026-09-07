# terminal-router

Records every interactive terminal session into a per-pane log file under
`~/.claude-logs`, so an AI assistant such as Claude Code or Codex can follow
a live CLI session in real time by reading a single file — without ever
having access to the device or shell itself.

The typical use case is an interactive SSH session on a Cisco or Huawei
router: the assistant has no access to the device and never needs any. The
operator types, the assistant reads the log and suggests, the operator
decides what to run.

## How it works

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
install time — you opt in explicitly with `terminal-router install` (or
`launch`), after acknowledging that the log captures whatever is printed
on screen. Never run these as root: they configure the calling user's
`$HOME`, and `sudo` would target `/root` instead.

## Commands

| Command | Effect |
|---|---|
| `terminal-router install` | set up the hooks for the current user (every terminal) |
| `terminal-router launch` | log a single session only, no dotfile edits |
| `terminal-router remove` | undo them (files backed up as `*.terminal-router.bak`) |
| `terminal-router status` | what's active, how much has been logged |
| `terminal-router tail` | follow the newest pane log |
| `terminal-router menu` | interactive menu (used by the desktop entry) |

Inside a logged pane: `logpause` detaches logging from that pane,
`logresume` resumes it into a new file. Use them around sensitive work.

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

`bash`, `tmux`. `cron` recommended (log rotation); `claude` and/or `codex`
on `PATH` so something actually reads the log — `install`/`launch`/`status`
warn (without blocking) if neither is found.

## Install

### Debian / Ubuntu — build the .deb

```bash
git clone https://github.com/fconidi/terminal-router.git
cd terminal-router
bash build-deb.sh
sudo apt install ./terminal-router_*_all.deb
terminal-router install   # as your normal user, not root
```

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

## License

MIT — see [LICENSE](LICENSE).
