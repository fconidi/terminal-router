# Changelog

All notable changes to this project are documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.3.8] - 2026-09-26

### Fixed
- Router and assistant now run in two independent Terminator widgets backed by
  separate tmux sessions. Native selection and context menus are confined to
  one side and can no longer include characters from the adjacent terminal.
- The desktop launcher opens the graphical workspace directly without leaving
  an unused MATE Terminal window behind.
- Launching from MATE Terminal, GNOME Terminal or Terminator now produces the
  same isolated two-widget workspace.

## [1.3.7] - 2026-09-26

### Fixed
- The tmux pane menu now opens on right-button release, so a touchpad
  two-finger tap no longer opens and immediately dismisses it.
- Dragging without Shift copies only the selected pane directly to the system
  clipboard through `xclip`. The workspace now states that Shift bypasses tmux.

## [1.3.6] - 2026-09-25

### Fixed
- `:auto off` now cancels the active AI request and clears queued questions, so
  no delayed analyses or tips appear after automatic mode is disabled.

## [1.3.5] - 2026-09-25

### Fixed
- The observer now reads up to the latest 128 KiB of router output without an
  80-line cutoff, preserving the beginning of typical long command results.

## [1.3.4] - 2026-09-25

### Fixed
- Pending AI command groups now remain confirmable for 120 seconds.
- Automatic and queued AI analyses wait while confirmation is pending, keeping
  the command list and one-time code visible and stable.

## [1.3.3] - 2026-09-25

### Fixed
- In configuration mode, Claude/Codex command proposals are now staged
  automatically instead of asking the operator to copy them into `:apply`.
- A confirmed proposal can contain up to 32 validated commands; the complete
  group is shown before one-time confirmation and sent to the router in order.

## [1.3.2] - 2026-09-25

### Fixed
- The router and AI observer are visible side by side again.
- Mouse selection is handled by tmux and confined to the selected pane, so
  copied router commands do not include text from the observer.

## [1.3.1] - 2026-09-25

### Fixed
- The router and AI observer now use separate tmux windows, so mouse selection
  and copy operations cannot mix characters between terminals.

## [1.3.0] - 2026-09-25

### Added
- Optional guarded configuration mode for the integrated workspace.
- Manual `:apply` and one-time `:confirm` flow with expiry, retry limits and
  transport checks before a command reaches `tio` or `ssh`.
- F9 pause state now blocks confirmed configuration commands.

## [1.2.2] - 2026-09-25

### Fixed
- The observer now follows the system locale instead of always displaying
  Italian text.

### Added
- English, Italian, French, German and Spanish observer messages and prompts.
- `TR_LANGUAGE` override with English fallback for unknown locales.

## [1.2.1] - 2026-09-25

### Added
- `tio` is now a mandatory package dependency for serial-console access.
- The integrated router pane shows example `tio` commands, device discovery
  with `tio --list`, and common USB serial device alternatives.

## [1.2.0] - 2026-09-24

### Added
- Two-pane workspace: router/switch shell left, Claude/Codex observer right,
  with automatic analysis and questions. Choose with `terminal-router claude`
  or `terminal-router codex`.
- Stable workspace log links across pause/resume. Each workspace has a dedicated
  tmux server; only the router pane is captured, ignoring global hooks.
- F9/F10 pause/resume recording even inside SSH; mouse pane selection and labels.
- Observer batches changes, bounds recent context, avoids idle requests and stops
  automatic requests on AI errors. Replies never become terminal input.
- Status/doctor discover workspaces. Tests cover both simulated AI engines and
  keyboard controls through a real tmux pseudoterminal client.

### Changed
- No-argument and desktop startup open the workspace. `menu` retains setup
  options; `launch` retains the previous recording-only session.
- Python 3 is now a runtime dependency, without third-party Python packages.
- Workspace output is sent to the selected AI provider using the CLI account;
  recording-only modes continue to keep logs local.
- Updated the man page with workspace usage, observer commands and F9/F10.

## [1.1.1] - 2026-09-23

### Fixed
- Installation banner reads the configured version from dpkg instead of showing
  the hard-coded 1.0.7. A regression test checks current and future versions.
- Installation notice now accounts for existing user setups during upgrades
  and recommends the pause command available in both logging modes.

## [1.1.0] - 2026-09-23

### Added
- `pause` and `resume` commands target the calling pane, including one-shot
  `launch` sessions. Existing `logpause` / `logresume` become shortcuts.
- Read-only `doctor` command checks setup, permissions, the `latest` link and
  live tmux panes. Errors return exit status 1; advisory warnings do not.
- Integration tests using temporary homes, a fake crontab and private tmux
  sockets; no router, credentials or real user configuration are required.

### Fixed
- Quote session names and logger paths before passing them to the shell;
  sanitize file labels, create unique private logs for rapid resumes and
  replace `latest` atomically after creating the log.
- `launch` handles nonzero window indices and renumbering, checks setup
  failures and cleans up its new session if configuring hooks fails.
- `install` and `launch` propagate installer errors instead of reporting success.
- `tail` follows changes to `latest` instead of staying on the previous log.
- Reinstall updates existing marked blocks with backups; incomplete or duplicate
  markers are rejected before editing. Removal checks both Bash and Zsh files.
- Rotation quotes HOME and matches only the exact managed cron entry, preserving
  unrelated jobs mentioning the log directory and migrating the old entry.
- Clarify that detaching tmux leaves capture running.

### Changed
- Require tmux 3.0 or newer for the hook command syntax.
- Keep editable man-page and Debian changelog sources under `docs/`; rebuild
  their compressed copies when packaging.

## [1.0.7] - 2026-09-15

### Fixed
- `remove`: fixed a crontab race where `crontab -l` was read twice (once to
  check, once to filter) instead of once; a concurrent crontab edit between
  the two reads could make the filter step overwrite the user's entire
  crontab with an empty one. Now reads it once and reuses that snapshot for
  both the check and the rewrite.
- Packaging: corrected `debian/copyright`, which declared `GPL-3+` while the
  project has always been MIT (see `LICENSE`).
- Packaging: `changelog.gz` and the man page were stuck at 1.0.5 while the
  package itself was already at 1.0.6; both now track the real version.

## [1.0.6] - 2026-09-06

### Fixed
- `assistant_status` (used by `install`/`launch`/`status` to warn when no AI
  assistant is on `PATH`) missed `claude`/`codex` when launched from a
  desktop menu entry: in that non-interactive shell, `~/.bashrc`'s own
  "not interactive? return" guard skips PATH/nvm setup entirely, so an
  installed assistant looked missing. Now also checks the common install
  locations (`~/.local/bin`, `~/.nvm/versions/node/*/bin`) directly.

## [1.0.5] - 2026-09-05

### Added
- `install`, `launch` and `status` now check whether `claude` or `codex` is
  on `PATH` and warn (without blocking) if neither is found, since the log
  then has no AI assistant to read it.

## [1.0.4] - 2026-09-05

### Added
- New command `terminal-router launch`: logs a single self-contained tmux
  session instead of every terminal, with no edits to `~/.bashrc`,
  `~/.zshrc` or `~/.tmux.conf`. Pipe-pane hooks are set on that one session
  only (no `-g`) and disappear with it, so other terminals — Terminator
  included — are unaffected.
- `install.sh`: new "logdir-only" mode (used by `launch`) that sets up
  `~/.claude-logs`, `pipe-logger.sh` and the rotation cron without touching
  the shell rc file or `~/.tmux.conf`.
- Menu: added "Launch a single logged session" entry.

## [1.0.3] - 2026-09-04

### Fixed
- `postinst`/`postrm`: stop rebuilding man, icon and desktop caches directly
  while APT holds its shutdown inhibitor. This avoids leaving the system
  unable to power off if an external cache updater stalls during package
  installation or removal.
- `terminal-router` now reports the packaged version correctly.

## [1.0.2] - 2026-09-04

### Fixed
- Menu placement, final: the entry now appears only in the SysLinuxOS
  "Networking" and "SysLinuxOS Tools" menus.
  - "Networking" comes from the `X-SysLinuxOS-Networking` category, also
    excluded from Accessories/Internet/System/Other so the entry doesn't
    show up twice.
  - "SysLinuxOS Tools" includes entries by explicit filename, which no
    category can reach, so the package ships a menu drop-in under
    `/etc/xdg/menus/applications-merged/` instead of patching
    `/etc/xdg/menus/mate-applications.menu` (a conffile owned by
    `mate-menus`).
- `postinst` now mentions that MATE caches the menu and may need a panel
  restart.

## [1.0.1] - 2026-09-04

### Added
- Menu placement: added the `X-SysLinuxOS-Networking` category so the entry
  lands in the SysLinuxOS "Networking" menu, next to gtkterm and cutecom,
  instead of the generic "Internet" menu.
- `status` now reports a detected unmarked legacy setup.
- `remove` now warns that an unmarked legacy block can't be removed
  automatically.

### Fixed
- `install` refuses to append a second block when an older, unmarked setup
  is detected, which would otherwise duplicate the tmux auto-start and
  define `logpause`/`logresume` twice.
- `install` no longer aborts on machines with no existing crontab, where
  `crontab -l` exits non-zero and `set -e`/`pipefail` killed the installer
  before the hooks were written.

## [1.0.0] - 2026-09-04

Initial release.

### Added
- `terminal-router` front-end: `install`, `remove`, `status`, `tail`,
  `menu`.
- Packages the standalone `claude-terminal-log` installer as a SysLinuxOS
  menu entry with icon.
- Removal path (marked blocks deleted with backups, crontab entry dropped,
  optional log deletion), which the standalone script lacked.
- `tmux` is now a package dependency, so the installer no longer prompts
  to install it.
- Opt-in: nothing is logged until the user accepts the security notice.
