"""GTK styling and VTE appearance shared by live terminals and previews."""

from . import themes
from .native import Gdk, Gtk, Pango, Vte


def rgba(value: str):
    color = Gdk.RGBA()
    color.parse(value)
    return color


def style_widget(widget, css: str) -> None:
    if getattr(widget, "appearance_css", None) == css:
        return
    context = widget.get_style_context()
    if not hasattr(widget, "appearance_provider"):
        widget.appearance_provider = Gtk.CssProvider()
        context.add_provider(widget.appearance_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2)
    widget.appearance_provider.load_from_string(css)
    widget.appearance_css = css


def scrollbar_class(theme):
    return f"scrollbar-{theme['header'][1:]}-{theme['scrollbar'][1:]}-{theme['scrollbar_width']}"


def scrollbar_css(theme):
    selector = "." + scrollbar_class(theme)
    return f"""
        {selector} {{ background: {theme['header']}; }}
        {selector} slider {{ min-width: {theme['scrollbar_width']}px;
                             background: mix({theme['header']}, {theme['scrollbar']}, 0.45); }}
        {selector} slider:hover {{ background: {theme['scrollbar']}; }}
    """


def font_families(widget):
    return sorted({family.get_name() for family in widget.get_pango_context().list_families()
                   if family.is_monospace()} | {"Monospace"}, key=str.casefold)


def font_description(widget, options):
    font = Pango.FontDescription()
    family = options["font"] or getattr(widget, "preferred_monospace", None)
    if not family:
        family = widget.preferred_monospace = (
            "JetBrains Mono" if "JetBrains Mono" in font_families(widget) else "Monospace")
    font.set_family(f"{family}, monospace" if family.casefold() != "monospace" else family)
    font.set_weight(getattr(Pango.Weight, options["weight"].upper()))
    font.set_size(options["font_size"] * Pango.SCALE)
    return font


def colors(terminal, theme, alpha=1.0):
    background = rgba(theme["terminal_bg"])
    background.alpha = alpha
    terminal.set_colors(rgba(theme["terminal_fg"]), background, [rgba(c) for c in theme["ansi"]])
    terminal.set_color_cursor(rgba(theme["cursor_color"]))
    terminal.set_color_cursor_foreground(rgba(theme["terminal_bg"]))
    terminal.set_color_highlight(rgba(theme["selection_bg"]))
    terminal.set_color_highlight_foreground(rgba(theme["selection_fg"]))


def typography(terminal, options):
    terminal.set_font(font_description(terminal, options))
    terminal.set_cell_width_scale(options["cell_width"] / 100)
    terminal.set_cell_height_scale(options["cell_height"] / 100)
    terminal.set_cursor_shape({"block": Vte.CursorShape.BLOCK, "ibeam": Vte.CursorShape.IBEAM,
                               "underline": Vte.CursorShape.UNDERLINE}[options["cursor"]])
    terminal.set_cursor_blink_mode(Vte.CursorBlinkMode.ON if options["blink"] else Vte.CursorBlinkMode.OFF)


def options(theme, overrides):
    return themes.APPEARANCE | {key: theme[key] for key in ("font", "font_size", "cursor", "blink", "padding")} | overrides
