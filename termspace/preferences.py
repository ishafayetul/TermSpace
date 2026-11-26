"""Native settings, profile, and chooser dialogs."""

import json

from . import appearance, model, themes
from .dialogs import ask, choose_file, message, prompt
from .native import Gdk, GLib, Gtk, Pango
from .store import export_file, import_file


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


def accelerator_pair(key, modifiers):
    key = Gdk.keyval_to_lower(key)
    control = Gdk.ModifierType.CONTROL_MASK
    shift = Gdk.ModifierType.SHIFT_MASK
    if key == Gdk.KEY_ISO_Left_Tab:
        key = Gdk.KEY_Tab
    if modifiers == control:
        key = {Gdk.KEY_equal: Gdk.KEY_plus, Gdk.KEY_KP_Equal: Gdk.KEY_plus, Gdk.KEY_KP_Add: Gdk.KEY_plus,
               Gdk.KEY_KP_Subtract: Gdk.KEY_minus, Gdk.KEY_KP_0: Gdk.KEY_0}.get(key, key)
    elif modifiers == (control | shift) and key in (Gdk.KEY_plus, Gdk.KEY_KP_Add):
        key, modifiers = Gdk.KEY_plus, control
    return key, int(modifiers)


def accelerator_map(values: dict) -> dict:
    result = {}
    reservations = {Gdk.KEY_Insert, Gdk.KEY_KP_Insert}
    blocked = (Gdk.ModifierType.SUPER_MASK | Gdk.ModifierType.HYPER_MASK | Gdk.ModifierType.META_MASK)
    control = Gdk.ModifierType.CONTROL_MASK
    shift = Gdk.ModifierType.SHIFT_MASK
    alt = Gdk.ModifierType.ALT_MASK
    for action, accelerator in values.items():
        if not accelerator:
            continue
        valid, key, mods = Gtk.accelerator_parse(accelerator)
        key, mods = accelerator_pair(key, mods)
        protected = (key in reservations or mods & blocked
                     or mods == control and key not in (Gdk.KEY_Tab, Gdk.KEY_plus, Gdk.KEY_minus, Gdk.KEY_0)
                     or mods == (control | shift) and key in (Gdk.KEY_Up, Gdk.KEY_Down)
                     or mods == alt and key not in (Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Left, Gdk.KEY_Right)
                     or not mods and not Gdk.KEY_F1 <= key <= Gdk.KEY_F35
                     or mods and not mods & (control | alt))
        pair = (key, mods)
        model.require(valid and key and not protected, f"Shortcut for {action.replace('-', ' ')} is reserved or invalid.")
        model.require(pair not in result, "Two actions use the same shortcut, including keyboard aliases.")
        result[pair] = action
    return result


class Form:
    def __init__(self, rows_per_column=64):
        self.rows_per_column = rows_per_column
        self.grid = margins(Gtk.Grid(column_spacing=18, row_spacing=10))
        self.rows = {}

    def add(self, key: str, text: str, value, *, choices=None, bounds=None, secret: bool = False,
            color: bool = False):
        if choices:
            options = list(choices)
            widget = Gtk.DropDown.new_from_strings(options)
            widget.set_selected(options.index(value) if value in options else 0)
            getter = lambda: options[widget.get_selected()]
        elif color:
            widget = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False), rgba=appearance.rgba(value),
                                           halign=Gtk.Align.START)

            def getter():
                rgba = widget.get_rgba()
                return "#" + "".join(f"{round(c * 255):02x}" for c in (rgba.red, rgba.green, rgba.blue))
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
        column, row = divmod(len(self.rows), self.rows_per_column)
        self.grid.attach(label, column * 2, row, 1, 1)
        self.grid.attach(widget, column * 2 + 1, row, 1, 1)
        self.rows[key] = (widget, getter)
        return widget

    def watch(self, callback):
        for widget, _getter in self.rows.values():
            signal = {
                Gtk.DropDown: "notify::selected", Gtk.Switch: "notify::active",
                Gtk.ColorDialogButton: "notify::rgba", Gtk.SpinButton: "value-changed",
            }.get(type(widget), "changed")
            widget.connect(signal, callback)

    def values(self) -> dict:
        return {key: getter() for key, (_widget, getter) in self.rows.items()}

    def scroll(self):
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(self.grid)
        return scroll


def preferences(app, parent):
    dialog = Gtk.Dialog(title="TermSpace Settings", transient_for=parent, modal=True, destroy_with_parent=True)
    dialog.add_css_class("settings-dialog")
    dialog.set_default_size(735, 570)
    stack = Gtk.Notebook()
    dialog.get_content_area().append(stack)
    data = app.settings
    fonts = appearance_form(app, dialog, parent)
    groups = {
        "General": [
            ("default_profile", "Default shell profile", app.profile_names()),
            ("default_directory", "Default working directory", None),
            ("default_workspace", "Default workspace", ["", *sorted(app.catalog["workspaces"])]),
            ("restore_layout", "Restore last window layout", None),
            ("confirm_close", "Confirm when closing active sessions", None),
            ("status_bar", "Show status bar", None), ("pane_headers", "Show pane headers", None),
        ],
        "Appearance": [],
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
            stack.append_page(fonts, Gtk.Label(label=heading))
            continue
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
    stack.insert_page(theme_page(app, dialog, parent), Gtk.Label(label="Themes"), 2)
    shortcuts = Form()
    for key, value in data["shortcuts"].items():
        shortcuts.add(key, key.replace("-", " ").capitalize(), value)
    reset = Gtk.Button(label="Restore default shortcuts")
    reset.connect("clicked", lambda *_: [shortcuts.rows[key][0].set_text(value)
                                         for key, value in model.SHORTCUTS.items()])
    shortcuts.grid.attach(Gtk.Label(label="Use GTK accelerator notation such as <Ctrl><Shift>t. "
                                    "Leave empty to disable an action and its aliases.", xalign=0, wrap=True), 0, len(shortcuts.rows), 2, 1)
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
            font_data = fonts.form.values()
            opacity = font_data.pop("background_opacity")
            font_data["font"] = "" if font_data["font"] == AUTOMATIC else font_data["font"]
            overrides = {key: value for key, value in font_data.items()
                         if key in app.settings["appearance"] or value != themes.APPEARANCE[key]}
            new = model.settings(app.settings | changes | {"shortcuts": shortcuts.values(), "limits": limits.values(),
                                                            "appearance": overrides, "background_opacity": opacity})
            app.save_settings(new)
        except (model.Invalid, OSError) as exc:
            app.error(dialog, "Could not save settings", exc)
            return
        dialog.destroy()

    dialog.connect("response", response)
    dialog.present()


AUTOMATIC = "Automatic (monospace)"
FONT_LABELS = {
    "font": "Font family", "font_size": "Default font size (pt)", "weight": "Font weight",
    "zoom_step": "Font zoom increment (pt)", "zoom_scope": "Font zoom scope",
    "cell_width": "Character spacing (%)", "cell_height": "Cell height (%)",
    "cursor": "Cursor shape", "blink": "Blinking cursor", "padding": "Terminal padding (px)",
    "wheel_zoom": "Ctrl + mouse wheel zoom",
}


def font_choices(widget, value):
    return [AUTOMATIC, *sorted(set(appearance.font_families(widget)) | ({value} if value else set()),
                               key=str.casefold)]


class Preview(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_can_focus(False)
        self.header = Gtk.Label(xalign=0)
        self.header.add_css_class("preview-header")
        self.append(self.header)
        self.sample = Gtk.Label(xalign=0, yalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR,
                                hexpand=True)
        self.sample.add_css_class("preview-sample")
        self.append(self.sample)
        self.swatches = Gtk.Label(xalign=0, css_classes=["preview-swatches"])
        self.swatches.update_property([Gtk.AccessibleProperty.LABEL], ["ANSI colors 0 through 15"])
        self.append(self.swatches)
        self.add_css_class("theme-preview")

    def update(self, name, theme, font):
        self.header.set_text(name)
        appearance.style_widget(self, """.theme-preview {{ border: {border_width}px solid {active_border};
            border-radius: {radius}px; background: {terminal_bg}; color: {terminal_fg}; }}""".format_map(theme))
        appearance.style_widget(self.header, """.preview-header {{ padding: 6px 9px; font-weight: bold;
            color: {text}; background: {header}; }}""".format_map(theme))
        appearance.style_widget(self.swatches, ".preview-swatches { padding: 4px 9px; }")
        appearance.style_widget(self.sample, f".preview-sample {{ padding: {font['padding']}px; }}")
        description = GLib.markup_escape_text(appearance.font_description(self.sample, font).to_string())
        spacing = round(font["font_size"] * Pango.SCALE * (font["cell_width"] / 100 - 1) * .6)
        cursor = {"block": "▉", "ibeam": "│", "underline": "_"}[font["cursor"]]
        palette = theme["ansi"]
        self.sample.set_markup(
            f'<span font_desc="{description}" letter_spacing="{spacing}" line_height="{font["cell_height"] / 100}">'
            f'<span foreground="{palette[2]}">dev@termspace</span> '
            f'<span foreground="{palette[4]}">~/project</span> $ ls\n'
            f'<span foreground="{palette[6]}">src/</span>  README.md  '
            f'<span foreground="{palette[3]}">tests/</span>\n'
            f'日本語  বাংলা  0123456789\n'
            f'$ <span foreground="{theme["cursor_color"]}">{cursor}</span></span>')
        self.swatches.set_markup("  ".join(f'<span foreground="{color}">■</span>' for color in theme["ansi"]))


def appearance_form(app, dialog, window):
    data = themes.APPEARANCE | app.settings["appearance"]
    form = Form()
    font = form.add("font", FONT_LABELS["font"], data["font"] or AUTOMATIC, choices=font_choices(dialog, data["font"]))
    font.set_tooltip_text("Automatic uses JetBrains Mono when installed and the system monospace font otherwise.")
    form.add("font_size", FONT_LABELS["font_size"], data["font_size"], bounds=themes.FONT_SIZE)
    opacity = form.add("background_opacity", "Terminal background opacity (%)",
                       app.settings["background_opacity"], bounds=(0, 100))
    opacity.set_tooltip_text("Lower values reveal the desktop on a composited display.")
    for key, title in list(FONT_LABELS.items())[2:]:
        form.add(key, title, data[key], choices=themes.FONT_CHOICES.get(key), bounds=themes.FONT_RANGES.get(key))
    preview = Preview()
    preview.set_hexpand(True)

    def values():
        result = form.values()
        result.pop("background_opacity")
        if result["font"] == AUTOMATIC:
            result["font"] = ""
        return result

    def refresh(*_args):
        theme = app.theme(app.app_theme_name()) or themes.BUILTINS[themes.DEFAULT]
        preview.update("Terminal font preview", theme, values())

    def workspace(*_args):
        window.appearance = model.appearance(values())
        window.apply_settings()

    def reset(*_args):
        for key, value in themes.APPEARANCE.items():
            widget = form.rows[key][0]
            if isinstance(widget, Gtk.DropDown):
                widget.set_selected(themes.FONT_CHOICES[key].index(value) if key != "font" else 0)
            elif isinstance(widget, Gtk.Switch):
                widget.set_active(value)
            else:
                widget.set_value(value)
        opacity.set_value(100)

    form.watch(refresh)
    dialog.connect("notify::is-active", refresh)
    refresh()
    side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, valign=Gtk.Align.START)
    side.append(preview)
    for title, callback in (
        ("Restore defaults", reset), ("Reset all pane sizes", lambda *_: window.zoom("zoom-reset", reset_all=True)),
        ("Apply to this workspace", workspace),
    ):
        action = Gtk.Button(label=title)
        action.connect("clicked", callback)
        side.append(action)
    side.get_last_child().set_tooltip_text("Apply to this window. Save the workspace to keep these settings.")
    side.get_last_child().get_prev_sibling().set_tooltip_text("Reset to the saved defaults in all open windows.")
    preview.set_size_request(265, -1)
    form.grid.attach(side, 2, 0, 1, len(form.rows))
    scroll = form.scroll()
    scroll.form = form
    return scroll


def theme_page(app, dialog, window):
    from .layout import panes

    outer = margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10), 16)
    picker = Gtk.DropDown()
    picker.update_property([Gtk.AccessibleProperty.LABEL], ["Application theme"])
    preview = Preview()
    controls = Gtk.Box(spacing=8, homogeneous=True)
    custom_controls = Gtk.Box(spacing=8, homogeneous=True)
    for widget in (picker, preview, controls, custom_controls):
        outer.append(widget)
    status = Gtk.Label(xalign=0, wrap=True, css_classes=["dim-label"])
    outer.append(status)
    names = ()
    updating = False

    def selected():
        index = picker.get_selected()
        return names[index] if index < len(names) else themes.DEFAULT

    def custom():
        return selected() in app.catalog.get("themes", {})

    def refresh():
        nonlocal names, updating
        updating = True
        available = app.available_themes()
        if available != names:
            names = available
            picker.set_model(Gtk.StringList.new(names))
        name = app.app_theme_name()
        picker.set_selected(names.index(name) if name in names else 0)
        updating = False
        update_preview()

    def update_preview():
        name = selected()
        theme = app.theme(name)
        preview.update(name, theme, appearance.options(theme, {}))
        status.set_text(f"Workspace theme: {window.theme_name or 'Inherit application theme'}")
        for widget in custom_only:
            widget.set_sensitive(custom())

    def apply(name, *, all_terminals=False):
        app.save_settings(app.settings | {"app_theme": name})
        if all_terminals:
            for existing in app.windows():
                existing.theme_name = ""
                for tab in existing.tabs:
                    tab.data["terminal_theme"] = ""
                    for pane in panes(tab.tree):
                        pane.data["terminal_theme"] = ""
            app.apply_theme()
        refresh()

    def perform(callback):
        app.workspace_operation(dialog, callback, title="Theme action failed")

    def on_select(*_args):
        if not updating and selected() != app.app_theme_name():
            perform(lambda: apply(selected()))
            refresh()

    def workspace(name, *, reset=False):
        window.theme_name = name
        if reset:
            window.appearance = {}
        app.refresh_styles()
        window.apply_settings()
        update_preview()

    def save_theme(name, original, data):
        app.set_theme(name, original, data)
        refresh()

    def import_theme():
        def load(path):
            name, data = model.theme_document(import_file(path, themes.THEME_FILE_LIMIT, strict=True))
            theme_editor(app, dialog, save_theme, name=name, data=data)
        choose_file(dialog, save=False, name="", kind="theme",
                    callback=lambda path: perform(lambda: load(path)))

    def export_theme():
        name = selected()
        document = {"schema_version": 1, "name": name, "theme": app.theme(name)}
        choose_file(dialog, save=True, name="termspace-theme.json", kind="theme",
                    callback=lambda path: perform(lambda: export_file(
                        path, document, themes.THEME_FILE_LIMIT, strict=True)))

    def delete_theme():
        name = selected()
        ask(dialog, "Delete custom theme?", f"Remove {name}? Terminals using it will inherit their theme.",
            [(Gtk.ResponseType.CANCEL, "Cancel"), (1, "Delete")],
            lambda code, _: perform(lambda: save_theme("", name, None)) if code == 1 else None)

    custom_only = []
    for box, title, callback in (
        (controls, "Restore Tokyo Night", lambda: apply(themes.DEFAULT)),
        (controls, "Apply to all terminals", lambda: apply(selected(), all_terminals=True)),
        (controls, "Use in this workspace", lambda: workspace(selected())),
        (controls, "Reset workspace", lambda: workspace("", reset=True)),
        (custom_controls, "New", lambda: theme_editor(app, dialog, save_theme, data=app.theme(selected()))),
        (custom_controls, "Edit / Rename", lambda: theme_editor(app, dialog, save_theme, name=selected(),
                                                                original=selected(), data=app.theme(selected()))),
        (custom_controls, "Duplicate", lambda: theme_editor(app, dialog, save_theme,
                                                            data=app.theme(selected()), name="Theme copy")),
        (custom_controls, "Delete", delete_theme), (custom_controls, "Import…", import_theme),
        (custom_controls, "Export…", export_theme),
    ):
        action = Gtk.Button(label=title)
        action.connect("clicked", lambda *_args, call=callback: perform(call))
        box.append(action)
        if title in ("Edit / Rename", "Delete"):
            custom_only.append(action)
    refresh()
    picker.connect("notify::selected", on_select)
    dialog.connect("notify::is-active", lambda *_: refresh())
    return outer


def theme_editor(app, parent, save_theme, *, data, name="", original=""):
    dialog = Gtk.Dialog(title="Custom theme", transient_for=parent, modal=True, destroy_with_parent=True)
    dialog.add_css_class("settings-dialog")
    dialog.set_default_size(690, 650)
    area = dialog.get_content_area()
    preview = margins(Preview(), 10)
    area.append(preview)
    tabs = Gtk.Notebook(vexpand=True)
    area.append(tabs)
    design, colors, ansi = Form(), Form(rows_per_column=11), Form(rows_per_column=8)
    design.add("name", "Theme name", name)
    design.add("font", FONT_LABELS["font"], data["font"] or AUTOMATIC, choices=font_choices(dialog, data["font"]))
    design.add("font_size", FONT_LABELS["font_size"], data["font_size"], bounds=themes.FONT_SIZE)
    design.add("cursor", FONT_LABELS["cursor"], data["cursor"], choices=themes.FONT_CHOICES["cursor"])
    design.add("blink", FONT_LABELS["blink"], data["blink"])
    for key, (_, low, high) in themes.GEOMETRY.items():
        design.add(key, key.replace("_", " ").capitalize() + " (px)", data[key], bounds=(low, high))
    for key in themes.COLOR_FIELDS:
        colors.add(key, key.replace("_fg", " foreground").replace("_bg", " background").replace("_", " ").capitalize(),
                   data[key], color=True)
    for index, value in enumerate(data["ansi"]):
        ansi.add(str(index), f"ANSI {index}", value, color=True)
    for form, title in ((design, "Typography and spacing"), (colors, "Interface and terminal colors"), (ansi, "ANSI colors")):
        tabs.append_page(form.scroll(), Gtk.Label(label=title))

    def draft():
        values = design.values()
        title = values.pop("name")
        if values["font"] == AUTOMATIC:
            values["font"] = ""
        return title, values | colors.values() | {"ansi": list(ansi.values().values())}

    def update(*_args):
        title, theme = draft()
        preview.update(title or "Theme preview", theme, appearance.options(theme, {}))

    def response(_dialog, code):
        if code == 1:
            title, theme = draft()
            try:
                save_theme(model.label(title), original, model.custom_theme(theme))
            except (OSError, model.Invalid) as exc:
                app.error(dialog, "Could not save theme", exc)
                return
        dialog.destroy()

    for form in (design, colors, ansi):
        form.watch(update)
    update()
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("Save theme", 1).add_css_class("suggested-action")
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
                 bounds={"font_size": themes.FONT_SIZE, "scrollback": (0, model.HARD_LIMITS["scrollback"])}.get(key),
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
