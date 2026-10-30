#!/bin/sh
# SPDX-License-Identifier: MIT
# Fixed-path observation and private preservation only. Does not install an OS.
# --fixture-root is for host tests; fixture results are explicitly labelled.
set -eu
PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PATH
umask 077
source_root=/
provenance=live-device-observation-not-qualified
if [ "$#" -gt 0 ]; then
    if [ "$#" -ne 2 ] || [ "$1" != --fixture-root ] || [ "$2" = / ]; then
        echo 'Usage: collect.sh [--fixture-root /host/test/tree]' >&2
        exit 2
    fi
    case "$2" in /*) ;; *) exit 2 ;; esac
    source_root=$(CDPATH= cd -- "$2" && pwd -P) || exit 2
    [ "$source_root" != / ] || exit 2
    provenance=host-fixture-not-device-evidence
fi
app_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) || exit 2
if [ "$source_root" = / ] && [ ! -d /mnt/SDCARD ]; then
    echo 'No mounted TrimUI card found; nothing collected.' >&2
    exit 2
fi
# Refuse redirected report roots. Each invocation has a new output directory.
if [ -L "$app_dir/reports" ]; then
    echo 'Reports directory is a link; refused.' >&2
    exit 2
fi
if [ ! -d "$app_dir/reports" ]; then
    mkdir "$app_dir/reports" || exit 2
fi
out=$(mktemp -d "$app_dir/reports/session-XXXXXX") || exit 2
report=$out/baseline.txt
private=$out/PRIVATE-internal-recovery
mkdir "$private" || exit 2
printf '%s\n' 'Collection in progress. Do not use USB Storage until this app exits.' > "$out/INCOMPLETE.txt"
# Firmware and model reads are bounded. No network config, process arguments,
# environment, ROM/save contents, accounts or serial numbers enter baseline.txt.
short_value() {
    if [ -f "$1" ] && [ ! -L "$1" ]; then
        head -c 256 "$1" 2>/dev/null | tr '\000\r\n' '   ' | tr -cd 'A-Za-z0-9 ._+:/()-'
    else
        printf 'unavailable'
    fi
}
hash_file() {
    if command -v sha256sum >/dev/null 2>&1 && [ -f "$1" ] && [ ! -L "$1" ]; then
        sha256sum "$1" 2>/dev/null | cut -d ' ' -f 1
    else
        printf 'unavailable'
    fi
}
{
    printf '%s\n' 'Smart Pro setup observation v1' "provenance=$provenance"
    printf '%s\n' 'custom_os_installed=false' 'hardware_qualified=false' 'physical_restore_tested=false'
    printf 'firmware.etc_version='; short_value "${source_root%/}/etc/version"; printf '\n'
    printf 'firmware.trimui_version='; short_value "${source_root%/}/etc/trimui_version"; printf '\n'
    printf 'model='; short_value "${source_root%/}/proc/device-tree/model"; printf '\n'
    printf 'kernel='; short_value "${source_root%/}/proc/sys/kernel/osrelease"; printf '\n'
    if [ "$source_root" = / ]; then
        printf 'architecture='; uname -m | tr -cd 'A-Za-z0-9_-'; printf '\n'
    else
        printf '%s\n' 'architecture=not-observed-host-fixture'
    fi
    mounts_file=${source_root%/}/proc/mounts
    if [ "$source_root" = / ]; then mounts_file=/proc/self/mounts; fi
    if [ -f "$mounts_file" ] && [ ! -L "$mounts_file" ]; then
        head -c 65536 "$mounts_file" | awk '$2 == "/" || $2 == "/mnt/SDCARD" { if ($3 ~ /^[A-Za-z0-9_.-]+$/) print "filesystem." $2 "=" $3 }' 
    fi
    for rel in usr/trimui/bin/runtrimui.sh usr/trimui/bin/runtrimui-original.sh bin/bash; do
        path=${source_root%/}/$rel
        if [ -L "$path" ]; then
            printf 'internal.%s=symlink-preserved-in-private-archive\n' "$rel"
        elif [ -f "$path" ]; then
            printf 'internal.%s.sha256=' "$rel"; hash_file "$path"; printf '\n'
        else
            printf 'internal.%s=absent-or-unreadable\n' "$rel"
        fi
    done
    for rel in usr/bin/python3 bin/python3 usr/bin/readelf bin/readelf; do
        if [ -e "${source_root%/}/$rel" ]; then
            printf 'tool.%s=present-not-executed\n' "$rel"
        else
            printf 'tool.%s=absent\n' "$rel"
        fi
    done
    for rel in spruce pyui Emu Emus Apps App; do
        if [ -d "${source_root%/}/mnt/SDCARD/$rel" ]; then
            printf 'card_marker.%s=present\n' "$rel"
        fi
    done
} > "$report" || exit 2
# Preserve only known internal startup/switch/shell inputs. This is a selected
# live file archive, not rootfs backup or proof of complete/consistent recovery.
set --
for rel in usr/trimui/bin/runtrimui.sh usr/trimui/bin/runtrimui-original.sh usr/trimui/bin/MainUI usr/trimui/scene bin/bash; do
    path=${source_root%/}/$rel
    if [ -e "$path" ] || [ -L "$path" ]; then
        set -- "$@" "$rel"
        printf 'present %s\n' "$rel" >> "$private/selection.txt"
    else
        printf 'absent %s\n' "$rel" >> "$private/selection.txt"
    fi
done
archive_status=not-created-no-selected-files
if [ "$#" -gt 0 ] && command -v tar >/dev/null 2>&1; then
    # Bound archive growth. tar preserves symlinks and metadata; it never follows
    # them or executes archived files. Failure leaves explicit incomplete data.
    if (ulimit -f 65536 && tar -C "$source_root" -cf "$private/internal-files.tar" "$@") 2> "$private/archive-errors.txt"; then
        if tar -tf "$private/internal-files.tar" > "$private/archive-list.txt" 2>> "$private/archive-errors.txt"; then
            archive_status=created-selected-live-files-not-restore-verified
            hash_file "$private/internal-files.tar" > "$private/internal-files.tar.sha256"
        else
            archive_status=failed-readback
        fi
    else
        archive_status=failed-keep-partial-private-data
    fi
elif [ "$#" -gt 0 ]; then
    archive_status=failed-tar-unavailable
fi
printf 'private_internal_archive=%s\n' "$archive_status" >> "$report"
printf '%s\n' 'No ROMs, saves, firmware, launcher, settings or services were changed.' \
    'Only this new report directory was written.' \
    'PRIVATE-internal-recovery may contain private configuration. Do not upload it.' \
    'Archive covers selected live internal files, not the full internal filesystem.' \
    'Files may change during collection; consistent recovery still needs review.' \
    'Tar listing and archive checksum do not prove restoration or independent storage.' \
    'Copy the whole session directory to Windows before any installation.' > "$out/READ-ME.txt"
# Keep INCOMPLETE on failed archive operations; observations remain useful.
case "$archive_status" in
    created-*)
        mv "$out/INCOMPLETE.txt" "$out/COLLECTED.txt" || exit 2
        printf '%s\n' 'Observation and selected private archive collected. Not qualified for installation.' > "$out/COLLECTED.txt"
        ;;
    *) printf '%s\n' 'Observation collected; private archive incomplete. Do not install yet.' >> "$out/INCOMPLETE.txt" ;;
esac
printf 'Report: %s\n' "$report"
# Returning exits the app through the existing launcher; no reboot/power/USB action.
case "$archive_status" in created-*) exit 0 ;; *) exit 1 ;; esac
