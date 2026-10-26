#!/bin/sh
# A fake of the system checkout's herdr.sh for the dashboard's tests
# (sd:6044): `launch` alone, through herdr_wrap.py beside it, against the
# `herdr` double in tests/doubles that each test puts first on PATH.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${PYTHON:-python3}" "$DIR/herdr_wrap.py" "$@"
