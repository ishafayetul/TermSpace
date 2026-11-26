"""The GI versions and APIs supported by Ubuntu 24.04."""

import gi

gi.require_versions({"Gtk": "4.0", "Gdk": "4.0", "Vte": "3.91"})
from gi.repository import Gdk, Gio, GLib, GObject, Gtk, Pango, Vte
