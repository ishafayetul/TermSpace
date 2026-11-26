#!/bin/sh
set -eu
exec "$(dirname "$0")/../main.py" "$@"
