import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from termspace import model
from termspace.__main__ import main
from termspace.store import Store, catalog, export_file, import_file


def workspace(layout=None):
    return {"schema_version": 1, "name": "Sample", "tabs": [{"layout": layout or model.leaf()}]}


class SecurityTests(unittest.TestCase):
    def test_root_gui_refused_before_gi(self):
        with patch("os.getuid", return_value=0), patch("sys.stderr") as stderr:
            self.assertEqual(main([]), 1)
        self.assertIn("refuses", str(stderr.write.call_args_list))

    def test_names_and_paths_are_data(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "dir ; ' $(synthetic)"
            path.mkdir()
            data = workspace(model.leaf(str(path), name="; $(synthetic)"))
            data["name"] = "../outside"
            result = model.workspace(data, imported=True)
            self.assertEqual(result["name"], "../outside")
            self.assertEqual(result["tabs"][0]["layout"]["working_directory"], str(path))

    def test_import_strips_execution_and_rejects_extra_fields(self):
        item = model.leaf(profile_name="Custom", startup_commands=["printf 'synthetic'"], trusted=True)
        data = workspace(item)
        result = model.workspace(data, imported=True)["tabs"][0]["layout"]
        self.assertEqual(result["profile"], model.DEFAULT_PROFILE)
        self.assertEqual(result["startup_commands"], [])
        self.assertNotIn("trusted", result)
        item["environment"] = {"PATH": "/tmp"}
        with self.assertRaises(model.Invalid):
            model.workspace(data, imported=True)

    def test_parser_limits(self):
        for raw in (b"{}x", b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":' + b'[' * 1000,
                    b'{"a":' + b'9' * 4400 + b'}', b'\xff'):
            with self.subTest(size=len(raw)), self.assertRaises(model.Invalid):
                model.decode(raw, 10000)
        with self.assertRaises(model.Invalid):
            model.decode(b" " * 32, 16)

    def test_structure_limits_and_duplicate_ids(self):
        terminal = model.leaf()
        nested = {"type": "split", "orientation": "left-right", "children": [terminal, terminal]}
        with self.assertRaises(model.Invalid):
            model.workspace(workspace(nested))
        nested["children"][1] = model.leaf()
        for limits in (model.LIMITS | {"depth": 1}, model.LIMITS | {"panes": 1}):
            with self.assertRaises(model.Invalid):
                model.workspace(workspace(nested), limits)
        self.assertEqual(len(list(model.leaves(model.workspace(workspace(nested))["tabs"][0]["layout"]))), 2)

    def test_escape_controls_and_clipboard_detection(self):
        value = "safe\x1b\u202e\r\n"
        self.assertTrue(model.unsafe_paste(value))
        self.assertEqual(model.preview(value), "safe\\x1b\\u202e\\r\\n")
        self.assertEqual(model.title("prefix" + value, "Terminal"), "prefixsafe")
        self.assertEqual(len(model.title("a" * 800, "")), 80)
        self.assertFalse(model.unsafe_paste("日本語 বাংলা"))

    def test_url_policy(self):
        self.assertTrue(model.url("https://example.test/safe%20path"))
        for url in ("file:///etc/passwd", "javascript:alert(1)", "https://good.test@bad.test/",
                    "https://bad.test/%0a", "https://bad.test/%", "https://bad.test/\x1b",
                    "https://bad.test:99999/", "https://bad.test\\x/", "https://bad.test/%E2%80%AE"):
            self.assertFalse(model.url(url), url)

    def test_invalid_profiles_and_overrides(self):
        for config in ({"shell": "bash"}, {"environment": {"BAD=KEY": "x"}},
                       {"environment": {"API_TOKEN": "synthetic"}}, {"arguments": ["-c\0"]},
                       {"working_directory": "/synthetic-missing-directory"}):
            with self.assertRaises(model.Invalid):
                model.profile(config)
        self.assertTrue(model.EXECUTION_ENV.search("LD_PRELOAD"))
        self.assertEqual(model.profile({"arguments": ["--norc"]})["arguments"], ["--norc"])

    def test_resource_setting_ranges(self):
        for change in ({"limits": {"scrollback": -1}}, {"hyperlinks": 1}, {"theme": "x"}):
            with self.assertRaises(model.Invalid):
                model.settings(change)


class StorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "termspace"
        self.store = Store(self.root)

    def test_atomic_private_roundtrip_and_transaction(self):
        self.store.update(lambda value: value | {"sample": 1})
        self.store.update(lambda value: value | {"other": 2})
        self.assertEqual(self.store.load(), {"schema_version": 1, "sample": 1, "other": 2})
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.root / "catalog.json").stat().st_mode & 0o777, 0o600)

    def test_rejects_unsafe_files_and_directory(self):
        self.root.mkdir(mode=0o700)
        outside = self.base / "outside"
        outside.write_text("{}")
        entry = self.root / "catalog.json"
        entry.symlink_to(outside)
        with self.assertRaises(OSError):
            self.store.update(lambda _: {})
        self.assertEqual(outside.read_text(), "{}")
        entry.unlink()
        entry.write_text("{}")
        entry.chmod(0o644)
        with self.assertRaises(model.Invalid):
            self.store.load()
        symlink = self.base / "bad"
        symlink.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            Store(symlink / "termspace").load()

    def test_corruption_preserved_and_oversized_import(self):
        self.root.mkdir(mode=0o700)
        path = self.root / "catalog.json"
        path.write_bytes(b"{ broken")
        path.chmod(0o600)
        with self.assertRaises(model.Invalid):
            self.store.update(catalog)
        self.assertEqual(path.read_bytes(), b"{ broken")
        with self.assertRaises(model.Invalid):
            import_file(path, 2)

    def test_export_cannot_overwrite_or_follow_symlink(self):
        export = self.base / "sample.json"
        export_file(export, {"a": 1}, 100)
        self.assertEqual(json.loads(export.read_bytes()), {"a": 1})
        with self.assertRaises(FileExistsError):
            export_file(export, {"a": 2}, 100)
        alias = self.base / "alias"
        alias.symlink_to(export)
        with self.assertRaises(OSError):
            export_file(alias, {}, 100)
        with self.assertRaises(OSError):
            import_file(alias, 100)

    def test_lock_contention(self):
        import fcntl
        self.store.update(lambda value: value)
        with (self.root / ".lock").open() as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(model.Invalid):
                self.store.update(lambda value: value)
        self.assertEqual(self.store.load(), {"schema_version": 1})
