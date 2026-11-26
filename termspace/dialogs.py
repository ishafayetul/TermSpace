"""Small native dialogs. All untrusted content is plain text."""

from pathlib import Path

from .native import Gtk


def ask(parent, heading: str, detail: str, buttons: list[tuple[int, str]], callback,
        *, text: str | None = None, default: int = Gtk.ResponseType.CANCEL,
        monospace: bool = False):
    dialog = Gtk.Dialog(title=heading, transient_for=parent, modal=True, destroy_with_parent=True)
    dialog.set_default_size(460, -1)
    box = dialog.get_content_area()
    for edge in ("top", "bottom", "start", "end"):
        getattr(box, f"set_margin_{edge}")(16)
    box.set_spacing(10)
    if detail:
        label = Gtk.Label(label=detail, xalign=0, wrap=True, max_width_chars=68)
        box.append(label)
    entry = None
    if text is not None and monospace:
        view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True,
                            wrap_mode=Gtk.WrapMode.CHAR)
        view.get_buffer().set_text(text)
        scroll = Gtk.ScrolledWindow(min_content_height=145, max_content_height=350,
                                    propagate_natural_height=True)
        scroll.set_child(view)
        box.append(scroll)
    elif text is not None:
        entry = Gtk.Entry(text=text, activates_default=True, max_length=80)
        box.append(entry)
    for response, name in buttons:
        dialog.add_button(name, response)
    dialog.set_default_response(default)

    def answered(_dialog, response):
        value = entry.get_text() if entry else ""
        dialog.destroy()
        callback(response, value)

    dialog.connect("response", answered)
    dialog.present()
    if entry:
        entry.grab_focus()
    return dialog


def message(parent, title: str, detail: str) -> None:
    ask(parent, title, detail, [(Gtk.ResponseType.CLOSE, "Close")], lambda *_: None,
        default=Gtk.ResponseType.CLOSE)


def prompt(parent, heading: str, value: str, callback, detail: str = "") -> None:
    ask(parent, heading, detail, [(Gtk.ResponseType.CANCEL, "Cancel"), (1, "Save")],
        lambda response, text: callback(text) if response == 1 else None, text=value, default=1)


def choose_file(parent, *, save: bool, name: str, callback) -> None:
    action = Gtk.FileChooserAction.SAVE if save else Gtk.FileChooserAction.OPEN
    dialog = Gtk.FileChooserNative.new("Export workspace" if save else "Import workspace",
                                       parent, action, "Export" if save else "Import", "Cancel")
    if save:
        dialog.set_current_name(name)
    file_filter = Gtk.FileFilter(name="Workspace JSON")
    file_filter.add_pattern("*.json")
    dialog.add_filter(file_filter)

    def response(_dialog, result):
        selected = dialog.get_file() if result == Gtk.ResponseType.ACCEPT else None
        dialog.destroy()
        if selected:
            path = selected.get_path()
            if path:
                callback(Path(path))
            else:
                message(parent, "Local file required", "Choose a file on this computer.")

    dialog.connect("response", response)
    dialog.show()
