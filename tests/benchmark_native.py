"""Measure this application's real shell readiness and idle footprint."""

import time

START = time.monotonic()

import json
import sys
import tempfile
from pathlib import Path

from termspace.__main__ import parser
from termspace.application import Application
from termspace.store import Store
from termspace.native import GLib
from tests.test_gtk import output, send, until


def benchmark(count: int) -> dict:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        store = Store(root / "config")
        app = Application(parser().parse_args, config=store, non_unique=True)
        store.update(lambda _: {"schema_version": 1,
                                "settings": {"default_profile": "Benchmark"},
                                "profiles": {"Benchmark": {"shell": "/bin/bash",
                                                           "arguments": ["--noprofile", "--norc"],
                                                           "environment": {"HISTFILE": "/dev/null",
                                                                           "PROMPT_COMMAND": ""}}}})
        app.register()
        window = app.build_window(cwd=folder)
        tab = window.current()
        generation = [tab.active]
        for index in range(4 if count == 16 else 0):
            next_generation = []
            for pane in generation:
                tab.split(pane, "left-right" if index % 2 == 0 else "top-bottom")
                next_generation.extend([pane, tab.active])
            generation = next_generation
        until(lambda: all(pane.session.state == "running" for pane in generation))
        for pane in generation:
            send(pane, "printf 'READY%s\\n' '_TERM'\n")
        until(lambda: all("READY_TERM" in output(pane) for pane in generation))
        startup = (time.monotonic() - START) * 1000
        begin = time.process_time()
        time_started = time.monotonic()
        loop = GLib.MainLoop()
        def stop():
            loop.quit()
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(2000, stop)
        loop.run()
        cpu = 100 * (time.process_time() - begin) / (time.monotonic() - time_started)
        usage = {}
        for line in Path("/proc/self/smaps_rollup").read_text().splitlines():
            key, _, value = line.partition(":")
            if key in ("Rss", "Pss", "Private_Dirty"):
                usage[key] = round(int(value.split()[0]) / 1024, 1)
        window.dispose_sessions()
        window.destroy()
        return {"panes": count, "startup_ms": round(startup, 1), "idle_cpu_pct_one_core": round(cpu, 2),
                "app_mib": usage}


if __name__ == "__main__":
    count = int(sys.argv[1])
    if count not in (1, 16):
        raise SystemExit("Choose 1 or 16 panes.")
    print(json.dumps(benchmark(count)))
