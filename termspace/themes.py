"""Built-in chrome colors and ANSI palettes, in VTE color order."""

# Chrome: window, header, tab, border, text, muted text, accent, purple.
# Terminal: background, foreground, then the 16 ANSI colors.
_ROWS = {
    "Tokyo Night": (
        "16161e 1f2335 292e42 414868 c0caf5 a9b1d6 7aa2f7 bb9af7",
        "1a1b26 c0caf5 15161e f7768e 9ece6a e0af68 7aa2f7 bb9af7 7dcfff a9b1d6 "
        "585f82 ff899d b9f27c ffbe89 8db0ff c7a9ff a4daff c0caf5"),
    "Tokyo Night Storm": (
        "1f2335 24283b 343b58 545c7e c0caf5 a9b1d6 7aa2f7 bb9af7",
        "24283b c0caf5 1d202f f7768e 9ece6a e0af68 7aa2f7 bb9af7 7dcfff a9b1d6 "
        "565f89 ff899d b9f27c ffbe89 8db0ff c7a9ff a4daff c0caf5"),
    "Catppuccin Mocha": (
        "181825 1e1e2e 313244 585b70 cdd6f4 bac2de 89b4fa cba6f7",
        "1e1e2e cdd6f4 45475a f38ba8 a6e3a1 f9e2af 89b4fa f5c2e7 94e2d5 bac2de "
        "585b70 f38ba8 a6e3a1 f9e2af 89b4fa f5c2e7 94e2d5 a6adc8"),
    "Catppuccin Macchiato": (
        "1e2030 24273a 363a4f 5b6078 cad3f5 b8c0e0 8aadf4 c6a0f6",
        "24273a cad3f5 494d64 ed8796 a6da95 eed49f 8aadf4 f5bde6 8bd5ca b8c0e0 "
        "5b6078 ed8796 a6da95 eed49f 8aadf4 f5bde6 8bd5ca a5adcb"),
    "Dracula": (
        "21222c 282a36 383a4b 6272a4 f8f8f2 c6c9de bd93f9 ff79c6",
        "282a36 f8f8f2 21222c ff5555 50fa7b f1fa8c bd93f9 ff79c6 8be9fd f8f8f2 "
        "6272a4 ff6e6e 69ff94 ffffa5 d6acff ff92df a4ffff ffffff"),
    "Nord": (
        "272c36 2e3440 3b4252 546078 eceff4 d8dee9 88c0d0 b48ead",
        "2e3440 eceff4 3b4252 bf616a a3be8c ebcb8b 81a1c1 b48ead 88c0d0 e5e9f0 "
        "64738e d47c85 b1cd98 f2d7a0 8fbcdb c9a3c3 8fbcbb eceff4"),
    "GitHub Dark": (
        "0d1117 161b22 21262d 484f58 e6edf3 b1bac4 58a6ff d2a8ff",
        "0d1117 e6edf3 484f58 ff7b72 3fb950 d29922 58a6ff bc8cff 39c5cf b1bac4 "
        "6e7681 ffa198 56d364 e3b341 79c0ff d2a8ff 56d4dd f0f6fc"),
    "Gruvbox Dark": (
        "1d2021 282828 3c3836 665c54 ebdbb2 d5c4a1 83a598 d3869b",
        "282828 ebdbb2 282828 fb4934 b8bb26 fabd2f 83a598 d3869b 8ec07c a89984 "
        "928374 fb4934 b8bb26 fabd2f 83a598 d3869b 8ec07c ebdbb2"),
    "One Dark": (
        "21252b 282c34 343a46 515b6d e1e5eb abb2bf 61afef c678dd",
        "282c34 e1e5eb 282c34 e06c75 98c379 e5c07b 61afef c678dd 56b6c2 abb2bf "
        "5c6370 ff7a85 b0da8b f2cf8c 75bdff d990ee 70c7d0 e1e5eb"),
    "Solarized Dark": (
        "001f27 002b36 073642 49666b fdf6e3 93a1a1 54b5ed b09de0",
        "002b36 eee8d5 073642 f36360 9aa400 d8a821 54b5ed ec75a6 4cb9af eee8d5 "
        "657b83 ff816a b2be2c edbb40 79c5ee b09de0 68cdc1 fdf6e3"),
    "Monokai": (
        "20211c 272822 3e3d32 5f5e50 f8f8f2 d0cfbc a6e22e ae81ff",
        "272822 f8f8f2 24251f f92672 a6e22e e6db74 66d9ef ae81ff a1efe4 f8f8f2 "
        "75715e ff5c93 c4f063 f4eb9a 91e5f5 c9aaff bcf8ef ffffff"),
    "Ubuntu Classic": (
        "211325 302034 482b49 69506e f3eaf4 d6c4d7 efa7cc c4a1ff",
        "300a24 f3eaf4 2e3436 f27578 9fda45 fce94f 83aaff df93d0 71d6db d3d7cf "
        "888a85 ff9293 bcfa75 fff09e a4c4ff f0b1e4 9dedf1 eeeeec"),
    "AMOLED Black": (
        "000000 101114 1c1e24 424650 e6eaf2 b0bacb 89aaff c6a0ff",
        "000000 e6eaf2 22242a ff8196 9be17d f3c570 89aaff c6a0ff 76d5e7 c4cada "
        "6c7385 ffa7b6 b7ef9f ffda91 a8c2ff d9bfff 9de7f4 ffffff"),
    "Light": (
        "edf0f7 e1e6f2 f8faff 9ba9c5 242f48 445371 345ea8 6844a4",
        "f8faff 242f48 242f48 a62646 28633c 81570b 345ea8 6844a4 146277 4c5970 "
        "596680 b32848 246a3d 805613 2d60a4 7146a5 116681 56647d"),
}

COLOR_FIELDS = (
    "window", "header", "tab", "border", "text", "muted", "accent", "purple",
    "terminal_bg", "terminal_fg", "pane_header", "active_border", "cursor_color",
    "selection_bg", "selection_fg", "scrollbar", "menu", "dialog", "success", "warning", "error",
)
GEOMETRY = {
    "padding": (8, 0, 24), "header_height": (26, 20, 44), "radius": (6, 0, 16),
    "border_width": (1, 1, 4), "tab_radius": (7, 0, 16), "scrollbar_width": (5, 3, 14),
}
FONT_SIZE = (6, 40)
FONT_CHOICES = {
    "weight": ("Normal", "Medium", "Semibold", "Bold"),
    "zoom_scope": ("Focused Pane", "Current Tab", "All Terminals"),
    "cursor": ("block", "ibeam", "underline"),
}
FONT_RANGES = {"font_size": FONT_SIZE, "zoom_step": (1, 8),
               "cell_width": (100, 160), "cell_height": (100, 180), "padding": (0, 24)}
APPEARANCE = {"font": "", "font_size": 11, "weight": "Normal", "zoom_step": 1,
              "zoom_scope": "Focused Pane", "cell_width": 100, "cell_height": 100,
              "cursor": "block", "blink": False, "padding": 8, "wheel_zoom": True}
THEME_FILE_LIMIT = 16_384
DEFAULT = "Tokyo Night"
SYSTEM = "System theme"
ALIASES = {"Ubuntu": "Ubuntu Classic", "Gruvbox": "Gruvbox Dark"}


def make_theme(chrome, terminal):
    background, foreground, *ansi = terminal.split()
    colors = dict(zip(COLOR_FIELDS[:10], ("#" + part for part in (*chrome.split(), background, foreground))))
    palette = ["#" + part for part in ansi]
    return colors | {
        "pane_header": colors["header"], "active_border": colors["accent"],
        "cursor_color": colors["accent"], "selection_bg": colors["accent"],
        "selection_fg": colors["window"] if colors["window"] != "#edf0f7" else "#ffffff",
        "scrollbar": colors["muted"], "menu": colors["header"], "dialog": colors["window"],
        "success": palette[2], "warning": palette[3], "error": palette[1], "ansi": palette,
        **{key: bounds[0] for key, bounds in GEOMETRY.items()},
        "font": "", "font_size": 11, "cursor": "block", "blink": False,
    }


BUILTINS = {name: make_theme(*row) for name, row in _ROWS.items()}
NAMES = (*BUILTINS, SYSTEM)
