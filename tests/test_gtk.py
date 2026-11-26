"""Native GTK and real PTY integration tests. Use an isolated test display."""

import ctypes
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from termspace import model, themes
from termspace.__main__ import parser
from termspace.store import Store

try:
    from termspace.application import Application
    from termspace.layout import panes
    from termspace.native import Gdk, GLib, Gtk, Pango, Vte
    from termspace.preferences import accelerator_map
    from termspace.terminal import Session
    Gtk.init_check()
    NATIVE = Gdk.Display.get_default() is not None
except (ImportError, ValueError):
    NATIVE = False


def until(check, timeout=5):
    context = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if check():
            return
        time.sleep(.007)
    raise AssertionError("GTK condition timed out")


def output(pane):
    return pane.session.terminal.get_text_format(Vte.Format.TEXT) or ""


def send(pane, text):
    pane.session.terminal.feed_child(text.encode())


def dialogs(window, title=None):
    return [item for item in Gtk.Window.list_toplevels()
            if isinstance(item, Gtk.Dialog) and item.get_transient_for() is window
            and item.get_visible() and (title is None or item.get_title() == title)]


def xevents(window, *, keys=(), click=None, drag=None):
    """Emit synthetic keyboard/mouse events on an isolated X11 test display."""
    x11 = ctypes.CDLL("libX11.so.6")
    xtst = ctypes.CDLL("libXtst.so.6")
    ptr, number, boolean, delay = ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong
    for library, name, args, result in (
        (x11, "XOpenDisplay", [ctypes.c_char_p], ptr),
        (x11, "XCloseDisplay", [ptr], boolean),
        (x11, "XSetInputFocus", [ptr, delay, boolean, delay], boolean),
        (x11, "XDefaultRootWindow", [ptr], delay),
        (x11, "XTranslateCoordinates", [ptr, delay, delay, boolean, boolean,
                                       ctypes.POINTER(boolean), ctypes.POINTER(boolean),
                                       ctypes.POINTER(delay)], boolean),
        (x11, "XKeysymToKeycode", [ptr, delay], ctypes.c_ubyte),
        (x11, "XSync", [ptr, boolean], boolean),
        (xtst, "XTestFakeKeyEvent", [ptr, number, boolean, delay], boolean),
        (xtst, "XTestFakeMotionEvent", [ptr, boolean, boolean, boolean, delay], boolean),
        (xtst, "XTestFakeButtonEvent", [ptr, number, boolean, delay], boolean),
    ):
        function = getattr(library, name)
        function.argtypes, function.restype = args, result
    display = x11.XOpenDisplay(None)
    assert display
    try:
        xid = window.get_surface().get_xid()
        x11.XSetInputFocus(display, xid, 1, 0)
        for key in keys:
            code = x11.XKeysymToKeycode(display, key)
            assert code, f"No X11 keycode for {key}"
            xtst.XTestFakeKeyEvent(display, code, True, 0)
        if click or drag:
            x, y, button = click if click else (*drag[:2], 1)
            root_x, root_y, child = boolean(), boolean(), delay()
            x11.XTranslateCoordinates(display, xid, x11.XDefaultRootWindow(display), x, y,
                                       ctypes.byref(root_x), ctypes.byref(root_y), ctypes.byref(child))
            xtst.XTestFakeMotionEvent(display, -1, root_x.value, root_y.value, 0)
            xtst.XTestFakeButtonEvent(display, button, True, 0)
            if drag:
                xtst.XTestFakeMotionEvent(display, -1, root_x.value + drag[2], root_y.value + drag[3], 0)
            xtst.XTestFakeButtonEvent(display, button, False, 0)
        for key in reversed(keys):
            xtst.XTestFakeKeyEvent(display, x11.XKeysymToKeycode(display, key), False, 0)
        x11.XSync(display, False)
    finally:
        x11.XCloseDisplay(display)


@unittest.skipUnless(NATIVE, "GTK/VTE and a test display are required")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.base = Path(cls.tmp.name)
        cls.stack = patch("termspace.model.login_shell", return_value="/bin/bash")
        cls.stack.start()
        cls.addClassCleanup(cls.stack.stop)
        cls.app = Application(parser().parse_args, config=Store(cls.base / "config"),
                              state=Store(cls.base / "state"), non_unique=True)
        cls.app.register()

    def setUp(self):
        data = {"schema_version": 1, "settings": model.settings({}),
                "workspaces": {}, "profiles": {"Test Bash": model.PROFILE | {
                    "shell": "/bin/bash", "arguments": ["--noprofile", "--norc"],
                    "environment": {"HISTFILE": "/dev/null", "PS1": "test$ ", "PROMPT_COMMAND": ""},
                }}}
        data["settings"]["default_profile"] = "Test Bash"
        self.app.config.update(lambda _: data)
        self.app.load_catalog(data)
        self.app.apply_theme()
        self.window = self.app.build_window(cwd=str(self.base))
        self.tab = self.window.current()
        self.pane = self.tab.active
        until(lambda: self.pane.session.state == "running")
        until(lambda: self.window.get_mapped())

    def tearDown(self):
        for window in self.app.windows():
            for dialog in dialogs(window):
                dialog.destroy()
            window.dispose_sessions()
            window.destroy()
        until(lambda: not self.app.windows())

    def test_01_shell_pty_unicode_resize_search_and_job_control(self):
        send(self.pane, 'echo "Hello TermSpace"; pwd; ls -d .; printenv TERM; '
             'python3 --version; git --version; printf "\\033[32m日本語 বাংলা\\033[0m\\n"; '
             'printf "MARK"; printf "ER\\n"; stty size\n')
        until(lambda: "MARKER" in output(self.pane))
        text = output(self.pane)
        self.assertIn(str(self.base), text)
        self.assertIn("xterm-256color", text)
        self.assertIn("Python 3.12", text)
        self.assertIn("git version", text)
        self.assertIn("日本語 বাংলা", text)
        session = self.pane.session
        session.search("MARKER", True, False)
        self.assertTrue(session.terminal.search_find_next())
        session.search("MARK.R", True, True)
        self.assertTrue(session.terminal.search_find_next())
        with self.assertRaises(model.Invalid):
            session.search("(a+)+$", True, True)
        before = (session.terminal.get_row_count(), session.terminal.get_column_count())
        self.window.set_default_size(900, 515)
        until(lambda: (session.terminal.get_row_count(), session.terminal.get_column_count()) != before)
        send(self.pane, "stty size\n")
        until(lambda: f"{session.terminal.get_row_count()} {session.terminal.get_column_count()}\n" in output(self.pane))
        send(self.pane, "sleep 20\n")
        time.sleep(.15)
        send(self.pane, "\x1a")
        until(lambda: "Stopped" in output(self.pane))
        send(self.pane, "fg\n")
        time.sleep(.15)
        send(self.pane, "\x03")
        send(self.pane, "printf 'SIGNAL%s\\n' '_OK'\n")
        until(lambda: "SIGNAL_OK" in output(self.pane))

    def test_02_splits_moves_renaming_and_close(self):
        self.pane.update_field("name", "Build")
        self.tab.data["name"] = "Manual tab"
        self.tab.refresh()
        original = self.pane.session.pid
        self.tab.split(self.pane, "left-right")
        sibling = self.tab.active
        self.tab.split(sibling, "top-bottom")
        nested = self.tab.active
        until(lambda: all(pane.session.state == "running" for pane in panes(self.tab.tree)))
        self.assertEqual(len({pane.session.pid for pane in panes(self.tab.tree)}), 3)
        self.tab.maximize(nested)
        self.assertEqual(self.tab.page.get_first_child(), nested.box)
        self.tab.maximize(nested)
        self.assertIn(sibling, list(panes(self.tab.tree)))
        self.tab.swap(self.pane, nested)
        self.assertIs(list(panes(self.tab.tree))[-1], self.pane)
        self.assertEqual(self.pane.session.pid, original)
        self.assertEqual(self.tab.heading.get_text(), "Manual tab")
        self.assertEqual(self.pane.heading.get_text(), "Build")
        source = self.window
        other = source.add_tab()
        source.notebook.reorder_child(other.page, 0)
        self.assertIs(source.tabs[0], other)
        self.app.move_tab(self.tab)
        self.assertIsNot(self.tab.window, source)
        self.assertEqual(self.pane.session.pid, original)
        self.tab.window.close_pane(nested)
        until(lambda: bool(dialogs(self.tab.window, "Close terminal sessions?")))
        dialogs(self.tab.window, "Close terminal sessions?")[0].response(1)
        self.assertNotIn(nested, list(panes(self.tab.tree)))
        self.assertEqual(self.pane.session.pid, original)

    def test_03_workspace_review_and_roundtrip(self):
        path = self.base / "space ; ' metachar"
        path.mkdir(exist_ok=True)
        marker = path / "authorized"
        self.pane.data["working_directory"] = str(path)
        self.pane.session.cwd = str(path)
        self.pane.data["startup_commands"] = ["printf OK > authorized"]
        self.tab.split(self.pane, "left-right")
        until(lambda: self.tab.tree.widget.get_width() > 0)
        self.tab.tree.widget.set_position(round(self.tab.tree.widget.get_width() * .38))
        until(lambda: self.tab.tree.widget.get_position() / self.tab.tree.widget.get_width() < .46)
        snapshot = self.window.snapshot("Reviewed")
        ratio = snapshot["tabs"][0]["layout"]["ratio"]
        self.assertNotEqual(ratio, .5)
        snapshot["tabs"][0]["layout"]["children"][0]["working_directory"] = str(path)
        self.app.put_workspace(snapshot)
        self.app.load_workspace("Reviewed", None, review=False)
        self.assertFalse(marker.exists())
        self.app.load_workspace("Reviewed", self.window, review=True)
        until(lambda: bool(dialogs(self.window, "Review workspace startup commands")))
        self.assertFalse(marker.exists())
        dialogs(self.window, "Review workspace startup commands")[0].response(2)
        self.assertFalse(marker.exists())
        self.app.load_workspace("Reviewed", self.window, review=True)
        dialogs(self.window, "Review workspace startup commands")[0].response(1)
        until(marker.exists)
        self.assertEqual(marker.read_text(), "OK")
        self.assertEqual(len(self.app.windows()), 4)
        restored = self.app.windows()[0].current()
        until(lambda: restored.tree.widget.get_property("position-set") and restored.tree.widget.get_width() > 0)
        self.assertAlmostEqual(restored.snapshot()["layout"]["ratio"], ratio, delta=.05)
        self.assertEqual(self.app.catalog["workspaces"]["Reviewed"]["tabs"][0]["layout"]["type"], "split")

    def test_04_osc_titles_window_requests_and_clipboard(self):
        terminal = self.pane.session.terminal
        clipboard = terminal.get_clipboard()
        display = self.window.get_display().__gtype__.name
        if "X11" in display:
            until(self.window.is_active)
        clipboard.set("termspace-original")
        provider = clipboard.get_content()
        self.assertIsNotNone(provider)
        terminal.feed(b"\x1b]52;c;Y2hhbmdlZA==\x07\x1b]52;c;?\x07"
                      b"\x1b]0;Display <b>plain</b>\xe2\x80\xae\x07"
                      b"\x1b[3;5;5t\x1b[4;400;300t\x1b[8;8;8t\x1b[9;1t")
        until(lambda: "Display <b>plain</b>" in self.pane.heading.get_text())
        self.assertNotIn("\u202e", self.pane.heading.get_text())
        self.assertFalse(self.window.is_maximized())
        self.assertEqual(self.window.get_title(), "TermSpace")
        self.assertFalse(terminal.get_allow_hyperlink())
        if "X11" in display:
            self.assertEqual(clipboard.get_content(), provider)
            result = []
            clipboard.read_text_async(None, lambda source, pending: result.append(source.read_text_finish(pending)))
            until(lambda: bool(result))
            self.assertEqual(result, ["termspace-original"])
        else:
            # A headless Wayland seat can revoke clipboard ownership when focus changes.
            self.assertIn(clipboard.get_content(), (None, provider))

        script = ('import os, select, termios, tty; fd = 0; old = termios.tcgetattr(fd); '
                  'tty.setraw(fd); os.write(1, b"\\033]52;c;?\\007"); '
                  'reply = os.read(fd, 4096) if select.select([fd], [], [], .35)[0] else b""; '
                  'termios.tcsetattr(fd, termios.TCSANOW, old); '
                  'print("QUERY" + ("_REPLIED" if reply else "_IGNORED"))')
        import shlex
        send(self.pane, "/usr/bin/python3 -c " + shlex.quote(script) + "\n")
        until(lambda: "QUERY_IGNORED" in output(self.pane))

    def test_05_clipboard_through_native_action_and_keyboard(self):
        terminal = self.pane.session.terminal
        clipboard = terminal.get_clipboard()
        clipboard.set("printf 'PASTE%s\\n' '_OK'\n")
        terminal.emit("paste-clipboard")
        until(lambda: bool(dialogs(self.window, "Review clipboard text")))
        dialog = dialogs(self.window, "Review clipboard text")[0]
        self.assertNotIn("PASTE_OK", output(self.pane))
        dialog.response(2)
        time.sleep(.1)
        self.assertNotIn("PASTE_OK", output(self.pane))
        send(self.pane, "\n")
        until(lambda: "PASTE_OK" in output(self.pane))
        if "X11" not in self.window.get_display().__gtype__.name or not os.environ.get("TERMSPACE_TEST_XEVENTS"):
            return
        terminal.get_primary_clipboard().set("printf 'PRIMARY%s\\n' '_BAD'\r\n")
        self.tab.focus()
        xevents(self.window, keys=(Gdk.KEY_Shift_L, Gdk.KEY_Insert))
        until(lambda: bool(dialogs(self.window, "Review clipboard text")))
        dialogs(self.window, "Review clipboard text")[0].response(Gtk.ResponseType.CANCEL)
        clipboard.set("printf 'STANDARD%s\\n' '_BAD'\n")
        self.tab.focus()
        xevents(self.window, keys=(Gdk.KEY_Control_L, Gdk.KEY_Shift_L, Gdk.KEY_v))
        until(lambda: bool(dialogs(self.window, "Review clipboard text")))
        dialogs(self.window, "Review clipboard text")[0].response(Gtk.ResponseType.CANCEL)
        self.tab.focus()
        xevents(self.window, keys=(Gdk.KEY_Control_L, Gdk.KEY_Shift_L, Gdk.KEY_Insert))
        until(lambda: bool(dialogs(self.window, "Review clipboard text")))
        dialogs(self.window, "Review clipboard text")[0].response(Gtk.ResponseType.CANCEL)
        self.tab.focus()
        valid, bounds = terminal.compute_bounds(self.window)
        self.assertTrue(valid)
        xevents(self.window, click=(int(bounds.get_x() + bounds.get_width() / 2),
                                    int(bounds.get_y() + bounds.get_height() / 2), 2))
        until(lambda: bool(dialogs(self.window, "Review clipboard text")))
        dialogs(self.window, "Review clipboard text")[0].response(Gtk.ResponseType.CANCEL)
        self.assertNotIn("PRIMARY_BAD", output(self.pane))
        self.assertNotIn("STANDARD_BAD", output(self.pane))

    def test_06_resource_lifecycle_and_16_panes(self):
        unrelated = subprocess.Popen(["/bin/sleep", "10"])
        self.addCleanup(unrelated.wait, timeout=5)
        self.addCleanup(unrelated.terminate)
        before = len(os.listdir("/proc/self/fd"))
        generation = [self.pane]
        for _ in range(4):
            next_generation = []
            for pane in generation:
                self.tab.split(pane, "left-right" if _ % 2 == 0 else "top-bottom")
                next_generation.extend([pane, self.tab.active])
            generation = next_generation
        self.assertEqual(len(list(panes(self.tab.tree))), 16)
        until(lambda: all(pane.session.state == "running" for pane in generation))
        pids = [pane.session.pid for pane in generation]
        self.assertEqual(len(set(pids)), 16)
        for pane in generation:
            send(pane, "printf 'PANE%s\\n' '_OK'\n")
        until(lambda: all("PANE_OK" in output(pane) for pane in generation))
        self.pane.session.pid = unrelated.pid
        self.window.request_close(self.window)
        dialogs(self.window, "Close terminal sessions?")[0].response(1)
        until(lambda: all(not Path(f"/proc/{pid}").exists() for pid in pids))
        self.assertIsNone(unrelated.poll())
        self.assertLessEqual(len(os.listdir("/proc/self/fd")), before + 4)

    def test_07_failed_shell_and_rapid_close(self):
        executable = self.base / "invalid-shell"
        executable.write_text("#!/definitely-not-a-shell\n")
        executable.chmod(0o700)
        profile = model.PROFILE | {"shell": str(executable)}
        session = Session(model.leaf(str(self.base)), profile, self.app.settings, lambda: None, lambda *_: None)
        until(lambda: session.state in ("failed", "exited"))
        session.close()
        self.app.settings["confirm_close"] = False
        for _ in range(12):
            tab = self.window.add_tab()
            self.window.close_tabs([tab])
        until(lambda: len(self.window.tabs) == 1)
        self.assertEqual(self.pane.session.state, "running")

    def test_08_preferences_shortcuts_and_theme(self):
        self.assertEqual(len(accelerator_map(model.SHORTCUTS)), len(model.SHORTCUTS))
        with self.assertRaises(model.Invalid):
            accelerator_map({"new-tab": "<Ctrl>d"})
        with self.assertRaises(model.Invalid):
            accelerator_map({"new-tab": "<Ctrl><Shift>t", "close-pane": "<Ctrl><Shift>t"})
        with self.assertRaises(model.Invalid):
            accelerator_map({"new-tab": "<Shift>Insert"})
        self.app.save_profile("Custom Shell", "Custom Shell", model.PROFILE | {"font_size": 14})
        self.assertEqual(self.app.profile("Custom Shell")["font_size"], 14)
        self.assertEqual(self.app.profile_names().count("Custom Shell"), 1)
        self.app.preferences(self.window)
        until(lambda: bool(dialogs(self.window, "TermSpace Settings")))
        dialogs(self.window, "TermSpace Settings")[0].response(Gtk.ResponseType.CANCEL)
        config = model.settings(self.app.settings | {"theme": "light", "scheme": "Nord", "pane_headers": False})
        self.app.save_settings(config)
        self.assertFalse(self.pane.header.get_visible())
        self.assertFalse(Gtk.Settings.get_default().get_property("gtk-application-prefer-dark-theme"))

    def test_09_installed_tools_and_large_output(self):
        import shutil
        self.pane.session.terminal.set_scrollback_lines(120)
        send(self.pane, "seq 1 12000; printf 'LARGE%s\\n' '_OK'\n")
        until(lambda: "LARGE_OK" in output(self.pane), timeout=12)
        self.assertEqual(self.pane.session.terminal.get_scrollback_lines(), 120)
        tools = {"ssh": "-V", "docker": "--version", "ros2": "--help"}
        for name, argv in tools.items():
            path = shutil.which(name)
            if path:
                import shlex
                send(self.pane, f"{shlex.quote(path)} {argv} >/dev/null 2>&1 && printf '{name}%s\\n' '_OK'\n")
                with self.subTest(tool=name):
                    until(lambda: f"{name}_OK" in output(self.pane), timeout=12)
        if shutil.which("nano"):
            send(self.pane, "nano -I\n")
            until(lambda: "GNU nano" in output(self.pane))
            send(self.pane, "\x18")
            until(lambda: "GNU nano" not in output(self.pane))
            send(self.pane, "printf 'NANO%s\\n' '_OK'\n")
            until(lambda: "NANO_OK" in output(self.pane))
        if shutil.which("htop"):
            send(self.pane, "htop\n")
            until(lambda: "Tasks:" in output(self.pane))
            send(self.pane, "q")
            until(lambda: "Tasks:" not in output(self.pane))
            send(self.pane, "printf 'HTOP%s\\n' '_OK'\n")
            until(lambda: "HTOP_OK" in output(self.pane))

    def test_10_shell_completion_and_command_injection_boundaries(self):
        path = self.base / "shell ; ' folder"
        path.mkdir(exist_ok=True)
        app = self.app.build_window(cwd=str(path))
        pane = app.current().active
        until(lambda: pane.session.state == "running")
        item = path / "complete-me"
        item.write_text("AUTOCOMPLETED\n")
        send(pane, "cat compl\t\n")
        until(lambda: "AUTOCOMPLETED" in output(pane))
        self.assertFalse((path / "synthetic-marker").exists())
        pane.data["name"] = "$(touch synthetic-marker)"
        app.current().data["name"] = "Tab; touch synthetic-marker"
        self.app.put_workspace(app.snapshot("$(touch synthetic-marker)"))
        self.app.load_workspace("$(touch synthetic-marker)", None, review=False)
        self.assertFalse((path / "synthetic-marker").exists())

    def test_11_state_roundtrip_and_workspace_catalog(self):
        self.app.save_settings(model.settings(self.app.settings | {"restore_layout": True}))
        self.tab.split(self.pane, "top-bottom")
        self.app.remember_window(self.window)
        state = self.app.state.load()
        self.assertEqual(state["tabs"][0]["layout"]["type"], "split")
        copy = self.app.open_layout(model.workspace(state))
        self.assertEqual(len(list(panes(copy.current().tree))), 2)
        self.assertIsNot(copy.current().active.session.terminal, self.pane.session.terminal)

    def test_12_opacity_setting_updates_background_without_restarting_shell(self):
        terminal = self.pane.session.terminal
        pid = self.pane.session.pid
        self.app.preferences(self.window)
        dialog = dialogs(self.window, "TermSpace Settings")[0]
        notebook = dialog.get_content_area().get_first_child()
        notebook.set_current_page(1)
        appearance = notebook.get_nth_page(1).get_child().get_child()
        opacity = appearance.get_child_at(1, 2)
        self.assertEqual(opacity.get_value_as_int(), 100)
        opacity.set_value(66)
        opacity.spin(Gtk.SpinType.STEP_BACKWARD, 1)
        paintable = Gtk.WidgetPaintable.new(self.window)
        painted = []
        paintable.connect("invalidate-contents", lambda *_: painted.append(True))
        with patch.object(terminal, "set_colors", wraps=terminal.set_colors) as set_colors:
            dialog.response(1)
        foreground, background, _palette = set_colors.call_args.args
        composited = self.window.get_display().is_composited()
        self.assertAlmostEqual(background.alpha, 0.65 if composited else 1.0)
        self.assertEqual(foreground.alpha, 1.0)
        self.assertEqual(terminal.get_opacity(), 1.0)
        self.assertEqual(self.window.has_css_class("translucent-terminal"), composited)
        self.assertEqual(self.pane.session.pid, pid)
        self.assertEqual(self.app.config.load()["settings"]["background_opacity"], 65)
        if composited:
            until(lambda: painted)
            snapshot = Gtk.Snapshot.new()
            paintable.snapshot(snapshot, paintable.get_intrinsic_width(), paintable.get_intrinsic_height())
            texture = self.window.get_renderer().render_texture(snapshot.to_node(), None)
            downloader = Gdk.TextureDownloader.new(texture)
            downloader.set_format(Gdk.MemoryFormat.R8G8B8A8)
            pixel_bytes, stride = downloader.download_bytes()
            pixels = pixel_bytes.get_data()
            _, body = terminal.compute_bounds(self.window)
            _, pane = self.pane.box.compute_bounds(self.window)
            _, header = self.pane.header.compute_bounds(self.window)
            y = int(body.get_y() + body.get_height() / 2)
            x = int(body.get_x() + body.get_width() / 2)
            self.assertAlmostEqual(pixels[y * stride + 4 * x + 3], 166, delta=1)
            self.assertEqual(pixels[y * stride + 4 * int(pane.get_x()) + 3], 255)
            header_y = int(header.get_y() + header.get_height() / 2)
            self.assertEqual(pixels[header_y * stride + 4 * x + 3], 255)
        self.app.save_settings(self.app.settings | {"background_opacity": 100})
        self.assertFalse(self.window.has_css_class("translucent-terminal"))
        self.assertNotIn("background_opacity", self.app.config.load()["settings"])

    @unittest.skipUnless(os.environ.get("TERMSPACE_TEST_XEVENTS"), "Requires an isolated X11 XTest display")
    def test_13_zoom_with_real_keyboard_and_wheel_events(self):
        terminal = self.pane.session.terminal
        size = lambda: terminal.get_font().get_size() // Pango.SCALE
        self.tab.focus()
        control = Gdk.KEY_Control_L
        for keys, expected in (
            ((Gdk.KEY_equal,), 12), ((Gdk.KEY_Shift_L, Gdk.KEY_equal), 13),
            ((Gdk.KEY_minus,), 12), ((Gdk.KEY_0,), 11),
        ):
            xevents(self.window, keys=(control, *keys))
            until(lambda: size() == expected)
        xevents(self.window, keys=(Gdk.KEY_Num_Lock,))
        try:
            for key, expected in ((Gdk.KEY_KP_Add, 12), (Gdk.KEY_KP_Add, 13),
                                  (Gdk.KEY_KP_Subtract, 12), (Gdk.KEY_KP_0, 11)):
                xevents(self.window, keys=(control, key))
                until(lambda: size() == expected)
        finally:
            xevents(self.window, keys=(Gdk.KEY_Num_Lock,))
        _, bounds = terminal.compute_bounds(self.window)
        x, y = int(bounds.get_x()) + 40, int(bounds.get_y()) + 40
        for direction, expected in ((4, 12), (5, 11)):
            xevents(self.window, keys=(control,), click=(x, y, direction))
            until(lambda: size() == expected)
        import shutil
        if shutil.which("setxkbmap"):
            subprocess.run(["setxkbmap", "fr"], check=True, capture_output=True)
            try:
                xevents(self.window, keys=(control, Gdk.KEY_equal))
                until(lambda: size() == 12)
                xevents(self.window, keys=(control, Gdk.KEY_Shift_L, Gdk.KEY_0))
                until(lambda: size() == 11)
            finally:
                subprocess.run(["setxkbmap", "us"], check=True, capture_output=True)
        self.assertEqual(self.pane.zoom_notice.get_text(), "Font Size: 11 pt")
        self.assertTrue(terminal.has_focus())
        until(lambda: not self.pane.zoom_notice.is_visible())
        with self.assertRaises(model.Invalid):
            accelerator_map({"zoom-in": "<Ctrl>plus", "new-tab": "<Ctrl>equal"})
        with self.assertRaises(model.Invalid):
            accelerator_map({"zoom-in": "<Ctrl>plus", "new-tab": "<Ctrl>KP_Add"})
        reserved = self.app.settings["shortcuts"] | {"zoom-in": ""}
        self.app.save_settings(self.app.settings | {"shortcuts": reserved, "appearance": {"wheel_zoom": False}})
        xevents(self.window, keys=(control, Gdk.KEY_equal))
        xevents(self.window, keys=(control,), click=(x, y, 4))
        send(self.pane, "echo ZOOM''_DISABLED\n")
        until(lambda: "ZOOM_DISABLED\n" in output(self.pane))
        self.assertEqual(size(), 11)
        self.tab.split(self.pane, "left-right")
        divider = self.tab.tree.widget
        until(lambda: divider.get_position() > 0)
        position = divider.get_position()
        _, area = divider.compute_bounds(self.window)
        x = int(area.get_x()) + position + 2
        y = int(area.get_y() + area.get_height() / 2)
        xevents(self.window, drag=(x, y, 55, 0))
        until(lambda: divider.get_position() >= position + 40)

    def test_14_scoped_zoom_pty_and_workspace(self):
        terminal = self.pane.session.terminal
        pid = self.pane.session.pid
        size = lambda pane: pane.session.terminal.get_font().get_size() // Pango.SCALE
        initial_grid = terminal.get_pty().get_size()
        send(self.pane, "echo ZOOM''_PREVIOUS; read response; echo ZOOM''_DONE:$response\n")
        until(lambda: "ZOOM_PREVIOUS\n" in output(self.pane))
        terminal.select_all()
        window_size = self.window.get_width(), self.window.get_height()
        self.window.perform("zoom-in")
        until(lambda: terminal.get_pty().get_size() != initial_grid)
        success, rows, cols = terminal.get_pty().get_size()
        self.assertTrue(success)
        self.assertEqual((rows, cols), (terminal.get_row_count(), terminal.get_column_count()))
        self.assertEqual((self.window.get_width(), self.window.get_height()), window_size)
        self.assertEqual(size(self.pane), 12)
        self.assertEqual(self.pane.session.pid, pid)
        self.assertIn("ZOOM_PREVIOUS", output(self.pane))
        if terminal.get_has_selection():
            self.assertIn("ZOOM_PREVIOUS", terminal.get_text_selected(Vte.Format.TEXT))
        send(self.pane, "still-alive\n")
        until(lambda: "ZOOM_DONE:still-alive" in output(self.pane))

        self.tab.split(self.pane, "left-right")
        second = self.tab.active
        self.tab.split(second, "top-bottom")
        third = self.tab.active
        self.window.perform("zoom-in")
        self.assertEqual([size(x) for x in (self.pane, second, third)], [12, 12, 13])
        other_tab = self.window.add_tab()
        other = self.app.build_window(cwd=str(self.base))
        self.assertEqual([size(other_tab.active), size(other.current().active)], [11, 11])
        self.window.notebook.set_current_page(0)
        self.app.save_settings(self.app.settings | {"appearance": {"zoom_scope": "Current Tab", "zoom_step": 2}})
        self.window.perform("zoom-in")
        self.assertEqual([size(x) for x in (self.pane, second, third, other_tab.active)], [14, 14, 15, 11])
        self.app.save_settings(self.app.settings | {"appearance": {"zoom_scope": "All Terminals"}})
        self.window.perform("zoom-out")
        self.assertEqual([size(x) for x in (self.pane, second, third, other_tab.active, other.current().active)],
                         [13, 13, 14, 10, 10])
        self.window.theme_name = "Nord"
        self.window.appearance = {"cell_height": 115, "padding": 10}
        self.tab.data["terminal_theme"] = "Dracula"
        third.data["terminal_theme"] = "Monokai"
        self.app.put_workspace(self.window.snapshot("Zoom layout"))
        self.app.load_workspace("Zoom layout", None, review=False)
        restored = next(w for w in self.app.windows() if w.workspace_name == "Zoom layout")
        self.assertEqual([size(pane) for pane in panes(restored.current().tree)], [13, 13, 14])
        self.assertEqual(restored.current().data["terminal_theme"], "Dracula")
        self.assertEqual(list(panes(restored.current().tree))[-1].data["terminal_theme"], "Monokai")
        self.assertEqual(restored.theme_name, "Nord")
        self.assertAlmostEqual(restored.current().active.session.terminal.get_cell_height_scale(), 1.15)
        self.assertIn("Zoom layout", restored.status.get_text())
        self.app.save_settings(self.app.settings | {"appearance": {"font_size": 16}})
        self.window.zoom("zoom-reset", reset_all=True)
        self.assertTrue(all(size(pane) == 16 for window in self.app.windows() for tab in window.tabs
                            for pane in panes(tab.tree)))
        new = self.window.add_tab()
        self.assertEqual(size(new.active), 16)
        for _ in range(30):
            self.window.perform("zoom-in")
        self.assertEqual(size(new.active), 40)
        for _ in range(45):
            self.window.perform("zoom-out")
        self.assertEqual(size(new.active), 6)

    def test_15_themes_editor_and_active_programs(self):
        import shutil
        from termspace.preferences import theme_editor

        self.tab.split(self.pane, "left-right")
        self.tab.split(self.tab.active, "top-bottom")
        self.window.add_tab()
        pids = {pane: pane.session.pid for tab in self.window.tabs for pane in panes(tab.tree)}
        until(lambda: all(pane.session.state == "running" for pane in pids))
        pids = {pane: pane.session.pid for pane in pids}
        self.app.preferences(self.window)
        settings = dialogs(self.window, "TermSpace Settings")[0]
        tabs = settings.get_content_area().get_first_child()
        tabs.set_current_page(2)
        picker = tabs.get_nth_page(2).get_first_child()
        for index, name in enumerate(self.app.available_themes()):
            picker.set_selected(index)
            theme = self.app.theme(name)
            self.assertEqual(self.pane.session.current_colors[0]["terminal_bg"], theme["terminal_bg"])
        gsettings = self.app.desktop
        if gsettings and os.environ.get("GSETTINGS_BACKEND") == "memory":
            with self.subTest(system_theme=True):
                gsettings.set_string("color-scheme", "prefer-dark")
                until(lambda: self.pane.session.current_colors[0]["window"] == "#16161e")
                gsettings.set_string("color-scheme", "prefer-light")
                until(lambda: self.pane.session.current_colors[0]["window"] == "#edf0f7")
                gsettings.reset("color-scheme")
        theme_editor(self.app, settings, self.app.set_theme, data=themes.BUILTINS["Nord"])
        editor = dialogs(settings, "Custom theme")[0]
        form = editor.get_content_area().get_last_child().get_nth_page(0).get_child().get_child()
        form.get_child_at(1, 0).set_text("Custom Example")
        form.get_child_at(1, 2).set_value(15)
        editor.response(1)
        self.assertEqual(self.app.config.load()["themes"]["Custom Example"]["font_size"], 15)
        settings.response(Gtk.ResponseType.CANCEL)
        self.window.notebook.set_current_page(0)
        self.tab.maximize(self.pane)
        until(lambda: self.pane.session.terminal.get_column_count() > 100)
        send(self.pane, "echo THEMED''_PTY\n")
        until(lambda: "THEMED_PTY\n" in output(self.pane))
        self.tab.data["terminal_theme"] = "Custom Example"
        self.tab.apply_settings()
        self.app.set_theme("Renamed", "Custom Example", self.app.theme("Custom Example"))
        self.assertEqual(self.tab.data["terminal_theme"], "Renamed")
        self.app.set_theme("", "Renamed")
        self.assertEqual(self.tab.data["terminal_theme"], "")

        programs = [
            ("nano", "nano -I", "GNU nano", "\x18"),
            ("htop", "htop", "Tasks:", "q"),
            ("vi", "vi -u NONE -i NONE", "VIM - Vi IMproved", "\x1b:q!\r"),
        ]
        for program, command, marker, quit_keys in programs:
            if not shutil.which(program):
                continue
            with self.subTest(program=program):
                exited = program + "_THEME_OK:0"
                send(self.pane, f"{command}; printf '{program}%s:%s\\n' '_THEME_OK' \"$?\"\n")
                until(lambda: marker in output(self.pane))
                self.app.save_settings(self.app.settings | {"app_theme": "Nord"})
                self.app.save_settings(self.app.settings | {"app_theme": "Catppuccin Mocha"})
                self.assertIn(marker, output(self.pane))
                send(self.pane, quit_keys)
                until(lambda: exited in output(self.pane))
        self.assertEqual({pane: pane.session.pid for pane in pids}, pids)


    def test_16_theme_import_export_and_apply_all_from_settings(self):
        import json

        path = self.base / "theme-import.json"
        sample = {"schema_version": 1, "name": "Example import", "theme": themes.BUILTINS["Nord"]}
        path.write_text(json.dumps(sample))
        self.app.preferences(self.window)
        dialog = dialogs(self.window, "TermSpace Settings")[0]
        notebook = dialog.get_content_area().get_first_child()
        notebook.set_current_page(2)
        page = notebook.get_nth_page(2)
        picker = page.get_first_child()
        buttons = {}
        for box in (picker.get_next_sibling().get_next_sibling(),
                    picker.get_next_sibling().get_next_sibling().get_next_sibling()):
            button = box.get_first_child()
            while button:
                buttons[button.get_label()] = button
                button = button.get_next_sibling()
        with patch("termspace.preferences.choose_file", side_effect=lambda *_, **k: k["callback"](path)):
            buttons["Import…"].emit("clicked")
        editor = dialogs(dialog, "Custom theme")[0]
        editor.response(1)
        self.assertEqual(self.app.theme("Example import"), sample["theme"])

        sample["theme"] = sample["theme"] | {"css": "example"}
        path.write_text(json.dumps(sample))
        with patch("termspace.preferences.choose_file", side_effect=lambda *_, **k: k["callback"](path)):
            buttons["Import…"].emit("clicked")
        self.assertFalse(dialogs(dialog, "Custom theme"))
        dialogs(dialog, "Theme action failed")[0].response(Gtk.ResponseType.CLOSE)

        picker.set_selected(self.app.available_themes().index("Example import"))
        destination = self.base / "theme-export.json"
        with patch("termspace.preferences.choose_file", side_effect=lambda *_, **k: k["callback"](destination)):
            buttons["Export…"].emit("clicked")
        self.assertEqual(model.theme_document(json.loads(destination.read_text()))[0], "Example import")
        self.tab.data["terminal_theme"] = "Dracula"
        self.pane.data["terminal_theme"] = "Light"
        self.pane.apply_settings()
        other = self.app.build_window(cwd=str(self.base))
        other.theme_name = "Monokai"
        other.apply_settings()
        buttons["Apply to all terminals"].emit("clicked")
        self.assertEqual(self.pane.session.current_colors[0]["window"], sample["theme"]["window"])
        self.assertEqual(other.current().active.session.current_colors[0]["window"], sample["theme"]["window"])
        self.assertFalse(other.theme_name)
        buttons["Restore Tokyo Night"].emit("clicked")
        self.assertEqual(self.app.app_theme_name(), themes.DEFAULT)
        self.assertEqual(self.app.available_themes()[picker.get_selected()], themes.DEFAULT)
