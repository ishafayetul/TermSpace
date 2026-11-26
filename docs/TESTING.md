# Testing and release evidence

## Tests

Run portable validation and storage checks with `/usr/bin/python3 -m unittest discover -s tests -p test_model.py -v`. Run the full suite on an isolated GTK display. The GTK suite sends test input to that display and temporarily owns its clipboard.

```bash
TERMSPACE_TEST_XEVENTS=1 xvfb-run -a /usr/bin/python3 -m unittest discover -s tests -v
GDK_BACKEND=wayland /usr/bin/python3 -m unittest discover -s tests -v
```

For Wayland, launch the second command from an isolated Wayland session or set `WAYLAND_DISPLAY` to the socket of a test compositor. Set `TERMSPACE_TEST_XEVENTS=1` only on the isolated X11 display to exercise the XTest keyboard and middle-click paths. These native X11 inputs use the system X11 and XTest libraries. Missing GTK/VTE or a test display skips native cases.

### Recorded on Ubuntu 24.04.5 x86-64

| Check | Result |
| --- | --- |
| Python, PyGObject, GTK and VTE | 3.12.3, 3.48.2, 4.14.5 and 0.76.0 (Ubuntu VTE revision 0.76.0-1ubuntu0.1) |
| X11, Xvfb | 25 tests passed, with synthetic Shift+Insert, Ctrl+Shift+Insert, Ctrl+Shift+V and middle-click |
| Wayland, headless GNOME Shell | 25 tests passed, with VTE paste-signal review, native shells, sizing and OSC 52 query coverage |
| CLI routing | The running instance opened a second window for a relative directory containing spaces. A missing workspace returned status 2. |
| Interactive software | Bash completion and job signals, Nano and Htop, terminal Unicode output in Japanese and Bengali |
| Native tool invocation | Git and Python versions, OpenSSH and Docker version commands, ROS 2 help |
| Stress and cleanup | 16 distinct live PTYs, 12 rapid tab openings/closings, 12,000 lines of output, closed children reaped and an unrelated process survived |
| Security regression | Bounded JSON, import trust stripping, startup command consent, shell metacharacters as data, paste review, plain-text titles, blocked URI schemes, owner-only storage, symlink and overwrite defenses, root launch refusal, OSC 52 query suppression |
| OSC 52 clipboard ownership | X11 retained its original clipboard data. The Wayland headless seat can revoke selection ownership on focus changes. It showed no replacement provider, and the PTY received no query response. |
| Network trace | An isolated Wayland startup and idle shell produced local Unix-socket traffic, with zero IPv4/IPv6 socket operations and zero listen calls |
| Debian package | Installed and removed with apt in a disposable Ubuntu 24.04 container. Confirmed dependency resolution, launcher version, GI imports, desktop files, and preservation of a configuration fixture. The packaged launcher also opened a native X11 window and started Bash. SHA-256 and desktop-file checks passed. |
| Secret and archive checks | The staged source passed the Ubuntu Gitleaks scanner. The Debian archive contained no maintainer scripts or privileged file modes. |

GTK 4.14 emits deprecation notices for some stable GTK APIs used by the source. VTE 0.76's GTK4 `set_pty(None)` path crashed during development. The implementation disposes the unparented widget through GObject. Live tests verify that VTE reaps its managed children using that path.

## Measurements

Xvfb with the Cairo renderer. Startup runs from the benchmark's Python entry point until Bash prints a readiness marker in every pane. CPU is TermSpace process time over a two-second idle interval. Memory is the application process's `smaps_rollup`, excluding child shells. PSS apportions shared pages.

| Panes | Startup | Idle CPU, one core | RSS | PSS |
| --- | ---: | ---: | ---: | ---: |
| 1, median of five | 237 ms | 0.09% | 172.9 MiB | 76.1 MiB |
| 16, one run | 462 ms | 0.24% | 184.2 MiB | 87.4 MiB |

The one-pane RSS exceeded the preferred 100 MB target in this fixture. Startup met the two-second target. Real compositor and renderer configurations can change memory use.

```bash
/usr/bin/python3 -m tests.benchmark_native 1
/usr/bin/python3 -m tests.benchmark_native 16
```

## Remaining manual checks

- Verify desktop menu discovery and package-manager integration on a full Ubuntu desktop installation.
- Exercise physical drag-and-drop, HiDPI and accessibility, Japanese/Bengali input methods, and desktop-wide clipboard transfer on GNOME Wayland and X11.
- Exercise live SSH, Docker, database and ROS sessions against dedicated test services, plus Zsh, Fish, Vim and tmux if installed.
- Repeat multi-window and resize workloads over a longer run and record memory and CPU on the intended hardware.
- To verify browser confirmation manually, enable links and Ctrl+click a synthetic HTTPS OSC 8 link on a test display. Check the exact destination is shown, and cancel the launch. Repeat with the setting off and with a non-HTTP scheme.
