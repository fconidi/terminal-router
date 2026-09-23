# Shared per-user configuration; sourced by the CLI and installer.
MARK_BEGIN="# >>> claude-terminal-log >>>"
MARK_END="# <<< claude-terminal-log <<<"
SED_RANGE='/^# >>> claude-terminal-log >>>$/,/^# <<< claude-terminal-log <<<$/d'
LOGDIR="$HOME/.claude-logs"
RCFILE="$HOME/.bashrc"
[ "$(basename "${SHELL:-}")" = "zsh" ] && RCFILE="$HOME/.zshrc"

# Keep HOME literal: cron expands it inside quotes, including spaces and '%'.
ROTATION='0 3 * * * find "$HOME/.claude-logs" -maxdepth 1 -type f -name '\''tmux-*.log'\'' -mtime +30 -delete # terminal-router:rotation'
LEGACY_ROTATION="0 3 * * * find $LOGDIR -maxdepth 1 -name 'tmux-*.log' -mtime +30 -delete"

has_rotation() {
    grep -Fx -e "$ROTATION" -e "$LEGACY_ROTATION" >/dev/null
}

without_rotation() {
    grep -vxF -e "$ROTATION" -e "$LEGACY_ROTATION" || [ "$?" -eq 1 ]
}

# Refuse malformed/duplicate markers before a range edit can remove user data.
valid_block() {
    [ -f "$1" ] || return 0
    awk -v begin="$MARK_BEGIN" -v end="$MARK_END" '
        $0 == begin { if (opened || count++) bad=1; opened=1 }
        $0 == end { if (!opened) bad=1; opened=0 }
        END { exit (bad || opened) ? 1 : 0 }
    ' "$1"
}

update_block() {
    local file="$1" block="$2" tmp
    touch "$file"
    tmp=$(mktemp "${file}.terminal-router.XXXXXX") || return 1
    if grep -qxF "$MARK_BEGIN" "$file"; then
        # Insert in place so later user settings keep their precedence.
        TR_BLOCK="$block" awk -v begin="$MARK_BEGIN" -v end="$MARK_END" '
            $0 == begin { print ENVIRON["TR_BLOCK"]; inside=1; next }
            $0 == end { inside=0; next }
            !inside { print }
        ' "$file" > "$tmp"
    else
        cat "$file" > "$tmp"
        printf '\n%s\n' "$block" >> "$tmp"
    fi
    if cmp -s "$file" "$tmp"; then
        echo "SKIP  $file (up to date)"
    else
        # Back up contents, not a symlink that would point at the edited file.
        cp -aL --remove-destination "$file" "$file.terminal-router.bak"
        cat "$tmp" > "$file"
        echo "OK    $file updated (backup: $file.terminal-router.bak)"
    fi
    rm -f "$tmp"
}
