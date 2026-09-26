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

CONNECTION_HINT='Serial console connection (tio):
  tio --list
  tio --baudrate 9600 --databits 8 --parity none --stopbits 1 --flow none /dev/ttyUSB0

Other common devices are /dev/ttyACM0 or /dev/serial/by-id/<device-name>.
If the device uses tio defaults (115200 8N1, no flow control):
  tio /dev/ttyUSB0
Inside tio, press Ctrl-t q to exit.'

show_connection_hint() {
    printf '%s\n' "$CONNECTION_HINT"
}

cmd_workspace() {
    require_user
    [ -z "${TMUX:-}" ] || die "detach first (Ctrl+b d), then open terminal-router from a plain terminal."
    local engine="${1:-}" binary state socket session left right command router_command router_shell hook_for_binding
    local clipboard_command='xclip -in -selection clipboard'
    local hook='exec "$HOME/.claude-logs/pipe-logger.sh" #{q:session_name} #I #P #{q:@terminal_router_log_key}'
    hook_for_binding=$(shell_quote "$hook")
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
    router_shell="${SHELL:-/bin/sh}"
    [ -x "$router_shell" ] || router_shell=/bin/sh
    router_command="printf '%s\\n' $(shell_quote "$CONNECTION_HINT"); exec $(shell_quote "$router_shell") -i"
    # In particular, ignore global logging hooks which would record the AI pane.
    left=$(tmux -S "$socket" -f /dev/null new-session -d -s "$session" -n router -x 160 -y 40 -P -F '#{pane_id}' "$router_command") || {
        rmdir "$state" 2>/dev/null || true
        die "could not create workspace."
    }
    # Include the engine's directory for node-based installations started from a menu.
    command="export PATH=$(shell_quote "${binary%/*}:$PATH"); exec python3"
    command+=" $(shell_quote "${INSTALLER%/*}/observer.py") $(shell_quote "$engine")"
    command+=" $(shell_quote "$binary") $(shell_quote "$state") $(shell_quote "$left")"
    if ! tmux -S "$socket" set-option -t "$session" mouse on ||
       ! tmux -S "$socket" unbind-key -T root MouseDown3Pane ||
       ! tmux -S "$socket" bind-key -T root MouseUp3Pane \
           display-menu -T '#[align=centre]#{@terminal_router_role}' -t = -x M -y M \
           'Copy word' w 'set-buffer "#{q:mouse_word}" ; run-shell -b "tmux save-buffer - | xclip -in -selection clipboard"' \
           'Copy line' l 'set-buffer "#{q:mouse_line}" ; run-shell -b "tmux save-buffer - | xclip -in -selection clipboard"' \
           '' 'Paste' p 'paste-buffer -p' \
           '' 'Zoom pane' z 'resize-pane -Z' ||
       ! tmux -S "$socket" bind-key -T copy-mode MouseDragEnd1Pane \
           send-keys -X copy-pipe-and-cancel "$clipboard_command" ||
       ! tmux -S "$socket" bind-key -T copy-mode-vi MouseDragEnd1Pane \
           send-keys -X copy-pipe-and-cancel "$clipboard_command" ||
       ! tmux -S "$socket" set-option -w -t "$left" pane-border-status top ||
       ! tmux -S "$socket" set-option -w -t "$left" pane-border-format ' #{@terminal_router_role} ' ||
       ! tmux -S "$socket" set-option -p -t "$left" @terminal_router_role router ||
       ! tmux -S "$socket" set-option -p -t "$left" @terminal_router_log_key "${state##*/}" ||
       ! tmux -S "$socket" set-option -p -t "$left" @terminal_router_config_blocked 0 ||
       ! tmux -S "$socket" pipe-pane -o -t "$left" "$hook" ||
       ! tmux -S "$socket" bind-key -n F9 "set-option -p -t $left @terminal_router_config_blocked 1; pipe-pane -t $left" ||
       ! tmux -S "$socket" bind-key -n F10 "set-option -p -t $left @terminal_router_config_blocked 0; pipe-pane -o -t $left $hook_for_binding" ||
       ! tmux -S "$socket" set-option -t "$session" status-right ' F9 pausa | F10 riprendi ' ||
       ! right=$(tmux -S "$socket" split-window -h -t "$left" -P -F '#{pane_id}' "$command") ||
       ! tmux -S "$socket" set-option -p -t "$right" @terminal_router_role assistant ||
       ! tmux -S "$socket" select-pane -t "$left"; then
        tmux -S "$socket" kill-server 2>/dev/null || true
        die "could not configure workspace; its tmux server was closed."
    fi
    echo "Router on the left; $engine observer on the right. Click a pane to switch."
    echo "Drag without Shift to copy one pane directly to the system clipboard."
    echo "Right-click opens the pane menu; Ctrl+b ] also pastes the tmux buffer."
    echo "Captured output is sent to your configured AI provider; normal account usage applies."
    echo "Detach: Ctrl+b d. Reattach: tmux -S $(shell_quote "$socket") attach"
    exec tmux -S "$socket" attach -t "$session"
}
