# Implementation plan

1. Verify Noble's GI bindings and VTE, define the trust model, and prove native asynchronous PTY spawning.
2. Add the GTK application, windows, notebook tabs, recursive splits, focus, and session-preserving moves.
3. Enforce validation and private storage, review native paste and PTY disposal paths, and add defensive tests.
4. Implement workspace and profile management, one-time command consent, search, and shortcut customization.
5. Refine GTK styling, accessibility, settings, error reporting, and desktop integration.
6. Run unit and live GTK tests, capture a real screenshot, measure startup and idle usage, and record coverage and release gaps.
7. Build and inspect the Debian package and record its SHA-256 checksum. Installation and removal require a suitable isolated environment or explicit authorization.

## Decisions

- Gtk.Notebook owns tab selection and drag reordering. Gtk.Paned owns split geometry. The binary tree retains existing widget identity for moves and maximization.
- One versioned JSON catalog uses a locked read-modify-write transaction and atomic replacement. Names are dictionary keys, never paths.
- Workspace snapshots keep configuration only. Imported profiles are replaced by Default Shell and imported startup commands are stripped.
- Run reviewed startup commands in their assigned PTYs via the configured shell's command mode. Ordinary panes start interactive shells. Authorization lasts for a single opening.
- VTE provides job control and PTY sizing. Closing uses PTY disposal and VTE child reaping, never a signal sent to a remembered PID.

## Status

All seven stages produced a working implementation in this repository. The package and checksum are in `dist/`. The [test record](TESTING.md) lists measured results and the remaining manual release checks.
