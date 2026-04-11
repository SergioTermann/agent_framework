#!/bin/bash
set -u

cd "$(dirname "$0")"

if [ -x ".venv/bin/python" ]; then
  ".venv/bin/python" start_app.py "$@"
  status=$?
elif command -v python3 >/dev/null 2>&1; then
  python3 start_app.py "$@"
  status=$?
elif command -v python >/dev/null 2>&1; then
  python start_app.py "$@"
  status=$?
else
  echo "[ERROR] Python 3.10+ was not found."
  echo "Install Python or create .venv first, then rerun."
  status=1
fi

if [ "$status" -ne 0 ]; then
  echo
  printf "Start failed. Press Enter to close this window."
  read -r _
fi

exit "$status"
