#!/bin/bash
# terminal-router — per-user installer.
#
# Sets up automatic tmux logging of every interactive terminal, so Claude Code
# can follow a live router CLI session (Cisco/Huawei over SSH) by reading
# ~/.claude-logs/latest. Claude never touches the device: the operator types,
# Claude reads the log and suggests, the operator executes.
#
# Runs as the invoking user and writes only inside $HOME. Never run with sudo.
# Idempotent: safe to re-run, does not duplicate blocks.
#
# Normally invoked via: terminal-router install
#
# With "logdir-only" as $1 (used by "terminal-router launch"), only the log
# directory, pipe-logger.sh and rotation cron are set up — ~/.bashrc,
# ~/.zshrc and ~/.tmux.conf are left untouched, since launch mode logs a
# single self-contained tmux session instead of every terminal.

set -euo pipefail

MODE="${1:-full}"

# Marker strings are intentionally kept as "claude-terminal-log" (the name of
# the standalone script this package supersedes) so that machines set up with
# the pre-packaging installer are recognised, updated and removed correctly.
MARK_BEGIN="# >>> claude-terminal-log >>>"
MARK_END="# <<< claude-terminal-log <<<"
LOGDIR="$HOME/.claude-logs"
RCFILE="$HOME/.bashrc"
[ "$(basename "${SHELL:-}")" = "zsh" ] && RCFILE="$HOME/.zshrc"

echo "== terminal-router: install =="

if [ "$(id -u)" -eq 0 ]; then
    echo "ERROR: do not run as root/sudo — this configures the calling user's" >&2
    echo "       HOME, and as root it would only configure /root." >&2
    exit 1
fi

if ! command -v tmux > /dev/null 2>&1; then
    echo "ERROR: tmux not found (it is a package dependency)." >&2
    echo "       Fix with: sudo apt install --reinstall terminal-router" >&2
    exit 1
fi

# --- refuse to stack a second copy on top of an unmarked legacy setup ---
# Machines configured with the pre-packaging script and then hand-edited may
# have lost the marker comments while keeping a working setup. Appending our
# block there would duplicate the tmux auto-start and the logpause/logresume
# definitions, so detect it and stop. Not relevant in logdir-only mode, which
# never touches either file.
if [ "$MODE" = "full" ]; then
    legacy_unmarked() {
        local f="$1"
        [ -f "$f" ] || return 1
        grep -qF "$MARK_BEGIN" "$f" && return 1
        grep -qE 'logpause\(\)|claude-logs/pipe-logger\.sh' "$f"
    }

    LEGACY=""
    legacy_unmarked "$RCFILE" && LEGACY="$RCFILE"
    legacy_unmarked "$HOME/.tmux.conf" && LEGACY="$LEGACY $HOME/.tmux.conf"

    if [ -n "$LEGACY" ]; then
        echo "ERROR: an older, unmarked setup was found in:" >&2
        for f in $LEGACY; do echo "         $f" >&2; done
        echo >&2
        echo "       It works, but it has no '$MARK_BEGIN' markers, so this" >&2
        echo "       installer cannot tell where it starts and ends. Continuing" >&2
        echo "       would append a second copy and define logpause/logresume" >&2
        echo "       twice." >&2
        echo >&2
        echo "       Fix: back up those files, delete the old tmux auto-start and" >&2
        echo "       logpause/logresume sections by hand, then re-run this." >&2
        echo "       Your logs in $LOGDIR are not affected." >&2
        exit 1
    fi
fi

# --- log dir + pipe script ---
mkdir -p "$LOGDIR"
chmod 700 "$LOGDIR"
cat > "$LOGDIR/pipe-logger.sh" <<'EOF'
#!/bin/bash
# Auto-invoked by a tmux hook (~/.tmux.conf). Logs one pane to its own file and
# keeps ~/.claude-logs/latest pointing at the most recently created pane, so
# Claude Code always has a stable path to tail.
umask 077
LOGDIR="$HOME/.claude-logs"
TS=$(date +%Y%m%d-%H%M%S)
FILE="$LOGDIR/tmux-$1-$2-$3-$TS.log"
ln -sf "$FILE" "$LOGDIR/latest"
cat >> "$FILE"
EOF
chmod 700 "$LOGDIR/pipe-logger.sh"
echo "OK    $LOGDIR/pipe-logger.sh (dir 700, new files 600 via umask)"

# --- rotation: daily cron, delete logs older than 30 days ---
CRON_LINE="find $LOGDIR -maxdepth 1 -name 'tmux-*.log' -mtime +30 -delete"
if ! command -v crontab > /dev/null 2>&1; then
    echo "WARN  crontab not found — log rotation not configured."
    echo "      Install cron (sudo apt install cron) and re-run, or prune manually."
elif crontab -l 2>/dev/null | grep -qF "$LOGDIR"; then
    echo "SKIP  crontab (rotation already present)"
else
    # 'crontab -l || true': it exits 1 when the user has no crontab at all,
    # which under set -e + pipefail would abort the whole installer.
    { crontab -l 2>/dev/null || true; echo "0 3 * * * $CRON_LINE"; } | crontab -
    echo "OK    crontab: daily 03:00, logs older than 30 days deleted"
fi

if [ "$MODE" = "full" ]; then

# --- ~/.tmux.conf ---
TMUX_BLOCK="$MARK_BEGIN
# Auto-log every pane (session/window/split) for real-time monitoring by
# Claude Code. Files: ~/.claude-logs/tmux-<sess>-<win>-<pane>-<timestamp>.log
# Always-current symlink: ~/.claude-logs/latest
set-hook -g after-new-session 'pipe-pane -o \"~/.claude-logs/pipe-logger.sh #S #I #P\"'
set-hook -g after-new-window 'pipe-pane -o \"~/.claude-logs/pipe-logger.sh #S #I #P\"'
set-hook -g after-split-window 'pipe-pane -o \"~/.claude-logs/pipe-logger.sh #S #I #P\"'
$MARK_END"

touch "$HOME/.tmux.conf"
if grep -qF "$MARK_BEGIN" "$HOME/.tmux.conf"; then
    echo "SKIP  ~/.tmux.conf (block already present)"
else
    printf '\n%s\n' "$TMUX_BLOCK" >> "$HOME/.tmux.conf"
    echo "OK    ~/.tmux.conf updated"
fi

# --- rc file (bashrc/zshrc) ---
RC_BLOCK="$MARK_BEGIN
# Auto-enter tmux on every interactive terminal, one independent session per
# tab/window so Terminator tabs stay separate instead of all mirroring the same
# view. Each pane is then logged automatically via the ~/.tmux.conf hooks.
# Note: plain 'tmux new-session', NOT 'exec tmux new-session' — exec would
# replace the shell, so detaching (Ctrl+b d) closed the whole terminal.
if command -v tmux &> /dev/null && [ -z \"\${TMUX:-}\" ] && [ -n \"\${PS1:-}\" ] && [[ ! \"\$TERM\" =~ screen ]] && [ -t 0 ] && [ -t 1 ]; then
    tmux new-session
fi

# Logging kill-switch: suspend before sensitive work (production SSH, secrets,
# credentials), resume afterwards. Only meaningful inside a tmux session.
logpause() {
    if [ -n \"\${TMUX:-}\" ]; then
        tmux pipe-pane
        echo \"[logging suspended for this pane]\"
    else
        echo \"[not inside tmux, nothing to suspend]\"
    fi
}
logresume() {
    if [ -n \"\${TMUX:-}\" ]; then
        tmux pipe-pane -o \"~/.claude-logs/pipe-logger.sh #S #I #P\"
        echo \"[logging resumed, new file]\"
    else
        echo \"[not inside tmux, nothing to resume]\"
    fi
}
$MARK_END"

touch "$RCFILE"
if grep -qF "$MARK_BEGIN" "$RCFILE"; then
    echo "SKIP  $RCFILE (block already present)"
else
    printf '\n%s\n' "$RC_BLOCK" >> "$RCFILE"
    echo "OK    $RCFILE updated"
fi

echo
echo "Done. Open a new terminal (or: source $RCFILE) to activate."
echo "  Live log:       terminal-router tail"
echo "  Status:         terminal-router status"
echo "  Remove:         terminal-router remove"
echo "  Pause/resume:   logpause / logresume   (inside a pane)"
echo
echo "Permissions: directory 700, files 600. Rotation: logs older than 30 days"
echo "are deleted nightly at 03:00."
echo
echo "WARNING: the log captures everything printed on screen, including any"
echo "password passed as a plaintext command-line argument (mysql -pXXX,"
echo "curl -H \"Authorization: ...\", cat of a .env file). Passwords typed at an"
echo "interactive sudo/SSH prompt are NOT captured (no tty echo)."
echo "Manual cleanup: rm ~/.claude-logs/tmux-*.log"

else
    echo "OK    logdir + rotation ready, ~/.bashrc/~/.zshrc/~/.tmux.conf untouched"
fi
