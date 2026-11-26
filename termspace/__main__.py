"""Local CLI entry point."""

import argparse
import os
import sys

from . import VERSION


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "TermSpace: invalid launch options. See --help.\n")


def parser():
    result = Parser(prog="termspace", description="Native Linux terminal workspaces", add_help=False,
                    allow_abbrev=False)
    result.add_argument("--new-window", action="store_true", help="open a new TermSpace window")
    group = result.add_mutually_exclusive_group()
    group.add_argument("--working-directory", metavar="DIR", help="open a window in DIR")
    group.add_argument("--workspace", metavar="NAME", help="open a saved workspace without startup commands")
    result.add_argument("--version", action="store_true", help="show version and exit")
    result.add_argument("-h", "--help", action="store_true", help="show this help and exit")
    return result


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    options = parser()
    args = options.parse_args(argv)
    if args.help:
        options.print_help()
        return 0
    if args.version:
        print(f"TermSpace {VERSION}")
        return 0
    if os.getuid() == 0 or os.geteuid() == 0:
        print("TermSpace refuses to start a graphical terminal as root. Start it as your normal user.",
              file=sys.stderr)
        return 1
    try:
        from .application import Application
        from .native import Gtk
    except (ImportError, ValueError):
        print("TermSpace needs Ubuntu's python3-gi, gir1.2-gtk-4.0 and gir1.2-vte-3.91.",
              file=sys.stderr)
        return 1
    if not Gtk.init_check():
        print("TermSpace needs an available Wayland or X11 display.", file=sys.stderr)
        return 1
    app = Application(options.parse_args)
    status = app.run(["termspace", *argv])
    return status


if __name__ == "__main__":
    raise SystemExit(main())
