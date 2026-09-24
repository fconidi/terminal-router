# Integrated router workspace

Opening `terminal-router` (also from the desktop entry) creates a private tmux
server with a router shell on the left and an AI observer on the right.
`terminal-router claude` / `terminal-router codex` select the engine explicitly;
automatic selection prefers Claude, then Codex. The existing `launch` command
continues to provide capture without AI; configuration remains in `menu`.

The observer reads only the left pane's stable log link. It automatically
analyses changed output, accepts questions, and never sends commands to a pane.
It groups updates, permits one AI request at a time, and makes no requests for
unchanged output. `:auto off`, `:auto on`, Enter (analyse now), and `:quit` control
the observer. CLI errors remain visible; automatic requests stop after failure.
Pausing recording also prevents automatic analysis until recording resumes.
F9/F10 control the router pipe directly, including inside an SSH session.
Output is sent through the chosen, already-authenticated AI CLI; normal account
usage applies. Tests replace both engines and never use a real AI account.

Implementation: Bash launcher and existing per-user logger; Python standard
library for bounded log reads, terminal input, asynchronous CLI requests and
timeouts. No third-party Python dependencies. Engine subprocesses receive the
log snapshot through stdin, and their replies are displayed as text only.
No forced model; optional TR_CLAUDE_MODEL / TR_CODEX_MODEL overrides.

Acceptance: two horizontal panes, focus initially left, mouse switching,
left capture on/right capture off, session isolation, stable logging across
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
