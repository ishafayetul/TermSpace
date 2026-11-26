"""Application window, focus, tabs and pane actions."""

from . import model
from .dialogs import ask, message, prompt
from .layout import Tab, Split, button, menu, panes, replace
from .native import Gdk, Gio, GLib, Gtk, Pango, Vte


class Window(Gtk.ApplicationWindow):
    def __init__(self, app, data: dict | None = None, commands: dict | None = None,
                 *, cwd: str = "", blank: bool = False):
        super().__init__(application=app, title="TermSpace")
        self.app = app
        self.title_text = (data or {}).get("window_title", "")
        self.set_title(self.title_text or "TermSpace")
        self.set_default_size((data or {}).get("width", 1100), (data or {}).get("height", 700))
        self.set_size_request(420, 280)
        self.set_icon_name(app.get_application_id())
        self.tabs: list[Tab] = []
        self.closed = False
        self.confirming = False
        self.search_pane = None
        self.layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(self.layout)
        header = Gtk.HeaderBar(css_classes=["app-header"])
        heading = Gtk.Label(label=self.get_title(), css_classes=["wordmark"], width_chars=22, max_width_chars=48, ellipsize=Pango.EllipsizeMode.END)
        self.connect("notify::title", lambda *_: heading.set_text(self.get_title()))
        header.set_title_widget(heading)
        self.set_titlebar(header)
        header.pack_start(button("tab-new-symbolic", "New tab", self.add_tab))
        header.pack_start(button("view-dual-symbolic", "Split focused pane",
                                 lambda: self.perform("split-default")))
        self.quick = Gtk.MenuButton(icon_name="pan-down-symbolic", tooltip_text="Window and workspace actions",
                                    css_classes=["flat"])
        self.quick.update_property([Gtk.AccessibleProperty.LABEL], ["Window and workspace actions"])
        self.quick.set_menu_model(menu(self.quick, "quick", [
            ("New window", self.app.open_window),
            ("Open window in directory…", self.open_directory),
            ("Rename window", self.rename),
            ("Rename active tab", lambda: self.current().edit("name") if self.current() else None),
            ("New tab with profile…", self.new_profile_tab),
            ("Save workspace", lambda: self.app.save_workspace(self)),
            ("Manage workspaces…", lambda: self.app.workspace_manager(self)),
            ("Fullscreen", lambda: self.perform("fullscreen")),
            ("About TermSpace", lambda: self.app.about(self)),
        ]))
        header.pack_end(button("emblem-system-symbolic", "Settings", lambda: self.app.preferences(self)))
        header.pack_end(self.quick)
        self.notebook = Gtk.Notebook(scrollable=True, hexpand=True, vexpand=True, css_classes=["terminal-tabs"])
        self.notebook.connect("switch-page", self.switched)
        self.notebook.connect("page-reordered", self.reordered)
        self.layout.append(self.notebook)
        self.build_search()
        status = Gtk.Box(spacing=10, css_classes=["status-bar"])
        status.append(Gtk.Image(icon_name="utilities-terminal-symbolic"))
        self.status = Gtk.Label(xalign=0, hexpand=True)
        self.session_state = Gtk.Label(xalign=1, css_classes=["dim-label"])
        status.append(self.status)
        status.append(self.session_state)
        self.layout.append(status)
        self.status_bar = status
        status.set_visible(self.app.settings["status_bar"])
        self.connect("close-request", self.request_close)
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.key)
        self.add_controller(keys)
        self.install_actions()
        if data:
            for tab in data["tabs"]:
                self.add_tab(tab, commands=commands, focus=False)
            self.notebook.set_current_page(0)
            if data["maximized"]:
                self.maximize()
        elif not blank:
            self.add_tab(cwd=cwd, focus=False)
        self.refresh_status()

    def install_actions(self):
        for name in model.SHORTCUTS:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda *_args, name=name: self.perform(name))
            self.add_action(action)

    def key(self, _controller, key, _code, modifiers) -> bool:
        masked = modifiers & Gtk.accelerator_get_default_mod_mask()
        key = Gdk.keyval_to_lower(key)
        if key == Gdk.KEY_ISO_Left_Tab:
            key = Gdk.KEY_Tab
        action = self.app.keys.get((key, int(masked)))
        # Ctrl+plus often arrives with Shift on physical keyboards.
        if not action and key == Gdk.KEY_plus:
            action = self.app.keys.get((key, int(masked & ~Gdk.ModifierType.SHIFT_MASK)))
        if action:
            self.activate_action(f"win.{action}", None)
            return True
        return False

    def current(self) -> Tab | None:
        index = self.notebook.get_current_page()
        if index >= 0:
            page = self.notebook.get_nth_page(index)
            return next((tab for tab in self.tabs if tab.page is page), None)
        return None

    def perform(self, action: str) -> None:
        tab = self.current()
        pane = tab.active if tab else None
        if action == "new-window":
            self.app.open_window()
        elif action == "new-tab":
            self.add_tab()
        elif action == "save-workspace":
            self.app.save_workspace(self)
        elif action == "fullscreen":
            self.unfullscreen() if self.is_fullscreen() else self.fullscreen()
        elif action in ("next-tab", "prev-tab") and self.tabs:
            self.notebook.set_current_page((self.notebook.get_current_page()
                                            + (1 if action == "next-tab" else -1)) % len(self.tabs))
        elif pane:
            terminal = pane.session.terminal
            if action in ("split-h", "split-v", "split-default"):
                tab.split(pane, {"split-h": "left-right", "split-v": "top-bottom"}.get(
                    action, self.app.settings["split_direction"]))
            elif action == "close-pane":
                self.close_pane(pane)
            elif action == "rename-pane":
                pane.rename()
            elif action == "maximize-pane":
                tab.maximize(pane)
            elif action == "copy":
                terminal.copy_clipboard_format(Vte.Format.TEXT)
            elif action == "paste":
                pane.session.paste()
            elif action == "search":
                self.show_search(pane)
            elif action.startswith("focus-"):
                self.focus_direction(tab, action.removeprefix("focus-"))
            elif action in ("zoom-in", "zoom-out", "zoom-reset"):
                scale = terminal.get_font_scale()
                terminal.set_font_scale({"zoom-in": min(3, scale * 1.1), "zoom-out": max(.5, scale / 1.1),
                                          "zoom-reset": 1}[action])

    def focus_direction(self, tab: Tab, direction: str):
        if tab.maximized:
            return
        _, active = tab.active.box.compute_bounds(tab.page)
        if active is None:
            return
        horizontal = direction in ("left", "right")
        sign = 1 if direction in ("right", "down") else -1
        candidates = []

        def center(bounds):
            return bounds.get_x() + bounds.get_width() / 2, bounds.get_y() + bounds.get_height() / 2
        ax, ay = center(active)
        for pane in panes(tab.tree):
            success, bounds = pane.box.compute_bounds(tab.page)
            if not success or pane is tab.active:
                continue
            x, y = center(bounds)
            along, across = (x - ax, y - ay) if horizontal else (y - ay, x - ax)
            if sign * along > 1:
                candidates.append((abs(along) + 2 * abs(across), pane))
        if candidates:
            tab.focus(min(candidates, key=lambda pair: pair[0])[1])

    def add_tab(self, data: dict | None = None, *, cwd: str = "", profile: str = "",
                commands: dict | None = None, focus: bool = True):
        profile_name = profile or self.app.settings["default_profile"]
        if data is None:
            data = {"name": "", "accent": "", "layout": model.leaf(self.app.resolve_cwd(cwd, profile_name),
                                                                   profile_name)}
        if not self.allow(tabs_count=1, panes_count=sum(1 for _ in model.leaves(data["layout"]))):
            return None
        tab = Tab(self, data, commands or {})
        self.attach(tab)
        if focus:
            self.notebook.set_current_page(self.notebook.page_num(tab.page))
            tab.focus()
        return tab

    def attach(self, tab: Tab) -> None:
        tab.window = self
        self.tabs.append(tab)
        self.notebook.append_page(tab.page, tab.label)
        self.notebook.set_tab_reorderable(tab.page, True)
        self.refresh_status()

    def detach_tab(self, tab: Tab) -> None:
        self.tabs.remove(tab)
        self.notebook.remove_page(self.notebook.page_num(tab.page))
        self.refresh_status()

    def allow(self, *, tabs_count: int = 0, panes_count: int = 0) -> bool:
        limits = self.app.settings["limits"]
        if len(self.tabs) + tabs_count <= limits["tabs"] and self.app.pane_count() + panes_count <= limits["panes"]:
            return True
        message(self, "Session limit reached", "Close a tab or pane, or adjust the limits in Settings.")
        return False

    def refresh_status(self) -> None:
        if not hasattr(self, "status"):
            return
        tab = self.current()
        pane = tab.active if tab else None
        count = sum(session.session.state in ("running", "starting") for tab in self.tabs for session in panes(tab.tree))
        self.status.set_text(f"{count} active terminal" + ("" if count == 1 else "s"))
        self.session_state.set_text((f"{model.title(pane.session.shell.rsplit('/', 1)[-1], 'Shell')}  ·  "
                                     f"{pane.session.state.capitalize()}") if pane else "")
        self.status.set_tooltip_text("Active terminal processes in this window")

    def switched(self, _notebook, child, _index) -> None:
        tab = next((tab for tab in self.tabs if tab.page is child), None)
        if tab:
            def focus():
                if not self.closed and self.current() is tab and not self.search_box.get_visible():
                    tab.focus()
                return GLib.SOURCE_REMOVE
            GLib.idle_add(focus)
        if hasattr(self, "search_box"):
            self.hide_search(focus=False)
        GLib.idle_add(lambda: (self.refresh_status(), GLib.SOURCE_REMOVE)[1])

    def reordered(self, notebook, _child, _index) -> None:
        self.tabs.sort(key=lambda tab: notebook.page_num(tab.page))

    def rename(self) -> None:
        def update(text):
            try:
                self.title_text = model.label(text, empty=True)
                self.set_title(self.title_text or "TermSpace")
            except model.Invalid as exc:
                message(self, "Invalid window name", str(exc))
        prompt(self, "Rename window", self.title_text, update)

    def open_directory(self) -> None:
        chooser = Gtk.FileChooserNative.new("Choose a working directory", self,
                                             Gtk.FileChooserAction.SELECT_FOLDER, "Open", "Cancel")

        def response(_chooser, result):
            selected = chooser.get_file() if result == Gtk.ResponseType.ACCEPT else None
            chooser.destroy()
            if selected and selected.get_path():
                self.app.open_window(cwd=selected.get_path())
        chooser.connect("response", response)
        chooser.show()

    def new_profile_tab(self) -> None:
        names = self.app.profile_names()
        from .preferences import select
        select(self, "New tab with profile", names, "Open tab",
               lambda index: self.add_tab(profile=names[index]))

    def confirm(self, sessions, perform) -> None:
        active = any(pane.session.state in ("starting", "running") for pane in sessions)
        if self.confirming:
            return
        if not active or not self.app.settings["confirm_close"]:
            perform()
            return
        self.confirming = True

        def answered(response, _text):
            self.confirming = False
            if response == 1 and not self.closed:
                perform()
        ask(self, "Close terminal sessions?", "Running jobs in these sessions may be terminated.",
            [(Gtk.ResponseType.CANCEL, "Cancel"), (1, "Close sessions")], answered)

    def close_pane(self, pane) -> None:
        tab = pane.tab
        if len(list(panes(tab.tree))) == 1:
            self.close_tabs([tab])
            return

        def close():
            if self.search_pane is pane:
                self.hide_search(focus=False)
            tab.remove(pane)
        self.confirm([pane], close)

    def close_tabs(self, tabs: list[Tab]) -> None:
        if not tabs:
            return
        if len(tabs) == len(self.tabs):
            self.request_close(self)
            return

        def close():
            self.hide_search(focus=False)
            for tab in tabs:
                self.detach_tab(tab)
                tab.close()
        self.confirm([pane for tab in tabs for pane in panes(tab.tree)], close)

    def request_close(self, _window) -> bool:
        if self.closed:
            return False

        def close():
            self.app.remember_window(self)
            self.dispose_sessions()
            self.destroy()
        self.confirm([pane for tab in self.tabs for pane in panes(tab.tree)], close)
        return True

    def dispose_sessions(self) -> None:
        self.closed = True
        self.hide_search(focus=False)
        for tab in self.tabs[:]:
            self.detach_tab(tab)
            tab.close()

    def build_search(self) -> None:
        self.search_box = Gtk.Box(spacing=6, css_classes=["search-bar"], visible=False)
        self.search_entry = Gtk.SearchEntry(placeholder_text="Find in terminal", max_width_chars=35, hexpand=True)
        self.search_entry.connect("activate", lambda *_: self.find(previous=False))
        self.search_entry.connect("stop-search", lambda *_: self.hide_search())
        self.search_entry.connect("search-changed", lambda *_: self.find(previous=False, navigate=False))
        self.search_case = Gtk.CheckButton(label="Case sensitive")
        self.search_regex = Gtk.CheckButton(label="Regex")
        for toggle in (self.search_case, self.search_regex):
            toggle.connect("toggled", lambda *_: self.find(previous=False, navigate=False))
        for child in (self.search_entry, self.search_case, self.search_regex,
                      button("go-up-symbolic", "Previous search match", lambda: self.find(previous=True)),
                      button("go-down-symbolic", "Next search match", lambda: self.find(previous=False)),
                      button("window-close-symbolic", "Close search", self.hide_search)):
            self.search_box.append(child)
        self.search_status = Gtk.Label(css_classes=["dim-label"], visible=False)
        self.layout.append(self.search_box)
        self.layout.append(self.search_status)

    def show_search(self, pane) -> None:
        self.search_pane = pane
        self.search_box.set_visible(True)
        self.search_entry.grab_focus()

    def find(self, *, previous: bool, navigate: bool = True) -> None:
        pane = self.search_pane
        if not pane:
            return
        query = self.search_entry.get_text()
        terminal = pane.session.terminal
        try:
            pane.session.search(query, self.search_case.get_active(), self.search_regex.get_active())
            found = terminal.search_find_previous() if previous else terminal.search_find_next()
            status = "No match" if query and not found else ""
        except (GLib.Error, model.Invalid) as exc:
            pane.session.search("", False, False)
            status = str(exc) if isinstance(exc, model.Invalid) else "Invalid regular expression."
        if not navigate and not query:
            status = ""
        self.search_status.set_text(status)
        self.search_status.set_visible(bool(status))

    def hide_search(self, *, focus: bool = True) -> None:
        if self.search_pane:
            self.search_pane.session.search("", False, False)
            self.search_pane = None
        self.search_box.set_visible(False)
        self.search_status.set_visible(False)
        if focus and (tab := self.current()):
            tab.focus()

    def move_pane(self, pane) -> None:
        from .preferences import select
        targets = [other for other in panes(pane.tab.tree) if other is not pane]
        tabs = [tab for tab in self.tabs if tab is not pane.tab]
        items = [f"Swap with {other.name}" for other in targets]
        items += [f"Move into {tab.heading.get_text()}" for tab in tabs]
        if not items:
            message(self, "No pane destination", "Create another tab or split this pane first.")
            return

        def move(index):
            source = pane.tab
            if index < len(targets):
                source.swap(pane, targets[index])
                return
            target = tabs[index - len(targets)]
            anchor = target.active
            from .layout import depth
            if depth(target.tree) >= self.app.settings["limits"]["depth"]:
                message(self, "Split limit reached", "The destination tab is at the split depth limit.")
                return
            self.hide_search(focus=False)
            source.detach()
            target.detach()
            source.maximized = target.maximized = None
            source.tree = replace(source.tree, pane, None)
            if source.tree:
                source.mount()
                source.focus(next(panes(source.tree)))
            else:
                self.detach_tab(source)
                source.close()
            pane.tab = target
            target.tree = replace(target.tree, anchor, Split(self.app.settings["split_direction"], .5, anchor, pane))
            target.mount()
            self.notebook.set_current_page(self.notebook.page_num(target.page))
            target.focus(pane)
        select(self, "Move or swap pane", items, "Apply", move)

    def edit_commands(self, pane) -> None:
        from .preferences import edit_text
        def save(value):
            try:
                pane.data["startup_commands"] = model.commands([value])
            except model.Invalid as exc:
                message(self, "Invalid startup command", str(exc))
        edit_text(self, "Pane startup commands", "\n".join(pane.data["startup_commands"]),
                  "Save this script with a workspace. It runs only after review when opening that workspace.", save)

    def snapshot(self, name: str, tab: Tab | None = None) -> dict:
        width, height = self.get_default_size()
        if not self.is_maximized() and not self.is_fullscreen():
            width = self.get_width() or width
            height = self.get_height() or height
        return {"schema_version": 1, "name": name, "window_title": self.title_text,
                "width": max(420, width), "height": max(280, height), "maximized": self.is_maximized(),
                "tabs": [item.snapshot() for item in ([tab] if tab else self.tabs)]}

    def apply_settings(self) -> None:
        self.status_bar.set_visible(self.app.settings["status_bar"])
        for tab in self.tabs:
            for pane in panes(tab.tree):
                pane.apply_settings()
