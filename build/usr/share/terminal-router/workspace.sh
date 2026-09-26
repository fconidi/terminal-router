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

CONNECTION_HINT='Serial console connection (recommended: tio):
  tio --list
  tio --baudrate 9600 --databits 8 --parity none --stopbits 1 --flow none /dev/ttyUSB0

Alternative terminal programs (if installed):
  screen /dev/ttyUSB0 9600
  picocom --baud 9600 --databits 8 --parity n --stopbits 1 --flow n /dev/ttyUSB0

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
    local engine="${1:-}" binary state socket router_session assistant_session left right command
    local router_command router_shell hook_for_binding router_client assistant_client layout
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
    command -v terminator >/dev/null || die "terminator is required for independent router and assistant terminals."
    ensure_consent || return 1
    bash "$INSTALLER" logdir-only || return $?
    state=$(mktemp -d "$LOGDIR/workspace-XXXXXXXX") || return 1
    socket="$state/tmux.sock"
    router_session="router-${state##*workspace-}"
    assistant_session="assistant-${state##*workspace-}"
    router_shell="${SHELL:-/bin/sh}"
    [ -x "$router_shell" ] || router_shell=/bin/sh
    router_command="printf '%s\\n' $(shell_quote "$CONNECTION_HINT"); exec $(shell_quote "$router_shell") -i"
    # In particular, ignore global logging hooks which would record the AI pane.
    left=$(tmux -S "$socket" -f /dev/null new-session -d -s "$router_session" -n router -x 96 -y 40 -P -F '#{pane_id}' "$router_command") || {
        rmdir "$state" 2>/dev/null || true
        die "could not create workspace."
    }
    # Include the engine's directory for node-based installations started from a menu.
    command="export PATH=$(shell_quote "${binary%/*}:$PATH"); exec python3"
    command+=" $(shell_quote "${INSTALLER%/*}/observer.py") $(shell_quote "$engine")"
    command+=" $(shell_quote "$binary") $(shell_quote "$state") $(shell_quote "$left")"
    if ! tmux -S "$socket" set-option -t "$router_session" mouse off ||
       ! tmux -S "$socket" set-option -t "$router_session" status-left ' router ' ||
       ! tmux -S "$socket" set-option -p -t "$left" @terminal_router_role router ||
       ! tmux -S "$socket" set-option -p -t "$left" @terminal_router_log_key "${state##*/}" ||
       ! tmux -S "$socket" set-option -p -t "$left" @terminal_router_config_blocked 0 ||
       ! tmux -S "$socket" pipe-pane -o -t "$left" "$hook" ||
       ! tmux -S "$socket" bind-key -n F9 "set-option -p -t $left @terminal_router_config_blocked 1; pipe-pane -t $left" ||
       ! tmux -S "$socket" bind-key -n F10 "set-option -p -t $left @terminal_router_config_blocked 0; pipe-pane -o -t $left $hook_for_binding" ||
       ! tmux -S "$socket" set-option -t "$router_session" status-right ' F9 pause | F10 resume ' ||
       ! tmux -S "$socket" set-option -g history-limit 50000 ||
       ! right=$(tmux -S "$socket" new-session -d -s "$assistant_session" -n assistant -x 72 -y 40 -P -F '#{pane_id}' "$command") ||
       ! tmux -S "$socket" set-option -t "$assistant_session" mouse on ||
       ! tmux -S "$socket" unbind-key -T root MouseDown3Pane ||
       ! tmux -S "$socket" bind-key -T root MouseUp3Pane \
           display-menu -T '#[align=centre]assistant' -t = -x M -y M \
           'History top' '<' 'copy-mode ; send-keys -X history-top' \
           'History bottom' '>' 'copy-mode ; send-keys -X history-bottom' ||
       ! tmux -S "$socket" set-option -t "$assistant_session" status-left " $engine " ||
       ! tmux -S "$socket" set-option -t "$assistant_session" status-right ' Wheel: scroll | Shift: select | F9 pause | F10 resume ' ||
       ! tmux -S "$socket" set-option -p -t "$right" @terminal_router_role assistant; then
        tmux -S "$socket" kill-server 2>/dev/null || true
        die "could not configure workspace; its tmux server was closed."
    fi
    router_client="$state/router-client.sh"
    assistant_client="$state/assistant-client.sh"
    layout="$state/terminator-layout.json"
    {
        echo '#!/bin/sh'
        printf 'exec tmux -S %s attach -t %s\n' "$(shell_quote "$socket")" "$(shell_quote "$router_session")"
    } > "$router_client"
    {
        echo '#!/bin/sh'
        printf 'exec tmux -S %s attach -t %s\n' "$(shell_quote "$socket")" "$(shell_quote "$assistant_session")"
    } > "$assistant_client"
    chmod 700 "$router_client" "$assistant_client" || {
        tmux -S "$socket" kill-server 2>/dev/null || true
        die "could not prepare workspace clients."
    }
    python3 - "$layout" "$router_client" "$assistant_client" <<'PY' || {
import json
import sys

layout_path, router_client, assistant_client = sys.argv[1:]
layout = {
    "layout": {
        "vertical": False,
        "terminal-router": [
            {"command": router_client, "title": "router", "ratio": 0.58},
            {"command": assistant_client, "title": "assistant"},
        ],
    }
}
with open(layout_path, "w", encoding="utf-8") as output:
    json.dump(layout, output)
PY
        tmux -S "$socket" kill-server 2>/dev/null || true
        die "could not prepare the Terminator layout."
    }
    chmod 600 "$layout" || {
        tmux -S "$socket" kill-server 2>/dev/null || true
        die "could not protect the Terminator layout."
    }
    echo "Router and $engine observer use independent Terminator widgets."
    echo "Router: select normally. Assistant: wheel scrolls history; hold Shift to select."
    echo "Selection cannot cross the divider."
    echo "Captured output is sent to your configured AI provider; normal account usage applies."
    exec terminator --no-dbus --maximise --title 'Terminal Router' --config-json "$layout"
}
