#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python_bin=${PYTHON:-python3}
export PYTHONPATH="$project_dir${PYTHONPATH:+:$PYTHONPATH}"
"$python_bin" -m compileall -q "$project_dir/psp_shell" "$project_dir/bridge" "$project_dir/integration" "$project_dir/tools" "$project_dir/packaging" "$project_dir/retroarch"
"$python_bin" -m unittest discover -s "$project_dir/tests" -v
if [ -d "$project_dir/ppsspp/tests" ]; then
    "$python_bin" -m unittest discover -s "$project_dir/ppsspp/tests" -v
fi
"$python_bin" -m psp_shell --demo --headless --frames 2 --screen library --screenshot "$project_dir/../dist/library.png" --report "$project_dir/../dist/host-preview.json"
