"""Native settings, profile, and chooser dialogs."""

import json

from . import model
from .dialogs import ask, message, prompt
from .native import Gdk, Gtk


def select(parent, title: str, names: list[str], button: str, callback) -> None:
    if not names:
        message(parent, title, "There are no entries.")
        return
    dialog = Gtk.Dialog(title=title, transient_for=parent, modal=True, destroy_with_parent=True)
    dropdown = Gtk.DropDown.new_from_strings(names)
    margins(dropdown, 16)
    dialog.get_content_area().append(dropdown)
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button(button, 1)

    def response(_dialog, action):
        index = dropdown.get_selected()
        dialog.destroy()
        if action == 1 and index < len(names):
            callback(index)
    dialog.connect("response", response)
    dialog.present()


def margins(widget, amount: int = 12):
    for side in ("start", "end", "top", "bottom"):
        getattr(widget, f"set_margin_{side}")(amount)
    return widget


def edit_text(parent, title: str, value: str, description: str, callback):
    dialog = Gtk.Dialog(title=title, transient_for=parent, modal=True, destroy_with_parent=True)
    dialog.set_default_size(520, 320)
    area = dialog.get_content_area()
    area.append(margins(Gtk.Label(label=description, wrap=True, xalign=0)))
    view = Gtk.TextView(monospace=True, wrap_mode=Gtk.WrapMode.CHAR)
    view.get_buffer().set_text(value)
    scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
    scroll.set_child(view)
    area.append(margins(scroll))
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("Save", 1)

    def response(_dialog, code):
        buffer = view.get_buffer()
        text = buffer.get_text(*buffer.get_bounds(), False)
        dialog.destroy()
        if code == 1:
            callback(text)
    dialog.connect("response", response)
    dialog.present()


def accelerator_map(values: dict) -> dict:
    from .native import Gdk
    result = {}
    reservations = {Gdk.KEY_Insert, Gdk.KEY_KP_Insert}
    blocked = (Gdk.ModifierType.SUPER_MASK | Gdk.ModifierType.HYPER_MASK | Gdk.ModifierType.META_MASK)
    for action, accelerator in values.items():
        if not accelerator:
            continue
        valid, key, mods = Gtk.accelerator_parse(accelerator)
        key = Gdk.keyval_to_lower(key)
        control = Gdk.ModifierType.CONTROL_MASK
        shift = Gdk.ModifierType.SHIFT_MASK
        alt = Gdk.ModifierType.ALT_MASK
        protected = (key in reservations or mods & blocked
                     or mods == control and key not in (Gdk.KEY_Tab, Gdk.KEY_plus, Gdk.KEY_minus, Gdk.KEY_0)
                     or mods == (control | shift) and key in (Gdk.KEY_Up, Gdk.KEY_Down)
                     or mods == alt and key not in (Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Left, Gdk.KEY_Right)
                     or not mods and not Gdk.KEY_F1 <= key <= Gdk.KEY_F35
                     or mods and not mods & (control | alt))
        pair = (key, int(mods))
        model.require(valid and key and not protected, f"Shortcut for {action.replace('-', ' ')} is reserved or invalid.")
        if key == Gdk.KEY_plus:
            other = (key, int(mods ^ shift))
        else:
            other = pair
        model.require(pair not in result and other not in result, "Two actions use the same shortcut.")
        result[pair] = action
    return result


class Form:
    def __init__(self):
        self.grid = margins(Gtk.Grid(column_spacing=18, row_spacing=10))
        self.rows = {}

    def add(self, key: str, text: str, value, *, choices=None, bounds=None, secret: bool = False):
        if choices:
            options = list(choices)
            widget = Gtk.DropDown.new_from_strings(options)
            widget.set_selected(options.index(value) if value in options else 0)
            getter = lambda: options[widget.get_selected()]
        elif type(value) is bool:
            widget = Gtk.Switch(active=value, halign=Gtk.Align.START)
            getter = widget.get_active
        elif bounds:
            widget = Gtk.SpinButton.new_with_range(*bounds, 1)
            widget.set_value(value)
            getter = widget.get_value_as_int
        else:
            widget = Gtk.Entry(text=value, hexpand=True, visibility=not secret, max_length=32768)
            getter = widget.get_text
        label = Gtk.Label(label=text, xalign=0, wrap=True, max_width_chars=29)
        widget.update_property([Gtk.AccessibleProperty.LABEL], [text])
        self.grid.attach(label, 0, len(self.rows), 1, 1)
        self.grid.attach(widget, 1, len(self.rows), 1, 1)
        self.rows[key] = (widget, getter)
        return widget

    def values(self) -> dict:
        return {key: getter() for key, (_widget, getter) in self.rows.items()}

    def scroll(self):
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(self.grid)
        return scroll


def preferences(app, parent):
    dialog = Gtk.Dialog(title="TermSpace Settings", transient_for=parent, modal=True, destroy_with_parent=True)
    dialog.set_default_size(670, 530)
    stack = Gtk.Notebook()
    dialog.get_content_area().append(stack)
    data = app.settings
    groups = {
        "General": [
            ("default_profile", "Default shell profile", app.profile_names()),
            ("default_directory", "Default working directory", None),
            ("default_workspace", "Default workspace", ["", *sorted(app.catalog["workspaces"])]),
            ("restore_layout", "Restore last window layout", None),
            ("confirm_close", "Confirm when closing active sessions", None),
            ("status_bar", "Show status bar", None), ("pane_headers", "Show pane headers", None),
        ],
        "Appearance": [("theme", "App appearance", ["dark", "light", "system"]),
                       ("scheme", "Terminal color scheme", model.THEMES)],
        "Terminal": [("split_direction", "Default split direction", ["left-right", "top-bottom"]),
                     ("inherit_directory", "Inherit current directory on split", None)],
        "Privacy": [("hyperlinks", "Allow Ctrl+click to review links", None)],
    }
    forms = []
    for heading, fields in groups.items():
        form = Form()
        forms.append(form)
        for key, label, choices in fields:
            form.add(key, label, data[key], choices=choices)
        if heading == "Appearance":
            form.grid.attach(Gtk.Label(label="Font, cursor and colors can also be set per shell profile.",
                                       wrap=True, xalign=0), 0, len(form.rows), 2, 1)
        if heading == "Terminal":
            profiles = Gtk.Button(label="Manage shell profiles…")
            profiles.connect("clicked", lambda *_: profile_manager(app, dialog))
            form.grid.attach(profiles, 0, len(form.rows), 2, 1)
        if heading == "Privacy":
            form.grid.attach(Gtk.Label(label="Paste review is always on. Imported workspaces use Default Shell. "
                                       "Startup authorization expires after each opening. TermSpace "
                                       "keeps no application logs or terminal transcripts.",
                                       wrap=True, xalign=0, max_width_chars=58), 0, len(form.rows), 2, 1)
            info = Gtk.Button(label="View diagnostics")
            info.connect("clicked", lambda *_: app.about(dialog))
            form.grid.attach(info, 0, len(form.rows) + 1, 2, 1)
        stack.append_page(form.scroll(), Gtk.Label(label=heading))
    shortcuts = Form()
    for key, value in data["shortcuts"].items():
        shortcuts.add(key, key.replace("-", " ").capitalize(), value)
    reset = Gtk.Button(label="Restore default shortcuts")
    reset.connect("clicked", lambda *_: [shortcuts.rows[key][0].set_text(value)
                                         for key, value in model.SHORTCUTS.items()])
    shortcuts.grid.attach(Gtk.Label(label="Use GTK accelerator notation such as <Ctrl><Shift>t. "
                                    "Leave empty to disable.", xalign=0, wrap=True), 0, len(shortcuts.rows), 2, 1)
    shortcuts.grid.attach(reset, 0, len(shortcuts.rows) + 1, 2, 1)
    stack.append_page(shortcuts.scroll(), Gtk.Label(label="Shortcuts"))
    limits = Form()
    for key, value in data["limits"].items():
        limits.add(key, key.replace("_", " ").capitalize(), value,
                   bounds=({"file_bytes": 4096, "scrollback": 0}.get(key, 1), model.HARD_LIMITS[key]))
    stack.append_page(limits.scroll(), Gtk.Label(label="Limits"))
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("Save settings", 1)

    def response(_dialog, code):
        if code != 1:
            dialog.destroy()
            return
        changes = {}
        for form in forms:
            changes.update(form.values())
        try:
            if changes["default_directory"]:
                changes["default_directory"] = model.directory(changes["default_directory"])
            new = model.settings(data | changes | {"shortcuts": shortcuts.values(), "limits": limits.values()})
            app.save_settings(new)
        except (model.Invalid, OSError) as exc:
            app.error(dialog, "Could not save settings", exc)
            return
        dialog.destroy()

    dialog.connect("response", response)
    dialog.present()


def profile_manager(app, parent) -> None:
    names = ["Custom Shell", *sorted(app.catalog["profiles"].keys() - {"Custom Shell"})]
    dialog = Gtk.Dialog(title="Shell profiles", transient_for=parent, modal=True, destroy_with_parent=True)
    box = margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10))
    box.append(Gtk.Label(label="Edit Custom Shell or create a named profile. Bash, Zsh and Fish "
                               "are available when their shells are installed.", wrap=True))
    dropdown = Gtk.DropDown.new_from_strings(names)
    box.append(dropdown)
    dialog.get_content_area().append(box)
    dialog.add_button("Close", Gtk.ResponseType.CLOSE)
    dialog.add_button("New profile", 1)
    dialog.add_button("Edit", 2)
    delete = dialog.add_button("Delete", 3)
    def update_delete(*_args):
        delete.set_sensitive(names[dropdown.get_selected()] in app.catalog["profiles"])
    dropdown.connect("notify::selected", update_delete)
    update_delete()

    def response(_dialog, code):
        index = dropdown.get_selected()
        dialog.destroy()
        if code in (1, 2):
            edit_profile(app, parent, names[index] if code == 2 else "")
        elif code == 3 and index < len(names):
            name = names[index]
            ask(parent, "Delete shell profile?", f"Delete {name}? Saved panes using it will use Default Shell.",
                [(Gtk.ResponseType.CANCEL, "Cancel"), (1, "Delete")],
                lambda answer, _: app.delete_profile(parent, name) if answer == 1 else None)

    dialog.connect("response", response)
    dialog.present()


def edit_profile(app, parent, original: str) -> None:
    dialog = Gtk.Dialog(title="Shell profile", transient_for=parent, modal=True, destroy_with_parent=True)
    dialog.set_default_size(720, 570)
    form = Form()
    data = model.PROFILE | app.catalog["profiles"].get(original, {})
    form.add("name", "Profile name", original)
    labels = {
        "shell": "Absolute shell executable (blank uses login shell)",
        "arguments": "Shell arguments (JSON array)", "working_directory": "Working directory",
        "font": "Font family", "font_size": "Font size", "foreground": "Foreground (#RRGGBB)",
        "background": "Background (#RRGGBB)", "palette": "16 ANSI colors (JSON array)",
        "cursor": "Cursor shape", "blink": "Blinking cursor", "scrollback": "Scrollback lines",
        "bell": "Audible bell", "accent": "Pane accent (#RRGGBB)", "environment": "Environment overrides (JSON object)",
        "startup_commands": "Workspace startup commands (JSON array)",
    }
    for key, label in labels.items():
        value = data[key]
        form.add(key, label, json.dumps(value, ensure_ascii=False) if type(value) in (dict, list) else value,
                 choices=["block", "ibeam", "underline"] if key == "cursor" else None,
                 bounds={"font_size": (6, 48), "scrollback": (0, model.HARD_LIMITS["scrollback"])}.get(key),
                 secret=key == "environment")
    dialog.get_content_area().append(form.scroll())
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("Review profile", 1)

    def response(_dialog, code):
        if code != 1:
            dialog.destroy()
            return
        draft = form.values()
        try:
            name = model.label(draft.pop("name"))
            model.require(name not in app.builtin_profiles() or name == original == "Custom Shell",
                          "Choose a name distinct from built-in profiles.")
            for key in ("arguments", "palette", "environment", "startup_commands"):
                draft[key] = model.decode(('{"field":' + draft[key] + '}').encode(), 32784)["field"]
            result = model.profile(draft)
        except (model.Invalid, OSError) as exc:
            app.error(dialog, "Invalid shell profile", exc)
            return
        executable = result["shell"] or model.login_shell()
        env_names = ", ".join(result["environment"]) or "None"
        sensitive = [key for key in result["environment"] if model.EXECUTION_ENV.search(key)]
        brief = f"Executable: {executable}\nArguments: {json.dumps(result['arguments'], ensure_ascii=False)}\n"
        brief += f"Environment names: {env_names}\nKeep credentials out of profiles."
        if sensitive:
            brief += "\nThese overrides can change program execution: " + ", ".join(sensitive)

        def save(answer, _value):
            if answer != 1:
                return
            try:
                app.save_profile(name, original, result)
            except (model.Invalid, OSError) as exc:
                app.error(dialog, "Could not save profile", exc)
                return
            dialog.destroy()
        ask(dialog, "Trust this local profile?", brief,
            [(Gtk.ResponseType.CANCEL, "Cancel"), (1, "Save profile")], save)

    dialog.connect("response", response)
    dialog.present()
