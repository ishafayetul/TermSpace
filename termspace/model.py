"""Configuration validation and trust-boundary helpers."""

import json
import os
import pwd
import re
import stat
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import uuid4

HARD_LIMITS = {"windows": 12, "tabs": 32, "panes": 96, "depth": 12,
               "scrollback": 100_000, "file_bytes": 1_048_576}
LIMITS = {"windows": 6, "tabs": 16, "panes": 48, "depth": 8,
          "scrollback": 20_000, "file_bytes": 262_144}
PASTE_LIMIT = 65_536
SHELLS = {"Bash": "/bin/bash", "Zsh": "/usr/bin/zsh", "Fish": "/usr/bin/fish"}
DEFAULT_PROFILE = "Default Shell"
SHORTCUTS = {
    "new-window": "<Ctrl><Shift>n", "new-tab": "<Ctrl><Shift>t",
    "split-h": "<Ctrl><Shift>d", "split-v": "<Ctrl><Shift>e",
    "close-pane": "<Ctrl><Shift>w", "rename-pane": "<Ctrl><Shift>r",
    "maximize-pane": "<Ctrl><Shift>m", "copy": "<Ctrl><Shift>c",
    "paste": "<Ctrl><Shift>v", "search": "<Ctrl><Shift>f",
    "save-workspace": "<Ctrl><Shift>s", "next-tab": "<Ctrl>Tab",
    "prev-tab": "<Ctrl><Shift>Tab", "focus-left": "<Alt>Left",
    "focus-right": "<Alt>Right", "focus-up": "<Alt>Up", "focus-down": "<Alt>Down",
    "zoom-in": "<Ctrl>plus", "zoom-out": "<Ctrl>minus", "zoom-reset": "<Ctrl>0",
    "fullscreen": "F11",
}
THEMES = ("Ubuntu", "Dracula", "Nord", "Gruvbox", "Solarized Dark",
          "Monokai", "Tokyo Night", "One Dark")
SETTINGS = {
    "theme": "dark", "scheme": "Ubuntu", "status_bar": True, "pane_headers": True,
    "confirm_close": True, "hyperlinks": False, "restore_layout": False,
    "inherit_directory": True, "split_direction": "left-right",
    "default_workspace": "", "default_profile": DEFAULT_PROFILE,
    "default_directory": "", "shortcuts": SHORTCUTS, "limits": LIMITS,
}
PROFILE = {
    "shell": "", "arguments": [], "working_directory": "", "font": "Monospace",
    "font_size": 11, "foreground": "", "background": "", "palette": [],
    "cursor": "block", "blink": False, "scrollback": 10_000, "bell": False,
    "accent": "", "environment": {}, "startup_commands": [],
}
COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")
VARIABLE = re.compile(r"[A-Za-z_][A-Za-z_0-9]{0,63}\Z", re.ASCII)
SECRET = re.compile(r"PASSWORD|PASSWD|TOKEN|SECRET|CREDENTIAL|PRIVATE_KEY|API_?KEY", re.I)
EXECUTION_ENV = re.compile(r"^(PATH$|LD_|DYLD_|PYTHON|BASH_ENV$|ENV$|ZDOTDIR$|GCONV_PATH$|PERL|RUBY|NODE_|GI_TYPELIB_PATH$)")


class Invalid(ValueError):
    """Safe validation error suitable for a dialog."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Invalid(message)


def invisible(char: str) -> bool:
    return (unicodedata.category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
            or char in "\u034f\u115f\u1160\u17b4\u17b5\u3164\uffa0"
            or '\ufe00' <= char <= '\ufe0f' or '\U000e0100' <= char <= '\U000e01ef')


def title(value: str | None, fallback: str) -> str:
    return "".join(c for c in (value or "")[:256] if not invisible(c)).strip()[:80] or fallback


def preview(value: str) -> str:
    return "".join(ascii(c)[1:-1] if invisible(c) else c for c in value)


def unsafe_paste(value: str) -> bool:
    return any(invisible(c) for c in value)


def url(value: str) -> bool:
    if (len(value) > 2048 or not value.isascii() or not value.isprintable()
            or any(c.isspace() or c == "\\" for c in value)
            or re.search(r"%(?![0-9a-fA-F]{2})", value)
            or any(invisible(c) or c == "\\" for c in unquote(value))):
        return False
    try:
        parts = urlsplit(value)
        return bool(parts.scheme in ("http", "https") and parts.hostname
                    and re.fullmatch(r"[A-Za-z0-9.:-]+", parts.hostname)
                    and "%" not in parts.netloc and parts.username is None
                    and parts.password is None and (parts.port is None or parts.port > 0))
    except ValueError:
        return False


def mapping(value: object, keys: set[str]) -> None:
    require(type(value) is dict and value.keys() <= keys, "Unexpected configuration fields.")


def string(value: object, limit: int, *, multiline: bool = False) -> str:
    require(isinstance(value, str) and len(value) <= limit
            and all(not invisible(c) or multiline and c in "\t\n" for c in value),
            "Invalid configuration text.")
    return value


def label(value: object, *, empty: bool = False) -> str:
    value = string(value, 80).strip()
    require(bool(value) or empty, "A name is required.")
    return value


def integer(value: object, minimum: int, maximum: int) -> int:
    require(type(value) is int and minimum <= value <= maximum, "Number out of range.")
    return value


def color(value: object) -> str:
    require(type(value) is str and (not value or bool(COLOR.fullmatch(value))),
            "Colors must use #RRGGBB.")
    return value


def directory(value: str, base: str | None = None) -> str:
    value = string(value, 4096)
    require(bool(value), "Choose an existing directory.")
    path = os.path.abspath(os.path.join(base or str(Path.home()), os.path.expanduser(value)))
    require(os.path.isdir(path) and os.access(path, os.X_OK), "The working directory is unavailable.")
    return path


def executable(path: str) -> bool:
    if not os.path.isabs(path):
        return False
    try:
        mode = os.stat(path).st_mode
        return stat.S_ISREG(mode) and not mode & (stat.S_ISUID | stat.S_ISGID) and os.access(path, os.X_OK)
    except OSError:
        return False


def login_shell() -> str:
    path = pwd.getpwuid(os.getuid()).pw_shell
    try:
        approved = Path("/etc/shells").read_text().splitlines()
    except OSError:
        approved = []
    return path if path in approved and executable(path) else "/bin/bash"


def commands(value: object) -> list[str]:
    require(type(value) is list and len(value) <= 8, "Too many startup commands.")
    return [string(item, 4096, multiline=True) for item in value if item != ""]


def profile(data: dict, *, check_paths: bool = True) -> dict:
    mapping(data, set(PROFILE))
    result = PROFILE | data
    shell = string(result["shell"], 4096)
    require(not shell or os.path.isabs(shell) and (not check_paths or executable(shell)),
            "Shell must be an absolute, executable non-setuid file.")
    args = result["arguments"]
    require(type(args) is list and len(args) <= 24, "Invalid shell argument list.")
    result["arguments"] = [string(arg, 1024) for arg in args]
    cwd = string(result["working_directory"], 4096)
    if cwd and check_paths:
        result["working_directory"] = directory(cwd)
    require(bool(string(result["font"], 80).strip()), "Choose a font family.")
    integer(result["font_size"], 6, 48)
    integer(result["scrollback"], 0, HARD_LIMITS["scrollback"])
    for key in ("foreground", "background", "accent"):
        color(result[key])
    palette = result["palette"]
    require(type(palette) is list and len(palette) in (0, 16) and all(color(c) for c in palette),
            "A custom ANSI palette requires 16 colors.")
    require(result["cursor"] in ("block", "ibeam", "underline"), "Invalid cursor shape.")
    require(all(type(result[k]) is bool for k in ("blink", "bell")), "Invalid profile toggle.")
    environ = result["environment"]
    require(type(environ) is dict and len(environ) <= 32, "Invalid environment overrides.")
    for key, value in environ.items():
        require(bool(VARIABLE.fullmatch(key)) and not SECRET.search(key),
                "Invalid variable name or a possible credential.")
        string(value, 2048)
    result["startup_commands"] = commands(result["startup_commands"])
    return result


def settings(data: dict) -> dict:
    mapping(data, set(SETTINGS))
    result = SETTINGS | data
    require(result["theme"] in ("dark", "light", "system") and result["scheme"] in THEMES,
            "Invalid theme or color scheme.")
    for key, default in SETTINGS.items():
        if type(default) is bool:
            require(type(result[key]) is bool, "Invalid setting toggle.")
    for key in ("default_workspace", "default_profile"):
        label(result[key], empty=True)
    if result["default_directory"] != "":
        string(result["default_directory"], 4096)
    require(result["split_direction"] in ("left-right", "top-bottom"), "Invalid split direction.")
    mapping(result["limits"], set(LIMITS))
    result["limits"] = LIMITS | result["limits"]
    for key, value in result["limits"].items():
        integer(value, {"file_bytes": 4096, "scrollback": 0}.get(key, 1), HARD_LIMITS[key])
    mapping(result["shortcuts"], set(SHORTCUTS))
    result["shortcuts"] = SHORTCUTS | result["shortcuts"]
    for value in result["shortcuts"].values():
        string(value, 48)
    return result


def leaf(cwd: str = "", profile_name: str = DEFAULT_PROFILE, **fields: object) -> dict:
    return {"type": "terminal", "id": uuid4().hex, "name": "", "accent": "",
            "working_directory": cwd, "profile": profile_name, "startup_commands": [], **fields}


def leaves(tree: dict):
    if tree["type"] == "terminal":
        yield tree
    else:
        for child in tree["children"]:
            yield from leaves(child)


def workspace(data: dict, limits: dict = LIMITS, *, imported: bool = False) -> dict:
    mapping(data, {"schema_version", "name", "window_title", "tabs", "width", "height", "maximized"})
    require(type(data.get("schema_version")) is int and data["schema_version"] == 1,
            "Unsupported workspace schema.")
    seen: set[str] = set()

    def layout(node: dict, depth: int) -> dict:
        require(depth <= limits["depth"] and type(node) is dict, "Layout is too deeply nested.")
        if node.get("type") == "terminal":
            mapping(node, set(leaf()) | ({"trusted", "authorized"} if imported else set()))
            ident = string(node.get("id"), 80)
            require(bool(ident) and ident not in seen, "Missing or duplicate pane ID.")
            seen.add(ident)
            require(len(seen) <= limits["panes"], "Workspace contains too many panes.")
            cwd = node.get("working_directory", "")
            if imported and cwd != "":
                cwd = directory(cwd)
            else:
                string(cwd, 4096)
            profile_name = label(node.get("profile", DEFAULT_PROFILE))
            startup = commands(node.get("startup_commands", []))
            return leaf(cwd, DEFAULT_PROFILE if imported else profile_name, id=ident,
                        name=label(node.get("name", ""), empty=True), accent=color(node.get("accent", "")),
                        startup_commands=[] if imported else startup)
        mapping(node, {"type", "orientation", "ratio", "children"})
        require(node.get("type") == "split" and node.get("orientation") in ("left-right", "top-bottom"),
                "Invalid split orientation.")
        ratio = node.get("ratio", .5)
        require(type(ratio) in (int, float) and .05 <= ratio <= .95, "Invalid split ratio.")
        children = node.get("children")
        require(type(children) is list and len(children) == 2, "A split requires two children.")
        return dict(node, ratio=ratio, children=[layout(child, depth + 1) for child in children])

    tabs = data.get("tabs")
    require(type(tabs) is list and 0 < len(tabs) <= limits["tabs"], "Invalid number of workspace tabs.")
    validated = []
    for tab in tabs:
        mapping(tab, {"name", "accent", "layout"})
        validated.append({"name": label(tab.get("name", ""), empty=True),
                          "accent": color(tab.get("accent", "")), "layout": layout(tab.get("layout"), 1)})
    maximized = data.get("maximized", False)
    require(type(maximized) is bool, "Invalid maximized setting.")
    return {"schema_version": 1, "name": label(data.get("name")),
            "window_title": label(data.get("window_title", ""), empty=True), "tabs": validated,
            "width": integer(data.get("width", 1100), 420, 8192),
            "height": integer(data.get("height", 700), 280, 8192), "maximized": maximized}


def decode(raw: bytes, limit: int) -> dict:
    require(len(raw) <= limit, "JSON file is too large.")

    def object_pairs(pairs: list) -> dict:
        result = dict(pairs)
        require(len(result) == len(pairs), "Duplicate JSON field.")
        return result

    def constant(_value: str) -> None:
        raise Invalid("Invalid JSON number.")

    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=object_pairs, parse_constant=constant)
    except (UnicodeError, RecursionError, ValueError) as exc:
        raise Invalid("Invalid or excessively nested JSON.") from exc
    require(type(data) is dict, "Expected a JSON object.")
    return data
