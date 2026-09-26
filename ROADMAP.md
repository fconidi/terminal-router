# Next ideas

The 1.1.0 release delivered the integrated Claude/Codex workspace, guarded
configuration, multilingual output, isolated terminal widgets, pane-level
controls, safer capture and repeatable regression tests. The following are
proposals beyond that release.

1. **Choose a pane to follow.** Add `logs` and `tail --pane` so opening a
   second pane does not move the assistant away from the router being examined.
   Use stable tmux pane IDs and expose paused/exited states. Acceptance: two
   simultaneous router sessions can be followed independently through resumes.

2. **Disk budget and retention settings.** Offer a configurable age and size
   limit, plus `prune --dry-run`. Identify active logs before removal and show
   exactly what would be deleted. Acceptance: active capture survives pruning
   and the dry run leaves every file unchanged.

3. **Readable exports for assistants.** Produce a separate plain-text export
   that handles ANSI escapes, carriage returns and terminal backspaces while
   preserving the original recording. Optional secret masking needs explicit
   rules and a preview; it must not promise to recognize every credential.
   Acceptance: test realistic Cisco/Huawei output and fragmented escape codes.

4. **Recording indicator.** An opt-in tmux status indicator could distinguish
   recording, paused and unavailable logger states without replacing the
   user's status configuration. Acceptance: pause/resume updates the indicator,
   and removing the feature restores the original settings.

Known limits: cron edits still have an external read/write race if another
program changes the user's crontab simultaneously. A pipe reported as open by
tmux is not an end-to-end disk health check. Automated tests currently exercise
Bash and tmux 3.5a; interactive Zsh startup and older supported tmux versions
need a compatibility matrix before a wider release.
