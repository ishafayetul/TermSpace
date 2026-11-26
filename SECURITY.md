# Security and threat model

TermSpace is a native terminal emulator. It is not a sandbox. Commands run with the shell user's permissions. The user's shell configuration, local applications, desktop session, kernel, and Ubuntu dependencies are part of the trusted computing base.

| Boundary | Threat | Control |
| --- | --- | --- |
| CLI and local paths | Option and command injection | Only local launch operations, validated directories, absolute executable paths and structured argv |
| Terminal and SSH output | Malicious titles, window manipulation, clipboard access or link activation | VTE parser, sanitized plain text, no window-control callbacks, OSC 52 regression checks, hyperlinks off by default |
| Clipboard | Invisible controls or pasted lines execute commands | Capture terminal paste routes, preview escaped controls, user choice, native bracketed paste |
| Imported workspaces | Code, environment or trust injection and resource exhaustion | Bounded strict JSON, validated layout, default shell substitution, command stripping and import review |
| Imported themes | Executable configuration, remote resources and unsafe file paths | Bounded, versioned JSON allowlist, validated colors and font names, descriptor-relative paths with no symlink components |
| Local settings | Symlink substitution, corruption and concurrent lost updates | Descriptor-relative storage, ownership and mode checks, exclusive lock, atomic replacement |
| Profiles | Executable, arguments and environment can change process behavior | Local profile edits require review, imports cannot select custom profiles, validate override names, keep secrets out |
| Startup commands | Unintended execution | One-time consent shows exact text, pane and working directory, skip by default and on CLI launch |
| Process lifecycle | Terminating unrelated processes | VTE-owned child watch and PTY closure, conservative close confirmation, no PID-based termination |
| Privilege and network | Unexpected elevation or data disclosure | Refuse root GUI, no application server, telemetry, credential collection or updater |
| Supply chain | Vulnerable or compromised libraries | Use Ubuntu packages and its standard security updates |

Detached jobs can outlive their terminal. A same-user attacker, hostile shell startup files or a compromised desktop can bypass application controls. A working directory can influence shell hooks and developer tools. Only import workspaces from sources you are willing to review. Clipboard contents, terminal output, commands, and environment values are not written to diagnostics. Explicit configuration and exported workspaces can contain private paths and authored commands.

## Updates and reporting

The supported release is TermSpace 1.1.0 on Ubuntu 24.04 LTS. Use Ubuntu's security updates for Python, GTK, PyGObject, and VTE, and install TermSpace updates from [GitHub Releases](https://github.com/ishafayetul/TermSpace/releases). The Debian package requires at least VTE `0.76.0-1ubuntu0.1`, the Noble build containing the window-handling fix in [USN-6833-1](https://ubuntu.com/security/notices/USN-6833-1).

Use the private reporting option on the [GitHub Security page](https://github.com/ishafayetul/TermSpace/security/advisories) when available. Otherwise, open a [GitHub issue](https://github.com/ishafayetul/TermSpace/issues) asking for a private reporting channel and omit vulnerability details from it. In a private report, include TermSpace, Ubuntu, GTK and VTE versions, the impact, and steps using synthetic data. Keep shell history, credentials, and private workspace files out of reports.

## Verified baseline

Noble's VTE 0.76.0 maintains the terminal escape parser. The upstream OSC 52 handler is a no-op for X selection operations, and the development runtime passed the PTY query and X11 write regression checks. Recheck new VTE versions before widening platform support. See the [upstream handler](https://github.com/GNOME/vte/blob/0.76.0/src/vteseq.cc) and the [test record](docs/TESTING.md).

Private application paths reject symlink components. Local configurations and shell profiles can influence behavior by design. Keep credentials out of environment overrides and startup scripts, and treat explicitly exported JSON as private if it contains sensitive details. The UI displays startup scripts for one-time consent and supplies them to the configured shell as command arguments.
