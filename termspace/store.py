"""Private, atomic XDG persistence. Catalog keys never become filenames."""

import fcntl
import json
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from .model import HARD_LIMITS, Invalid, custom_theme, decode, label, mapping, profile, require, settings, workspace
from .themes import ALIASES, NAMES

DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
READ = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
CREATE = os.O_WRONLY | os.O_NOFOLLOW | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC


def encode(data: dict, size: int) -> bytes:
    result = (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    require(len(result) <= size, "JSON data exceeds the configured file limit.")
    return result


def regular(fd: int, *, private: bool) -> None:
    info = os.fstat(fd)
    require(stat.S_ISREG(info.st_mode), "Expected a regular file.")
    if private:
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_nlink == 1, "Private files require owner-only mode 0600 and one link.")


def read(fd: int, size: int, *, private: bool) -> dict:
    with os.fdopen(fd, "rb") as stream:
        regular(stream.fileno(), private=private)
        return decode(stream.read(size + 1), size)


@contextmanager
def local_parent(path: Path):
    require(path.is_absolute() and path.name and ".." not in path.parts, "Choose an absolute local file.")
    fd = os.open("/", DIRECTORY)
    try:
        for part in path.parent.parts[1:]:
            child = os.open(part, DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def import_file(path: Path, size: int, *, strict: bool = False) -> dict:
    if strict:
        with local_parent(path) as folder:
            return read(os.open(path.name, READ, dir_fd=folder), size, private=False)
    return read(os.open(path, READ), size, private=False)


def export_file(path: Path, data: dict, size: int, *, strict: bool = False) -> None:
    content = encode(data, size)
    if strict:
        with local_parent(path) as folder:
            write_export(folder, path.name, content)
    else:
        folder = os.open(path.parent, DIRECTORY)
        try:
            write_export(folder, path.name, content)
        finally:
            os.close(folder)


def write_export(folder: int, name: str, content: bytes) -> None:
    temp = ".termspace-export-" + uuid4().hex
    fd = os.open(temp, CREATE, 0o600, dir_fd=folder)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp, name, src_dir_fd=folder, dst_dir_fd=folder, follow_symlinks=False)
    finally:
        os.unlink(temp, dir_fd=folder)


def xdg(variable: str, fallback: Path) -> Path:
    path = Path(os.environ.get(variable, ""))
    return path if path.is_absolute() else fallback


def catalog(data: dict) -> dict:
    mapping(data, {"schema_version", "settings", "workspaces", "profiles", "themes"})
    require(type(data.get("schema_version")) is int and data["schema_version"] == 1,
            "Unsupported catalog schema.")
    result = {"schema_version": 1, "settings": settings(data.get("settings", {})),
              "workspaces": data.get("workspaces", {}), "profiles": data.get("profiles", {}),
              "themes": data.get("themes", {})}
    validators = {"workspaces": lambda value: workspace(value, HARD_LIMITS),
                  "profiles": lambda value: profile(value, check_paths=False), "themes": custom_theme}
    for key, validate in validators.items():
        items = result[key]
        require(type(items) is dict and len(items) <= 128, "Invalid catalog entries.")
        for name, value in items.items():
            require(label(name) == name, "Invalid catalog entry name.")
            if key == "themes":
                require(name not in NAMES and name not in ALIASES, "Theme name is reserved.")
            clean = validate(value)
            if key == "workspaces":
                require(clean["name"] == name, "Workspace catalog name does not match its entry.")
    return result


class Store:
    def __init__(self, root: Path | None = None, filename: str = "catalog.json"):
        self.root = root or xdg("XDG_CONFIG_HOME", Path.home() / ".config") / "termspace"
        self.filename = filename

    @contextmanager
    def folder(self):
        require(self.root.is_absolute() and ".." not in self.root.parts, "Invalid XDG directory.")
        fd = os.open("/", DIRECTORY)
        try:
            for part in self.root.parts[1:]:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(part, DIRECTORY, dir_fd=fd)
                os.close(fd)
                fd = child
            info = os.fstat(fd)
            require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
                    "The TermSpace data directory must be owned by you with mode 0700.")
            yield fd
        finally:
            os.close(fd)

    def _read(self, folder: int) -> dict:
        try:
            fd = os.open(self.filename, READ, dir_fd=folder)
        except FileNotFoundError:
            return {"schema_version": 1}
        return read(fd, HARD_LIMITS["file_bytes"], private=True)

    def load(self) -> dict:
        with self.folder() as folder:
            return self._read(folder)

    def update(self, operation) -> dict:
        with self.folder() as folder:
            lock = os.open(".lock", READ | os.O_CREAT, 0o600, dir_fd=folder)
            try:
                regular(lock, private=True)
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise Invalid("Another TermSpace window is saving. Try again.") from exc
                data = operation(self._read(folder))
                content = encode(data, HARD_LIMITS["file_bytes"])
                name = ".tmp-" + uuid4().hex
                fd = os.open(name, CREATE, 0o600, dir_fd=folder)
                try:
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(content)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(name, self.filename, src_dir_fd=folder, dst_dir_fd=folder)
                    os.fsync(folder)
                finally:
                    try:
                        os.unlink(name, dir_fd=folder)
                    except FileNotFoundError:
                        pass
                return data
            finally:
                os.close(lock)
