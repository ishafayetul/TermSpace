"""Binary layout and GTK views. Pane identity survives every layout edit."""

from dataclasses import dataclass

from . import model
from .dialogs import ask, message, prompt
from .native import Gdk, Gio, GLib, Gtk, Pango, Vte
from .terminal import Session

H = Gtk.Orientation.HORIZONTAL
V = Gtk.Orientation.VERTICAL


def button(icon: str, label: str, callback):
    widget = Gtk.Button(icon_name=icon, tooltip_text=label)
    widget.update_property([Gtk.AccessibleProperty.LABEL], [label])
    widget.add_css_class("flat")
    widget.connect("clicked", lambda *_: callback())
    return widget


def menu(widget, group: str, items):
    actions = Gio.SimpleActionGroup()
    entries = Gio.Menu()
    for index, (label, callback) in enumerate(items):
        name = f"item{index}"
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", lambda *_args, call=callback: call())
        actions.add_action(action)
        entries.append(label, f"{group}.{name}")
    widget.insert_action_group(group, actions)
    return entries


def accent(widget, value: str) -> None:
    if getattr(widget, "accent_value", None) == value:
        return
    widget.accent_value = value
    previous = getattr(widget, "accent_provider", None)
    context = widget.get_style_context()
    if previous:
        context.remove_provider(previous)
    widget.accent_provider = None
    if value:
        provider = Gtk.CssProvider()
        provider.load_from_data(f".accented {{ box-shadow: inset 3px 0 {value}; }}".encode())
        context.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        widget.add_css_class("accented")
        widget.accent_provider = provider


class Pane:
    def __init__(self, tab, data: dict, startup: str = ""):
        self.tab = tab
        self.data = data
        self.box = Gtk.Box(orientation=V, hexpand=True, vexpand=True, css_classes=["pane"])
        self.header = Gtk.Box(spacing=2, css_classes=["pane-header"])
        self.heading = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END)
        self.header.append(self.heading)
        self.box.append(self.header)
        profile = tab.window.app.profile(data["profile"])
        self.session = Session(data, profile, tab.window.app.settings, self.changed, self.context,
                               startup=startup, start=False)
        body = Gtk.Box()
        terminal = self.session.terminal
        body.append(terminal)
        scrollbar = Gtk.Scrollbar(orientation=V, adjustment=terminal.get_vadjustment(),
                                  css_classes=["terminal-scrollbar"])
        body.append(scrollbar)
        self.box.append(body)
        self.focus_signal = terminal.connect("notify::has-focus", self.focused)
        self.link_gesture = Gtk.GestureClick(button=1, propagation_phase=Gtk.PropagationPhase.CAPTURE)
        self.link_gesture.connect("pressed", self.link_click)
        terminal.add_controller(self.link_gesture)
        self.menu_button = Gtk.MenuButton(icon_name="view-more-symbolic", tooltip_text="Pane actions",
                                         css_classes=["flat"])
        self.menu_button.update_property([Gtk.AccessibleProperty.LABEL], ["Pane actions"])
        self.header.append(self.menu_button)
        self.header.append(button("view-fullscreen-symbolic", "Maximize or restore pane",
                                  lambda: self.tab.maximize(self)))
        self.header.append(button("window-close-symbolic", "Close pane",
                                  lambda: self.tab.window.close_pane(self)))
        self.apply_settings()
        self.changed()
        self.session.spawn(startup)

    def actions(self):
        session = self.session
        actions = [
            ("Copy", lambda: session.terminal.copy_clipboard_format(Vte.Format.TEXT)),
            ("Paste", session.paste), ("Select all", session.terminal.select_all),
            ("Search", lambda: self.tab.window.show_search(self)),
            ("Rename pane", self.rename), ("Change pane color", self.change_accent),
            ("Split left/right", lambda: self.tab.split(self, "left-right")),
            ("Split top/bottom", lambda: self.tab.split(self, "top-bottom")),
            ("Maximize / restore pane", lambda: self.tab.maximize(self)),
            ("Duplicate pane", lambda: self.tab.split(self, self.tab.window.app.settings["split_direction"], duplicate=True)),
            ("Move or swap pane", lambda: self.tab.window.move_pane(self)),
            ("Edit startup commands", lambda: self.tab.window.edit_commands(self)),
            ("Clear scrollback", lambda: session.terminal.reset(False, True)),
            ("Reset terminal", lambda: session.terminal.reset(True, False)),
            ("Close pane", lambda: self.tab.window.close_pane(self)),
        ]
        return actions

    def context(self, terminal, _context) -> None:
        terminal.set_context_menu_model(menu(terminal, "pane", self.actions()))

    def link_click(self, gesture, _count, x, y) -> None:
        state = gesture.get_current_event_state()
        if self.tab.window.app.settings["hyperlinks"] and state & Gdk.ModifierType.CONTROL_MASK:
            url = self.session.terminal.check_hyperlink_at(x, y)
            if url and model.url(url):
                gesture.set_state(Gtk.EventSequenceState.CLAIMED)
                self.open_link(url)

    def open_link(self, url: str) -> None:
        window = self.tab.window
        if not window.app.settings["hyperlinks"] or not model.url(url):
            return

        def launch(response, _text):
            if response == 1 and window.app.settings["hyperlinks"] and not self.session.closed:
                try:
                    Gio.AppInfo.launch_default_for_uri(url, None)
                except GLib.Error:
                    message(window, "Unable to open link", "No browser accepted the URL.")

        ask(window, "Open this link?", "Your default browser may make a network request.",
            [(Gtk.ResponseType.CANCEL, "Cancel"), (1, "Open")], launch, text=url, monospace=True)

    def focused(self, terminal, _param) -> None:
        if terminal.has_focus():
            self.tab.set_active(self)

    def changed(self) -> None:
        session = getattr(self, "session", None)
        if not session:
            return
        name = self.data["name"] or model.title(session.terminal.get_window_title(),
                                               self.data["profile"] if self.data["profile"] != model.DEFAULT_PROFILE
                                               else "Terminal")
        self.name = name
        suffix = {"exited": " · Exited", "failed": " · Shell failed"}.get(session.state, "")
        self.heading.set_text(name + suffix)
        self.tab.refresh()

    def rename(self) -> None:
        prompt(self.tab.window, "Rename pane", self.data["name"],
               lambda value: self.update_field("name", value), "Leave empty to use the shell title.")

    def change_accent(self) -> None:
        prompt(self.tab.window, "Pane accent color", self.data["accent"],
               lambda value: self.update_field("accent", value), "Use #RRGGBB, or leave empty.")

    def update_field(self, key: str, value: str) -> None:
        try:
            self.data[key] = model.color(value) if key == "accent" else model.label(value, empty=True)
            self.apply_settings()
            self.changed()
        except model.Invalid as exc:
            message(self.tab.window, "Invalid pane setting", str(exc))

    def apply_settings(self) -> None:
        settings = self.tab.window.app.settings
        self.header.set_visible(settings["pane_headers"])
        self.session.configure(settings)
        self.menu_button.set_menu_model(menu(self.menu_button, "pane", self.actions()))
        accent(self.header, self.data["accent"] or self.session.profile["accent"])

    def snapshot(self) -> dict:
        return dict(self.data, working_directory=self.session.current_directory())

    def close(self) -> None:
        self.session.terminal.disconnect(self.focus_signal)
        self.session.terminal.remove_controller(self.link_gesture)
        self.session.close()


@dataclass(eq=False)
class Split:
    orientation: str
    ratio: float
    left: "Pane | Split"
    right: "Pane | Split"
    widget: Gtk.Paned | None = None

    def sample_ratio(self) -> None:
        if self.widget:
            size = self.widget.get_width() if self.orientation == "left-right" else self.widget.get_height()
            if size > 0 and self.widget.get_property("position-set"):
                self.ratio = min(.95, max(.05, self.widget.get_position() / size))


def panes(node):
    if isinstance(node, Pane):
        yield node
    elif node:
        yield from panes(node.left)
        yield from panes(node.right)


def depth(node) -> int:
    return 1 if isinstance(node, Pane) else 1 + max(depth(node.left), depth(node.right))


def replace(node, source, target):
    if node is source:
        return target
    if isinstance(node, Split):
        left = replace(node.left, source, target)
        right = replace(node.right, source, target)
        if left is None or right is None:
            return left or right
        node.left, node.right = left, right
    return node


class Tab:
    def __init__(self, window, data: dict, commands: dict[str, str]):
        self.window = window
        self.data = data
        self.page = Gtk.Box(orientation=V, hexpand=True, vexpand=True)
        self.label = Gtk.Box(spacing=4, css_classes=["tab-label"])
        self.heading = Gtk.Label(ellipsize=Pango.EllipsizeMode.END, width_chars=10, max_width_chars=28)
        self.badge = Gtk.Label(css_classes=["tab-count"])
        self.label.append(self.heading)
        self.label.append(self.badge)
        self.label.append(button("window-close-symbolic", "Close tab", lambda: self.window.close_tabs([self])))
        self.maximized = None
        self.active = None
        self.tree = None
        self.tree = self.restore(data["layout"], commands)
        self.set_active(next(panes(self.tree)))
        self.mount()
        self.context_menu = Gtk.PopoverMenu()
        self.context_menu.set_parent(self.label)
        gesture = Gtk.GestureClick(button=3)
        gesture.connect("pressed", self.context)
        self.label.add_controller(gesture)
        keyboard = Gtk.EventControllerKey()
        keyboard.connect("key-pressed", self.menu_key)
        self.label.add_controller(keyboard)
        self.label.set_focusable(True)
        self.refresh()

    def restore(self, node: dict, commands: dict):
        if node["type"] == "terminal":
            script = commands.get(node["id"], "")
            cwd = node["working_directory"] if script else self.window.app.resolve_cwd(
                node["working_directory"], node["profile"])
            return Pane(self, dict(node, id=model.leaf()["id"], working_directory=cwd), script)
        left, right = node["children"]
        return Split(node["orientation"], node["ratio"], self.restore(left, commands), self.restore(right, commands))

    def context(self, gesture, _count, x, y):
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        area = Gdk.Rectangle()
        area.x, area.y, area.width, area.height = int(x), int(y), 1, 1
        self.context_menu.set_pointing_to(area)
        self.show_context()

    def menu_key(self, _controller, key, _code, modifiers):
        if key == Gdk.KEY_Menu or key == Gdk.KEY_F10 and modifiers & Gdk.ModifierType.SHIFT_MASK:
            self.context_menu.set_pointing_to(None)
            self.show_context()
            return True
        return False

    def show_context(self):
        self.context_menu.set_menu_model(menu(self.label, "tab", [
            ("New tab", self.window.add_tab),
            ("Rename tab", lambda: self.edit("name")),
            ("Change tab color", lambda: self.edit("accent")),
            ("Duplicate layout", lambda: self.window.add_tab(self.snapshot())),
            ("Move to new window", lambda: self.window.app.move_tab(self)),
            ("Save as workspace", lambda: self.window.app.save_workspace(self.window, self)),
            ("Close tab", lambda: self.window.close_tabs([self])),
            ("Close other tabs", lambda: self.window.close_tabs([tab for tab in self.window.tabs if tab is not self])),
        ]))
        self.context_menu.popup()

    def edit(self, key: str):
        def save(value):
            try:
                self.data[key] = model.color(value) if key == "accent" else model.label(value, empty=True)
                self.refresh()
            except model.Invalid as exc:
                message(self.window, "Invalid tab setting", str(exc))
        prompt(self.window, "Rename tab" if key == "name" else "Tab accent color",
               self.data[key], save, "Use #RRGGBB, or leave empty." if key == "accent"
               else "Leave empty to follow the focused pane.")

    def refresh(self) -> None:
        self.heading.set_text(self.data["name"] or (self.active.name if self.active else "Terminal"))
        self.badge.set_text(str(sum(1 for _ in panes(self.tree))))
        accent(self.label, self.data["accent"])
        self.window.refresh_status()

    def set_active(self, pane: Pane) -> None:
        if self.active:
            self.active.box.remove_css_class("focused")
        self.active = pane
        pane.box.add_css_class("focused")
        self.refresh()

    def detach(self) -> None:
        if child := self.page.get_first_child():
            self.page.remove(child)

        def release(node):
            if isinstance(node, Split) and node.widget:
                node.sample_ratio()
                node.widget.set_start_child(None)
                node.widget.set_end_child(None)
                node.widget = None
                release(node.left)
                release(node.right)
        release(self.tree)

    def mount(self) -> None:
        def build(node):
            if isinstance(node, Pane):
                return node.box
            widget = node.widget = Gtk.Paned(orientation=H if node.orientation == "left-right" else V,
                                            wide_handle=False, hexpand=True, vexpand=True)
            widget.set_start_child(build(node.left))
            widget.set_end_child(build(node.right))
            widget.set_shrink_start_child(False)
            widget.set_shrink_end_child(False)

            def position(paned, _clock):
                if paned.get_property("position-set"):
                    return GLib.SOURCE_REMOVE
                size = paned.get_width() if node.orientation == "left-right" else paned.get_height()
                if not size:
                    return GLib.SOURCE_CONTINUE
                paned.set_position(round(size * node.ratio))
                return GLib.SOURCE_REMOVE

            widget.add_tick_callback(position)
            return widget
        self.page.append(build(self.maximized or self.tree))

    def focus(self, pane: Pane | None = None) -> None:
        if pane:
            self.set_active(pane)
        if self.active:
            self.active.session.terminal.grab_focus()

    def split(self, pane: Pane, orientation: str, *, duplicate: bool = False) -> None:
        def level(node, distance):
            if node is pane:
                return distance
            if isinstance(node, Split):
                return max(level(node.left, distance + 1), level(node.right, distance + 1))
            return 0
        settings = self.window.app.settings
        if not self.window.allow(panes_count=1):
            return
        if level(self.tree, 1) >= settings["limits"]["depth"]:
            message(self.window, "Split limit reached", "Raise the split depth limit in Settings.")
            return
        cwd = pane.session.current_directory() if settings["inherit_directory"] or duplicate else ""
        data = model.leaf(self.window.app.resolve_cwd(cwd, pane.data["profile"]), pane.data["profile"],
                          name=pane.data["name"] if duplicate else "", accent=pane.data["accent"])
        created = Pane(self, data)
        self.detach()
        self.maximized = None
        self.tree = replace(self.tree, pane, Split(orientation, .5, pane, created))
        self.mount()
        self.focus(created)

    def maximize(self, pane: Pane) -> None:
        self.detach()
        self.maximized = None if self.maximized is pane else pane
        self.mount()
        self.focus(pane)

    def remove(self, pane: Pane) -> None:
        self.detach()
        if pane is self.maximized:
            self.maximized = None
        self.tree = replace(self.tree, pane, None)
        pane.close()
        self.mount()
        self.focus(self.maximized or next(panes(self.tree)))

    def swap(self, first: Pane, second: Pane) -> None:
        if first is second:
            return
        self.detach()
        self.maximized = None

        def swap_nodes(node):
            if isinstance(node, Split):
                node.left = swap_nodes(node.left)
                node.right = swap_nodes(node.right)
            return second if node is first else first if node is second else node
        self.tree = swap_nodes(self.tree)
        self.mount()
        self.focus(first)

    def snapshot(self) -> dict:
        def serialize(node):
            if isinstance(node, Pane):
                return node.snapshot()
            node.sample_ratio()
            return {"type": "split", "orientation": node.orientation, "ratio": node.ratio,
                    "children": [serialize(node.left), serialize(node.right)]}
        return {"name": self.data["name"], "accent": self.data["accent"], "layout": serialize(self.tree)}

    def close(self) -> None:
        self.detach()
        self.context_menu.unparent()
        for pane in panes(self.tree):
            pane.close()
