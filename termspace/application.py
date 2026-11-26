"""GTK lifecycle and transactions for local workspaces and profiles."""

import json
import os
import platform
from pathlib import Path

import gi

from . import APP_ID, VERSION, model
from .dialogs import ask, choose_file, message, prompt
from .layout import panes
from .native import Gio, GLib, Gtk, Vte
from .preferences import accelerator_map, preferences, select
from .store import Store, catalog, export_file, import_file, xdg
from .window import Window


class Application(Gtk.Application):
    def __init__(self, parse, *, config: Store | None = None, state: Store | None = None,
                 non_unique: bool = False):
        flags = Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        if non_unique:
            flags |= Gio.ApplicationFlags.NON_UNIQUE
        super().__init__(application_id=APP_ID, flags=flags)
        self.parse = parse
        self.config = config or Store()
        self.state = state or Store(xdg("XDG_STATE_HOME", Path.home() / ".local/state") / "termspace",
                                    "layout.json")
        self.catalog = catalog({"schema_version": 1})
        self.settings = self.catalog["settings"]
        self.keys = accelerator_map(self.settings["shortcuts"])
        self.startup_error = ""
        self.started = False

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_path(str(Path(__file__).with_name("style.css")))
        from .native import Gdk
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        try:
            self.load_catalog(catalog(self.config.load()))
        except (OSError, model.Invalid) as exc:
            self.startup_error = self.error_text(exc)
        self.apply_theme()

    def do_activate(self) -> None:
        if windows := self.windows():
            windows[0].present()
        else:
            self.initial_window()

    def do_command_line(self, command_line) -> int:
        try:
            args = self.parse(command_line.get_arguments()[1:])
            if args.version or args.help:
                return 0
            if args.workspace:
                self.load_workspace(args.workspace, None, review=False)
            elif args.working_directory is not None:
                base = os.fsdecode(command_line.get_cwd()) if command_line.get_cwd() else None
                self.build_window(cwd=model.directory(args.working_directory, base))
            elif args.new_window:
                self.build_window()
            else:
                self.activate()
        except (model.Invalid, OSError) as exc:
            command_line.printerr_literal("TermSpace: " + self.error_text(exc) + "\n")
            return 2
        except SystemExit:
            command_line.printerr_literal("TermSpace: invalid launch options. See --help.\n")
            return 2
        return 0

    def windows(self) -> list[Window]:
        return [window for window in self.get_windows() if isinstance(window, Window) and not window.closed]

    def pane_count(self) -> int:
        return sum(1 for window in self.windows() for tab in window.tabs for _ in panes(tab.tree))

    def initial_window(self) -> None:
        if not self.started:
            self.started = True
            try:
                if self.settings["restore_layout"]:
                    data = self.state.load()
                    if "tabs" in data:
                        saved = model.workspace(data, self.settings["limits"])
                        self.open_layout(saved)
                        return
                if self.settings["default_workspace"]:
                    self.load_workspace(self.settings["default_workspace"], None, review=False)
                    return
            except (OSError, model.Invalid) as exc:
                self.startup_error = self.error_text(exc)
        self.open_window()

    def open_window(self, *, cwd: str = "", blank: bool = False):
        try:
            if cwd:
                cwd = model.directory(cwd)
            return self.build_window(cwd=cwd, blank=blank)
        except (OSError, model.Invalid) as exc:
            self.error(self.windows()[0] if self.windows() else None, "Could not open window", exc)
            return None

    def build_window(self, data=None, commands=None, *, cwd="", blank=False):
        limits = self.settings["limits"]
        model.require(len(self.windows()) < limits["windows"], "Window limit reached.")
        count = sum(1 for tab in data["tabs"] for _ in model.leaves(tab["layout"])) if data else int(not blank)
        model.require(self.pane_count() + count <= limits["panes"], "Pane limit reached.")
        self.started = True
        window = Window(self, data, commands, cwd=cwd, blank=blank)
        window.present()
        if (active := window.current()) is not None:
            active.focus()
        if self.startup_error:
            message(window, "Configuration could not be loaded", self.startup_error +
                    " The existing file is preserved. Fix its permissions or move it aside to save new settings.")
            self.startup_error = ""
        return window

    def move_tab(self, tab):
        source = tab.window
        target = self.open_window(blank=True)
        if target is None:
            return
        source.hide_search(focus=False)
        tab.context_menu.popdown()
        source.detach_tab(tab)
        target.attach(tab)
        target.notebook.set_current_page(0)
        tab.focus()
        if not source.tabs:
            source.dispose_sessions()
            source.destroy()

    def builtin_profiles(self) -> dict:
        named = {name: model.PROFILE | {"shell": executable}
                 for name, executable in model.SHELLS.items() if model.executable(executable)}
        return {model.DEFAULT_PROFILE: model.PROFILE.copy(), **named,
                "Custom Shell": model.PROFILE.copy()}

    def profile_names(self) -> list[str]:
        builtins = self.builtin_profiles()
        return [*builtins, *sorted(self.catalog["profiles"].keys() - builtins.keys())]

    def profile(self, name: str) -> dict:
        builtins = self.builtin_profiles()
        if name in self.catalog["profiles"] and (name not in builtins or name == "Custom Shell"):
            return model.profile(self.catalog["profiles"][name], check_paths=False)
        return builtins.get(name, builtins[model.DEFAULT_PROFILE])

    def resolve_cwd(self, value: str, name: str) -> str:
        for path in (value, self.profile(name)["working_directory"], self.settings["default_directory"],
                     str(Path.home()), "/"):
            if path:
                try:
                    return model.directory(path)
                except model.Invalid:
                    pass
        return "/"

    @staticmethod
    def error_text(exc: Exception) -> str:
        return str(exc) if isinstance(exc, model.Invalid) else (
            "The local file operation failed. Check access, disk space, and whether the destination already exists.")

    def error(self, parent, title: str, exc: Exception) -> None:
        if parent:
            message(parent, title, self.error_text(exc))
        else:
            import sys
            print(f"TermSpace: {self.error_text(exc)}", file=sys.stderr)

    def load_catalog(self, value: dict) -> None:
        keys = accelerator_map(value["settings"]["shortcuts"])
        self.catalog, self.settings, self.keys = value, value["settings"], keys

    def transaction(self, change) -> None:
        def mutate(raw):
            value = catalog(raw)
            accelerator_map(value["settings"]["shortcuts"])
            change(value)
            catalog(value)
            return value
        self.load_catalog(self.config.update(mutate))

    def apply_theme(self) -> None:
        settings = Gtk.Settings.get_default()
        if self.settings["theme"] == "system":
            settings.reset_property("gtk-application-prefer-dark-theme")
        else:
            settings.set_property("gtk-application-prefer-dark-theme", self.settings["theme"] == "dark")
        for window in self.windows():
            window.apply_settings()

    def preferences(self, parent) -> None:
        preferences(self, parent)

    def save_settings(self, data: dict) -> None:
        self.transaction(lambda value: value.update(settings=data))
        self.apply_theme()

    def save_profile(self, name: str, original: str, data: dict) -> None:
        def change(value):
            profiles = value["profiles"]
            model.require(name not in profiles or name == original, "A profile with this name exists.")
            if original and original != name:
                model.require(original in profiles, "The profile was already removed.")
                profiles.pop(original)
                if value["settings"]["default_profile"] == original:
                    value["settings"]["default_profile"] = name
                for entry in value["workspaces"].values():
                    for tab in entry.get("tabs", []):
                        for pane in model.leaves(tab["layout"]):
                            if pane["profile"] == original:
                                pane["profile"] = name
            profiles[name] = data
        self.transaction(change)

    def delete_profile(self, parent, name):
        try:
            def change(value):
                value["profiles"].pop(name, None)
                if value["settings"]["default_profile"] == name:
                    value["settings"]["default_profile"] = model.DEFAULT_PROFILE
            self.transaction(change)
        except (OSError, model.Invalid) as exc:
            self.error(parent, "Could not delete profile", exc)

    def remember_window(self, window) -> None:
        if not self.settings["restore_layout"] or not window.tabs:
            return
        try:
            snapshot = model.workspace(window.snapshot("Previous layout"), self.settings["limits"])
            self.state.update(lambda _value: snapshot)
        except (OSError, model.Invalid) as exc:
            self.startup_error = self.error_text(exc)

    def open_layout(self, data: dict, commands: dict | None = None):
        return self.build_window(data, commands)

    def load_workspace(self, name: str, parent, *, review: bool, replace_window: bool = False):
        if name not in self.catalog["workspaces"]:
            raise model.Invalid("Workspace was not found.")
        workspace = model.workspace(self.catalog["workspaces"][name], self.settings["limits"])
        prepared = {}
        details = []
        for tab in workspace["tabs"]:
            for pane in model.leaves(tab["layout"]):
                pane["working_directory"] = self.resolve_cwd(pane["working_directory"], pane["profile"])
                if review:
                    profile = self.profile(pane["profile"])
                    commands = [*profile["startup_commands"], *pane["startup_commands"]]
                    if commands:
                        script = "\n".join(commands)
                        prepared[pane["id"]] = script
                        details.append(f"Tab: {tab['name'] or 'Terminal'}  •  Pane: {pane['name'] or 'Terminal'} "
                                       f"({pane['id']})\n"
                                       f"Directory: {pane['working_directory']}\n"
                                       f"Shell: {profile['shell'] or model.login_shell()}\n"
                                       f"Arguments: {json.dumps(profile['arguments'], ensure_ascii=False)}\n\n{script}")

        def open_selected(approved):
            def open_window():
                try:
                    if not replace_window:
                        self.open_layout(workspace, prepared if approved else None)
                        return
                    remaining = self.pane_count() - sum(1 for tab in parent.tabs for _ in panes(tab.tree))
                    incoming = sum(1 for tab in workspace["tabs"] for _ in model.leaves(tab["layout"]))
                    model.require(remaining + incoming <= self.settings["limits"]["panes"], "Pane limit reached.")
                    parent.hide_search(focus=False)
                    for tab in parent.tabs[:]:
                        parent.detach_tab(tab)
                        tab.close()
                    parent.title_text = workspace["window_title"]
                    parent.set_title(parent.title_text or "TermSpace")
                    parent.set_default_size(workspace["width"], workspace["height"])
                    parent.maximize() if workspace["maximized"] else parent.unmaximize()
                    for tab in workspace["tabs"]:
                        parent.add_tab(tab, commands=prepared if approved else None, focus=False)
                    parent.notebook.set_current_page(0)
                except (OSError, model.Invalid) as exc:
                    if not parent:
                        raise
                    self.error(parent, "Could not open workspace", exc)
            if replace_window:
                parent.confirm([pane for tab in parent.tabs for pane in panes(tab.tree)], open_window)
            else:
                open_window()

        if prepared:
            ask(parent, "Review workspace startup commands",
                "Commands run in their listed panes. Each pane runs its script until the shell exits.",
                [(Gtk.ResponseType.CANCEL, "Cancel"), (2, "Open without running"), (1, "Run and open")],
                lambda response, _: open_selected(response == 1) if response in (1, 2) else None,
                default=2, text="\n\n────────\n\n".join(details), monospace=True)
        else:
            open_selected(False)

    def save_workspace(self, parent, tab=None, *, update=""):
        def save(name):
            self.workspace_operation(parent, lambda: self.put_workspace(parent.snapshot(model.label(name), tab),
                                                                        replace=update))
        if update:
            ask(parent, "Update workspace?", f"Replace the saved layout for {update} with this window?",
                [(Gtk.ResponseType.CANCEL, "Cancel"), (1, "Update")],
                lambda answer, _: save(update) if answer == 1 else None)
        else:
            prompt(parent, "Save workspace", "", save, "Save the layout, profiles, and working directories.")

    def put_workspace(self, data, *, replace=""):
        clean = model.workspace(data, self.settings["limits"])

        def change(value):
            workspaces = value["workspaces"]
            name = clean["name"]
            model.require(name not in workspaces or name == replace, "A workspace with this name exists.")
            model.require(not replace or replace in workspaces, "The workspace was already removed.")
            if replace and replace != name:
                del workspaces[replace]
                if value["settings"]["default_workspace"] == replace:
                    value["settings"]["default_workspace"] = name
            workspaces[name] = clean
        self.transaction(change)

    def workspace_operation(self, parent, callback):
        try:
            return callback()
        except (OSError, model.Invalid) as exc:
            self.error(parent, "Workspace action failed", exc)
            return None

    def workspace_manager(self, parent):
        actions = {
            "Open in this window": lambda name: self.load_workspace(name, parent, review=True, replace_window=True),
            "Open in new window": lambda name: self.load_workspace(name, parent, review=True),
            "Update from this window": lambda name: self.save_workspace(parent, update=name),
            "Set as default": lambda name: self.transaction(lambda value: value["settings"].update(default_workspace=name)),
            "Rename": lambda name: self.rename_workspace(parent, name, duplicate=False),
            "Duplicate": lambda name: self.rename_workspace(parent, name, duplicate=True),
            "Delete": lambda name: self.delete_workspace(parent, name),
            "Export JSON": lambda name: self.export_workspace(parent, name),
        }
        names = sorted(self.catalog["workspaces"])
        dialog = Gtk.Dialog(title="Workspaces", transient_for=parent, modal=True, destroy_with_parent=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        from .preferences import margins
        dialog.get_content_area().append(margins(box, 16))
        default = self.settings["default_workspace"]
        saved = Gtk.DropDown.new_from_strings([name + ("  (default)" if name == default else "") for name in names]
                                               or ["No saved workspaces"])
        modes = Gtk.DropDown.new_from_strings(list(actions))
        for element in (Gtk.Label(label="Saved workspace", xalign=0), saved,
                        Gtk.Label(label="Action", xalign=0), modes):
            box.append(element)
        saved.update_property([Gtk.AccessibleProperty.LABEL], ["Saved workspace"])
        modes.update_property([Gtk.AccessibleProperty.LABEL], ["Workspace action"])
        saved.set_sensitive(bool(names))
        modes.set_sensitive(bool(names))
        dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        dialog.add_button("Import…", 2)
        dialog.add_button("Save current…", 3)
        dialog.add_button("Apply", 1).set_sensitive(bool(names))

        def response(_dialog, result):
            index, action = saved.get_selected(), modes.get_selected()
            dialog.destroy()
            if result == 1 and index < len(names):
                self.workspace_operation(parent, lambda: list(actions.values())[action](names[index]))
            elif result == 2:
                self.import_workspace(parent)
            elif result == 3:
                self.save_workspace(parent)
        dialog.connect("response", response)
        dialog.present()

    def rename_workspace(self, parent, name, *, duplicate):
        prompt(parent, "Duplicate workspace" if duplicate else "Rename workspace", name,
               lambda text: self.workspace_operation(parent, lambda: self.put_workspace(
                   dict(self.catalog["workspaces"][name], name=model.label(text)),
                   replace="" if duplicate else name)))

    def delete_workspace(self, parent, name):
        def delete():
            def change(value):
                value["workspaces"].pop(name, None)
                if value["settings"]["default_workspace"] == name:
                    value["settings"]["default_workspace"] = ""
            self.transaction(change)
        ask(parent, "Delete workspace?", f"Remove {name} from saved workspaces?",
            [(Gtk.ResponseType.CANCEL, "Cancel"), (1, "Delete")],
            lambda answer, _: self.workspace_operation(parent, delete) if answer == 1 else None)

    def export_workspace(self, parent, name):
        data = self.catalog["workspaces"][name]
        choose_file(parent, save=True, name="termspace-workspace.json",
                    callback=lambda path: self.workspace_operation(parent, lambda: export_file(
                        path, data, self.settings["limits"]["file_bytes"])))

    def import_workspace(self, parent):
        def load(path):
            limits = self.settings["limits"]
            raw = import_file(path, limits["file_bytes"])
            data = model.workspace(raw, limits, imported=True)
            items = [pane for tab in data["tabs"] for pane in model.leaves(tab["layout"])]
            preview = "\n".join(f"{pane['name'] or 'Terminal'}  •  "
                                f"{pane['working_directory'] or 'Default working directory'}" for pane in items)
            ask(parent, "Review workspace import",
                f"{data['name']} · {len(data['tabs'])} tabs · {len(items)} panes. "
                "Imported panes use Default Shell. Startup commands are removed.",
                [(Gtk.ResponseType.CANCEL, "Cancel"), (1, "Import")],
                lambda answer, _: self.workspace_operation(parent, lambda: self.put_workspace(data))
                if answer == 1 else None, text=preview, monospace=True)
        choose_file(parent, save=False, name="", callback=lambda path: self.workspace_operation(parent, lambda: load(path)))

    def about(self, parent):
        gtk = ".".join(str(value) for value in (Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version()))
        vte = ".".join(str(value) for value in (Vte.get_major_version(), Vte.get_minor_version(), Vte.get_micro_version()))
        from .native import Gdk
        display = Gdk.Display.get_default()
        message(parent, f"TermSpace {VERSION}",
                f"MIT license\nNative Linux terminal workspaces\n\nGTK {gtk}\nVTE {vte} (GI 3.91)\n"
                f"Python {platform.python_version()}\nPyGObject {gi.__version__}\n"
                f"Display: {display.__gtype__.name}\nArchitecture: {platform.machine()}")
