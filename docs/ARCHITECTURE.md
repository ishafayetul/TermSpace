# Architecture

The source and Debian launcher run `main.py` with Ubuntu's Python in isolated import mode. `termspace/__main__.py` parses only local launch options and refuses root GUI use before loading GTK. `application.py` owns Gtk.Application, menus, resources and catalog transactions. Existing instances handle launch requests using GTK's local application bus.

`window.py` manages Gtk.ApplicationWindow, Gtk.Notebook, keyboard dispatch and search. `layout.py` represents a tab as a binary tree. A branch stores orientation, ratio and its Gtk.Paned. A leaf holds one stable Pane and its VTE Session. Structural edits rebuild split containers around retained pane widgets. Tab transfer reuses the tab page and all PTYs.

`terminal.py` manages VTE's asynchronous spawn and child-exit signals. VTE creates and sizes the PTY. The application tracks the pending/running/failed/exited state and disposes unparented VTE widgets on close. Terminal sizing, bracketed paste and rendering remain inside VTE. An absolute coreutils launcher ensures the working directory still exists at the point of exec. A workspace cannot fall back to executing its reviewed command elsewhere when that directory disappears.

`model.py` defines validation and resource ceilings. `store.py` holds descriptor-relative private persistence, per-catalog locks and fsynced replacement. File names are constant, while workspace identifiers are keys in a versioned catalog. Version 1 is the first schema. Optional fields are normalized through defaults and future versions require explicit migrations. Export uses a separate user-selected path and does not overwrite existing files.

`preferences.py` and `dialogs.py` provide native GTK forms and responses. Process output and clipboard previews are treated as plain text. The [threat model](../SECURITY.md) records the boundaries and known risks.
