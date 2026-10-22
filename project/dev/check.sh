#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python_bin=${PYTHON:-python3}
export PYTHONPATH="$project_dir${PYTHONPATH:+:$PYTHONPATH}"
exec "$python_bin" "$project_dir/dev/certify.py" "$@"
