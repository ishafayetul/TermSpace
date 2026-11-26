# Contributing to TermSpace

## Develop on Ubuntu 24.04

Install the dependencies in [README.md](README.md), then run the app with `scripts/run_dev.sh`. Use `/usr/bin/python3` for compatibility with Ubuntu's PyGObject bindings. See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for the code layout and [TESTING.md](docs/TESTING.md) for the X11 and Wayland test procedure.

Keep changes focused. Use the existing VTE interfaces for shell I/O, job control and PTY sizing. When a change affects clipboard input, workspace data or child processes, add a focused regression test using synthetic fixture data.

## Test and build

```bash
scripts/check_dependencies.sh
/usr/bin/python3 -m unittest discover -s tests -v
scripts/build_deb.sh
```

Run native tests on an isolated display. The tests deliberately take ownership of its clipboard and, optionally, synthesize X11 input. Tests and packaging run without system installation.

## Report an issue

Include the TermSpace version, Ubuntu version, display backend, and a minimal reproduction. **Settings → Privacy → View diagnostics** shows the toolkit and display versions. Redact private paths and terminal contents before attaching screenshots or workspaces. For security vulnerabilities, follow [SECURITY.md](SECURITY.md).
