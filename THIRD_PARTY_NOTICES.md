# Third-party dependencies

TermSpace's original code, artwork and theme definitions are MIT licensed. The named color schemes use original ANSI palette definitions inspired by published theme names. Upstream theme files, fonts and artwork are not redistributed.

| Ubuntu packages | Development baseline | Notices on the host |
| --- | --- | --- |
| `python3` | CPython 3.12.3 | `/usr/share/doc/python3.12/copyright` |
| `python3-gi`, `python3-gi-cairo` | PyGObject 3.48.2, cairo bridge declared for installation | `/usr/share/doc/python3-gi/copyright` |
| `gir1.2-gtk-4.0`, `libgtk-4-1` | GTK 4.14.5 | `/usr/share/doc/libgtk-4-1/copyright` |
| `gir1.2-vte-3.91`, `libvte-2.91-gtk4-0` | VTE 0.76.0, Ubuntu revision 0.76.0-1ubuntu0.1 | `/usr/share/doc/libvte-2.91-gtk4-0/copyright` |

Ubuntu supplies and updates the libraries separately. The TermSpace Debian package contains no copies of these libraries or GI typelibs. The dependency and security lifecycle details are available from [Ubuntu](https://ubuntu.com/security) and [VTE upstream](https://gitlab.gnome.org/GNOME/vte).
