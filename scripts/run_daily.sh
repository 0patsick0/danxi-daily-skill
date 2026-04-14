#!/usr/bin/env bash
set -euo pipefail

PY_BIN=""
if command -v python >/dev/null 2>&1; then
	PY_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
	PY_BIN="python3"
elif command -v py >/dev/null 2>&1; then
	PY_BIN="py"
else
	echo "Python runtime not found. Please install Python or ensure python/python3/py is in PATH." >&2
	exit 127
fi

"$PY_BIN" scripts/generate_daily.py "$@"
