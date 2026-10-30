#!/bin/sh
# SPDX-License-Identifier: MIT
# Stock/CrossMix App entry. No hardware/input/display service is started.
app_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) || exit 1
exec /bin/sh "$app_dir/collect.sh"
