# Pinned spruce source fixes

These reviewable patches target spruceOS v4.5.4, commit
`d45ff8dfe5756147522b04ae5863d17a90e88b54`. The [manifest](manifest.json)
records each source file's SHA-256 before and after application. Nothing here
changes an installed card automatically.

| Patch | Result |
| --- | --- |
| `0001-pyui-quote-game-launch.patch` | Quotes the launch directory while retaining the lexical system path. |
| `0002-ota-require-verified-tls.patch` | Reports HTTPS verification failure without an insecure retry. |
| `0003-preserve-archive-extraction-status.patch` | Returns the extractor's actual exit status. |
| `0004-usb-refuse-unstaged-export.patch` | Refuses USB export when RAM staging fails and reports that the card was not exported. |

The USB patch preserves the successful `save_poweroff.sh --usb-storage-export`
handoff. That existing shutdown route owns clean unmount and reboot. On staging
failure, the app returns an error to the existing principal loop, which owns UI
return, message-writer cleanup and idle-watchdog restart. The patch removes the
fallback that exposed a mounted SD card. It adds no service or power owner.

Run the source regressions with an untouched pinned checkout:

```sh
PYTHONPATH=project SPRUCE_SOURCE_ROOT=/path/to/spruce-v4.5.4 python3 -m unittest discover -s project/tests -p 'test_*patch.py' -v
PYTHONPATH=project SPRUCE_SOURCE_ROOT=/path/to/spruce-v4.5.4 python3 -m unittest discover -s project/tests -p test_upstream_reliability.py -v
```

The USB harness runs the pinned launcher with temporary substitutes for imports
and all device/service commands. It reproduces the original mounted-export
branch, verifies refusal after staging failure, and compares successful handoffs
before and after the patch. It also checks failed and missing shutdown helpers.
These are host source checks. USB clean unmount, FAT/exFAT interruption recovery
and UI/service return still need physical TG5040 qualification and a reviewed
release application path.

SpruceOS, Copyright (c) 2024 SpruceOS, a project by SpruceUI, is used under its
[pinned upstream licence](https://github.com/spruceUI/spruceOS/blob/d45ff8dfe5756147522b04ae5863d17a90e88b54/LICENSE).
The shell-source patches retain those terms. The PyUI patch also retains the
[nested PyUI licence](https://github.com/spruceUI/spruceOS/blob/d45ff8dfe5756147522b04ae5863d17a90e88b54/App/PyUI/main-ui/LICENSE.md),
including its unresolved source-use notification requirement. The original
Python test harnesses use the project's MIT licence; that licence does not
relicense the patched upstream source.
