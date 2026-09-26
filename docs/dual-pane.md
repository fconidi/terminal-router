# Integrated router workspace

Opening `terminal-router` (also from the desktop entry) creates a private tmux
server with separate router and observer sessions, displayed in two independent
Terminator widgets on the left and right.
`terminal-router claude` / `terminal-router codex` select the engine explicitly;
automatic selection prefers Claude, then Codex. The existing `launch` command
continues to provide capture without AI; configuration remains in `menu`.

The observer reads only the router pane's stable log link. It automatically
analyses changed output, accepts questions, and never sends commands to a pane.
It groups updates, permits one AI request at a time, and makes no requests for
unchanged output. `:auto off`, `:auto on`, Enter (analyse now), and `:quit` control
the observer. `:auto off` cancels the active request and clears queued questions;
new questions typed afterwards still work. CLI errors remain visible; automatic requests stop after failure.
Pausing recording also prevents automatic analysis until recording resumes.
F9/F10 control the router pipe directly, including inside an SSH session.
Output is sent through the chosen, already-authenticated AI CLI; normal account
usage applies. Tests replace both engines and never use a real AI account.

The router pane shows a serial-console hint for `tio`. Use `tio --list` to find
the adapter, then connect with `tio --baudrate 9600 --databits 8 --parity none
--stopbits 1 --flow none /dev/ttyUSB0`; `/dev/ttyACM0` and
`/dev/serial/by-id/` are common alternatives. With tio defaults, `tio
/dev/ttyUSB0` is enough. Press `Ctrl-t q` to exit.

The observer selects the language from the system locale automatically and
supports English, Italian, French, German and Spanish. Unknown and `C` locales
use English. Override it with `TR_LANGUAGE=en|it|fr|de|es`; use
`TR_LANGUAGE=auto` to restore automatic selection.

Configuration mode is disabled by default. In the observer pane, use
`:config on`, then ask the AI to apply or type the commands. Every structured
proposal is validated and staged automatically. Review the complete ordered
group and enter the displayed `:confirm <code>` within 120 seconds; only then are
all commands sent to the router pane. New AI analyses wait while confirmation is
pending. A group contains at most 32 commands.
`:cancel` discards it, `:config off` disables the mode, and `:apply <command>`
remains a manual one-command fallback. Only `tio` or `ssh` may be the active
foreground transport; shell operators, control characters and newlines are
rejected. F9 also blocks sending while the router pane is paused.

Implementation: Bash launcher and existing per-user logger; Python standard
library for bounded log reads, terminal input, asynchronous CLI requests and
timeouts. No third-party Python dependencies. Engine subprocesses receive the
log snapshot through stdin, and their replies are displayed as text only.
No forced model; optional TR_CLAUDE_MODEL / TR_CODEX_MODEL overrides.

Acceptance: two side-by-side terminal widgets, focus initially on the router,
native selection and context menus confined to one widget, router capture
on/observer capture off, session isolation, stable logging across
pause/resume, no terminal input injection, clean handling of missing engines,
CLI failures and shutdown. Operator input must remain usable while AI runs.

Build: `bash build-deb.sh`
Tests: `python3 -m unittest discover -s tests -v`
Syntax: `bash -n build/usr/bin/terminal-router build/usr/share/terminal-router/*.sh`

Source conventions: quoted Bash arguments and explicit error checks; Python
subprocess argument lists, never shell interpolation or eval. Test real tmux
on private sockets and temporary HOME, stub only the AI and user crontab.

CLI options were checked against the installed help and official references:
[Codex CLI](https://developers.openai.com/codex/cli/reference/),
[Codex configuration](https://developers.openai.com/codex/config-reference/),
[Claude Code CLI](https://code.claude.com/docs/en/cli-reference).
