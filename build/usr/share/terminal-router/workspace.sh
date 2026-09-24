# Integrated two-pane workspace; sourced by terminal-router.
resolve_assistant() {
    local name="$1" path
    path=$(command -v "$name") && { printf '%s\n' "$path"; return 0; }
    for path in "$HOME/.local/bin/$name" "$HOME"/.nvm/versions/node/*/bin/"$name"; do
        [ -x "$path" ] && { printf '%s\n' "$path"; return 0; }
    done
    return 1
}

shell_quote() { printf "'%s'" "${1//\'/\'\\\'\'}"; }

cmd_workspace() {
    require_user
    [ -z "${TMUX:-}" ] || die "detach first (Ctrl+b d), then open terminal-router from a plain terminal."
    local engine="${1:-}" binary state socket session left right command
    local hook='exec "$HOME/.claude-logs/pipe-logger.sh" #{q:session_name} #I #P #{q:@terminal_router_log_key}'
    case "$engine" in
        "")
            if binary=$(resolve_assistant claude); then engine=claude
            elif binary=$(resolve_assistant codex); then engine=codex
            else die "install and sign in to Claude Code or Codex first; 'terminal-router launch' records without AI."
            fi ;;
        claude|codex) binary=$(resolve_assistant "$engine") || die "$engine not found; install and sign in first." ;;
        *) die "usage: terminal-router workspace [claude|codex]" ;;
    esac
    command -v python3 >/dev/null || die "python3 is required for the AI observer."
    ensure_consent || return 1
    bash "$INSTALLER" logdir-only || return $?
    state=$(mktemp -d "$LOGDIR/workspace-XXXXXXXX") || return 1
    socket="$state/tmux.sock"
    session="router-${state##*workspace-}"
    # In particular, ignore global logging hooks which would record the AI pane.
    left=$(tmux -S "$socket" -f /dev/null new-session -d -s "$session" -n router -x 160 -y 40 -P -F '#{pane_id}') || {
        rmdir "$state" 2>/dev/null || true
        die "could not create workspace."
    }
    # Include the engine's directory for node-based installations started from a menu.
    command="export PATH=$(shell_quote "${binary%/*}:$PATH"); exec python3"
    command+=" $(shell_quote "${INSTALLER%/*}/observer.py") $(shell_quote "$engine")"
    command+=" $(shell_quote "$binary") $(shell_quote "$state") $(shell_quote "$left")"
    if ! tmux -S "$socket" set-option -t "$session" mouse on ||
       ! tmux -S "$socket" set-option -w -t "$left" pane-border-status top ||
       ! tmux -S "$socket" set-option -w -t "$left" pane-border-format ' #{@terminal_router_role} ' ||
       ! tmux -S "$socket" set-option -p -t "$left" @terminal_router_role router ||
       ! tmux -S "$socket" set-option -p -t "$left" @terminal_router_log_key "${state##*/}" ||
       ! tmux -S "$socket" pipe-pane -o -t "$left" "$hook" ||
       ! tmux -S "$socket" bind-key -n F9 pipe-pane -t "$left" ||
       ! tmux -S "$socket" bind-key -n F10 pipe-pane -o -t "$left" "$hook" ||
       ! tmux -S "$socket" set-option -t "$session" status-right ' F9 pausa | F10 riprendi ' ||
       ! right=$(tmux -S "$socket" split-window -h -t "$left" -P -F '#{pane_id}' "$command") ||
       ! tmux -S "$socket" set-option -p -t "$right" @terminal_router_role assistant ||
       ! tmux -S "$socket" select-pane -t "$left"; then
        tmux -S "$socket" kill-server 2>/dev/null || true
        die "could not configure workspace; its tmux server was closed."
    fi
    echo "Router on the left; $engine observer on the right. Click a pane to switch."
    echo "Captured output is sent to your configured AI provider; normal account usage applies."
    echo "Detach: Ctrl+b d. Reattach: tmux -S $(shell_quote "$socket") attach"
    exec tmux -S "$socket" attach -t "$session"
}
