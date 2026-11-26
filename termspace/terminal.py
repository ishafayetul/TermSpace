"""A VTE widget, its PTY lifecycle and deliberate clipboard input."""

import os
import re

from . import model
from .dialogs import ask, message
from .native import Gdk, Gio, GLib, GObject, Gtk, Pango, Vte

ORIENTATION = Gtk.Orientation
CONTROL = Gdk.ModifierType.CONTROL_MASK
SHIFT = Gdk.ModifierType.SHIFT_MASK
PCRE_MULTILINE = 0x00000400
PCRE_CASELESS = 0x00000008
# Original palettes inspired by the named themes. The ANSI order follows VTE.
PALETTES = {
    "Ubuntu": ("#201927", "#eee8f0", "#d4779b", "#aa8ef0"),
    "Dracula": ("#282a36", "#f8f8f2", "#ff79c6", "#bd93f9"),
    "Nord": ("#2e3440", "#eceff4", "#bf616a", "#88c0d0"),
    "Gruvbox": ("#282828", "#ebdbb2", "#fb4934", "#d79921"),
    "Solarized Dark": ("#002b36", "#eee8d5", "#dc6871", "#47a6b8"),
    "Monokai": ("#272822", "#f8f8f2", "#f92672", "#ae81ff"),
    "Tokyo Night": ("#1a1b26", "#c0caf5", "#f7768e", "#7aa2f7"),
    "One Dark": ("#282c34", "#e1e5eb", "#e06c75", "#61afef"),
}


def rgba(value: str):
    result = Gdk.RGBA()
    result.parse(value)
    return result


class Session:
    def __init__(self, data: dict, profile: dict, settings: dict, changed, context,
                 *, startup: str = "", start: bool = True):
        self.data = data
        self.profile = profile
        self.cwd = data["working_directory"]
        self.shell = profile["shell"] or model.login_shell()
        self.changed = changed
        self.state = "starting"
        self.pid: int | None = None
        self.exit_status: int | None = None
        self.closed = False
        self.search_query = None
        self.spawning = Gio.Cancellable()
        self.pasting: Gio.Cancellable | None = None
        self.paste_dialog = None
        self.terminal = terminal = Vte.Terminal(hexpand=True, vexpand=True)
        terminal.set_enable_sixel(False)
        terminal.set_scroll_on_keystroke(True)
        terminal.set_mouse_autohide(True)
        self.configure(settings)
        self.signals = [
            terminal.connect("child-exited", self.exited),
            terminal.connect("window-title-changed", lambda *_: self.changed()),
            terminal.connect("paste-clipboard", self.native_paste),
            terminal.connect("setup-context-menu", context),
        ]
        self.keys = Gtk.EventControllerKey.new()
        self.keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.keys.connect("key-pressed", self.key)
        terminal.add_controller(self.keys)
        self.mouse = Gtk.GestureClick.new()
        self.mouse.set_button(2)
        self.mouse.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.mouse.connect("pressed", self.middle)
        terminal.add_controller(self.mouse)
        if start:
            self.spawn(startup)

    def configure(self, settings: dict) -> None:
        terminal = self.terminal
        profile = self.profile
        terminal.set_allow_hyperlink(settings["hyperlinks"])
        terminal.set_scrollback_lines(min(profile["scrollback"], settings["limits"]["scrollback"]))
        terminal.set_audible_bell(profile["bell"])
        terminal.set_cursor_blink_mode(Vte.CursorBlinkMode.ON if profile["blink"] else Vte.CursorBlinkMode.OFF)
        terminal.set_cursor_shape({"block": Vte.CursorShape.BLOCK, "ibeam": Vte.CursorShape.IBEAM,
                                   "underline": Vte.CursorShape.UNDERLINE}[profile["cursor"]])
        font = Pango.FontDescription()
        font.set_family(profile["font"])
        font.set_size(profile["font_size"] * Pango.SCALE)
        terminal.set_font(font)
        background, foreground, red, accent = PALETTES[settings["scheme"]]
        gtk = Gtk.Settings.get_default()
        named_dark = gtk and gtk.get_property("gtk-theme-name").lower().endswith("-dark")
        if settings["theme"] == "light" or (settings["theme"] == "system" and gtk
                and not gtk.get_property("gtk-application-prefer-dark-theme") and not named_dark):
            background, foreground, red, accent = "#f6f3f9", "#302839", "#aa294e", "#5540a0"
            palette = [foreground, red, "#256a41", "#815807", accent, "#8b368d", "#226874", "#675d73"]
            palette = palette + palette
        else:
            palette = ["#3e3749", red, "#98c79f", "#e9c17f", accent, "#df9bdf", "#85c8d5", foreground,
                       "#9287a4", red, "#b5e0ad", "#ffe0a1", accent, "#eec1f2", "#b4e0eb", "#ffffff"]
        terminal.set_colors(rgba(profile["foreground"] or foreground),
                            rgba(profile["background"] or background),
                            [rgba(c) for c in profile["palette"] or palette])

    def spawn(self, startup: str = "") -> None:
        if not model.executable(self.shell):
            self.state = "failed"
            self.changed()
            return
        # VTE can fall back after chdir failure. env fails closed before executing the shell.
        argv = ["/usr/bin/env", f"--chdir={self.cwd}", "--", self.shell, *self.profile["arguments"]]
        if startup:
            argv.extend(["-c", startup])
        environ = [f"{key}={value}" for key, value in self.profile["environment"].items()]
        flags = Vte.PtyFlags.NO_LASTLOG | Vte.PtyFlags.NO_UTMP | Vte.PtyFlags.NO_WTMP
        try:
            # Noble's PyGObject requires the child_setup_data slot even when unused.
            spawn_flags = GLib.SpawnFlags(Vte.SPAWN_NO_SYSTEMD_SCOPE)
            self.terminal.spawn_async(flags, self.cwd, argv, environ, spawn_flags,
                                      None, None, 5000, self.spawning, self.spawned, None)
        except (GLib.Error, TypeError):
            self.state = "failed"
            self.changed()

    def spawned(self, terminal, pid: int, error, _data) -> None:
        if self.closed:
            return
        self.pid = pid if pid >= 0 and self.exit_status is None else None
        if self.exit_status is None:
            self.state = "failed" if error or pid < 0 else "running"
        self.changed()

    def exited(self, _terminal, status: int) -> None:
        self.pid = None
        self.exit_status = status
        self.state = "exited"
        self.changed()

    def current_directory(self) -> str:
        try:
            # OSC 7 is controlled by remote output. Prefer the local child identity.
            if self.pid:
                path = os.readlink(f"/proc/{self.pid}/cwd")
                return model.directory(path)
        except (ValueError, OSError):
            pass
        return self.cwd

    def close(self) -> None:
        self.closed = True
        self.spawning.cancel()
        if self.pasting:
            self.pasting.cancel()
        if self.paste_dialog:
            self.paste_dialog.destroy()
            self.paste_dialog = None
        for handler in self.signals:
            self.terminal.disconnect(handler)
        self.terminal.remove_controller(self.keys)
        self.terminal.remove_controller(self.mouse)
        terminal = self.terminal
        if parent := terminal.get_parent():
            parent.remove(terminal)
        # Noble's GTK4 VTE handles PTY closure and reaping in widget disposal.
        terminal.run_dispose()

    def native_paste(self, terminal) -> None:
        GObject.signal_stop_emission_by_name(terminal, "paste-clipboard")
        self.paste()

    def key(self, _controller, key, _code, modifiers) -> bool:
        if key in (Gdk.KEY_Insert, Gdk.KEY_KP_Insert) and modifiers & SHIFT:
            self.paste(primary=not bool(modifiers & CONTROL))
            return True
        return False

    def middle(self, gesture, *_args) -> None:
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self.paste(primary=True)

    def paste(self, *, primary: bool = False) -> None:
        root = self.terminal.get_root()
        if self.closed or root is None or self.state != "running" or self.pasting or self.paste_dialog:
            return
        clipboard = self.terminal.get_primary_clipboard() if primary else self.terminal.get_clipboard()
        cancel = self.pasting = Gio.Cancellable.new()
        content = bytearray()
        timed_out = False

        def timeout():
            nonlocal timed_out, deadline
            timed_out = True
            deadline = 0
            cancel.cancel()
            return GLib.SOURCE_REMOVE

        deadline = GLib.timeout_add_seconds(5, timeout)

        def finish(error: str = ""):
            if deadline:
                GLib.source_remove(deadline)
            self.pasting = None
            if self.closed or self.state != "running" or self.terminal.get_root() is not root:
                return
            if timed_out or error:
                message(root, "Paste unavailable", "Clipboard read timed out." if timed_out else error)
                return
            try:
                value = content.decode("utf-8")
            except UnicodeError:
                message(root, "Paste unavailable", "Clipboard text is not valid UTF-8.")
                return
            if not model.unsafe_paste(value):
                self.terminal.paste_text(value)
                return

            def answer(response, _text):
                self.paste_dialog = None
                if self.closed or self.state != "running" or self.terminal.get_root() is not root:
                    return
                if response == 2:
                    self.terminal.paste_text(value.replace("\0", "").rstrip("\r\n"))
                elif response == 1:
                    self.terminal.paste_text(value.replace("\0", ""))

            self.paste_dialog = ask(
                root, "Review clipboard text", "This text contains line breaks or hidden characters. "
                "Control characters appear as escapes. NUL bytes are omitted and VTE handles terminal paste formatting.",
                [(Gtk.ResponseType.CANCEL, "Cancel"), (2, "Paste without trailing newline"), (1, "Paste")],
                answer, text=model.preview(value), monospace=True)

        def read_chunk(stream, result):
            try:
                data = stream.read_bytes_finish(result).get_data()
            except GLib.Error:
                stream.close_async(GLib.PRIORITY_DEFAULT, None, None)
                finish("Could not read clipboard text.")
                return
            content.extend(data)
            if not data or len(content) > model.PASTE_LIMIT:
                stream.close_async(GLib.PRIORITY_DEFAULT, None, None)
                finish("Clipboard text exceeds 64 KiB." if data else "")
            else:
                stream.read_bytes_async(4096, GLib.PRIORITY_DEFAULT, cancel, read_chunk)

        def opened(source, result):
            try:
                stream, _mime = source.read_finish(result)
            except GLib.Error:
                finish("Clipboard does not contain compatible text.")
                return
            stream.read_bytes_async(4096, GLib.PRIORITY_DEFAULT, cancel, read_chunk)

        clipboard.read_async(["text/plain;charset=utf-8", "UTF8_STRING", "text/plain"],
                             GLib.PRIORITY_DEFAULT, cancel, opened)

    def search(self, query: str, case: bool, regex: bool) -> None:
        options = (query, case, regex)
        if self.search_query == options:
            return
        if not query:
            self.terminal.search_set_regex(None, 0)
            self.search_query = options
            return
        model.require(len(query) <= 128, "Search text is limited to 128 characters.")
        if regex:
            # One bounded PCRE2 match budget per candidate, with expensive constructs excluded.
            model.require(not re.search(r"[()|{}\\]", query), "Use a simple regular expression without "
                          "groups, alternation, escapes or counted repeats.")
            model.require(sum(query.count(c) for c in "*+?") <= 2, "Use at most two quantifiers.")
        pattern = "(*LIMIT_MATCH=1000)(*LIMIT_DEPTH=100)" + (query if regex else re.escape(query))
        flags = PCRE_MULTILINE | (0 if case else PCRE_CASELESS)
        self.terminal.unselect_all()
        self.terminal.search_set_regex(Vte.Regex.new_for_search(pattern, -1, flags), 0)
        self.terminal.search_set_wrap_around(True)
        self.search_query = options
