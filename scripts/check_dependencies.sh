#!/bin/sh
set -eu
/usr/bin/python3 - <<'PY'
import sys
try:
    import gi
    gi.require_versions({"Gtk": "4.0", "Vte": "3.91"})
    from gi.repository import Gtk, Vte
except (ImportError, ValueError) as error:
    raise SystemExit("Install the Ubuntu GI and GTK4 VTE dependencies listed in the README.") from error

print("Python", sys.version.split()[0])
print("PyGObject", gi.__version__)
print("GTK", ".".join(str(part) for part in (Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version())))
print("VTE", ".".join(str(part) for part in (Vte.get_major_version(), Vte.get_minor_version(), Vte.get_micro_version())))
PY
