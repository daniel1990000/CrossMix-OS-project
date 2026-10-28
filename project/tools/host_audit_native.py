# SPDX-License-Identifier: MIT
"""Development-only raw native load-session checks; packets grant no authority.

Reuse the canonical packet codec only. Do not construct qualified profiles,
production sessions, capabilities or authenticated frontend Resume evidence.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time

from psp_shell.state_evidence import FORMAT, MAX_PACKET, UPSTREAM, _decode_packet, encode_packet


class NativeAuditError(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise NativeAuditError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _private_bytes(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _read_private(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid() and before.st_nlink == 1 and
             stat.S_IMODE(before.st_mode) == 0o600 and 0 < before.st_size <= MAX_PACKET,
             'Native load evidence must be a bounded owned 0600 regular file')
        data = stream.read(MAX_PACKET + 1)
        after = os.fstat(stream.fileno())
        named = os.stat(path, follow_symlinks=False)
        identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        need(identity(before) == identity(after) == identity(named) and len(data) == before.st_size,
             'Native load evidence changed during read')
    return data


def validate_declaration(manifest):
    need(type(manifest.get('native_slot')) is int and 0 <= manifest['native_slot'] <= 99,
         'Record the actual fixture native slot explicitly')
    need(isinstance(manifest.get('native_disc_version'), str) and
         re.fullmatch(r'[0-9]{1,3}\.[0-9]{1,3}', manifest['native_disc_version']),
         'Record exact fixture native disc version')
    need(manifest.get('native_architecture') in ('x86_64', 'aarch64'),
         'Record native host architecture')
    version = manifest['identity']['emulator']['version']
    need(isinstance(version, str) and 0 < len(version) <= 128, 'Record exact reported engine version')


def prepare_load_session(output, *, emulator, iso, manifest):
    validate_declaration(manifest)
    output = Path(output).resolve(strict=True)
    state = output / 'starting.ppst'
    emulator, iso = Path(emulator).resolve(strict=True), Path(iso).resolve(strict=True)
    need(sha(emulator) == manifest['emulator_sha256'] and sha(iso) == manifest['iso_sha256'] and
         sha(state) == manifest['starting_state_sha256'], 'Native load inputs changed before request creation')
    session = output / 'native-load-session'
    session.mkdir(mode=0o700)
    fields = (secrets.token_hex(16), secrets.token_hex(16), secrets.token_hex(16),
        Path('/proc/sys/kernel/random/boot_id').read_text().strip(), '1',
        'host-audit:' + manifest['identity']['game_id'], str(iso), manifest['iso_sha256'],
        manifest['emulator_sha256'], str(output), 'resume', str(state), manifest['starting_state_sha256'],
        FORMAT, str(manifest['native_slot']))
    request = encode_packet(b'TPSE1Q\n', fields)
    _private_bytes(session / 'request', request)
    context = {'schema': 1, 'kind': 'development-native-load-probe', 'grants_production_authority': False,
        'request_fields': list(fields), 'request_sha256': hashlib.sha256(request).hexdigest(),
        'engine_size': emulator.stat().st_size, 'iso_size': iso.stat().st_size, 'state_size': state.stat().st_size,
        'disc_id': manifest['identity']['game_id'], 'disc_version': manifest['native_disc_version'],
        'engine_version': manifest['identity']['emulator']['version'], 'architecture': manifest['native_architecture'],
        'created_monotonic_ns': time.monotonic_ns()}
    _private_bytes(session / 'context.json', (json.dumps(context, indent=2) + '\n').encode())
    directory = os.open(session, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return context


def read_context(output):
    return json.loads(_read_private(Path(output) / 'native-load-session/context.json'))


def expected_result(context):
    q = context['request_fields']
    return tuple(q[:6]) + ('load', '1', 'success', None, context['disc_id'], context['disc_version'],
        context['disc_id'] + '_' + context['disc_version'], q[6], q[8], q[7], q[12],
        str(context['engine_size']), str(context['iso_size']), str(context['state_size']), q[11], q[14],
        UPSTREAM, 'trimui-slot-evidence-v1', context['engine_version'], context['architecture'], FORMAT)


def verify_load_session(output, context, manifest):
    """Check actual native success packets and unchanged copied state.

    The native slot is trusted-caller metadata. This private comparison binds it
    to the explicit fixture declaration; it does not authenticate that declaration
    or grant any production session/profile/freshness capability.
    """
    output = Path(output)
    session = output / 'native-load-session'
    directory = session.lstat()
    need(stat.S_ISDIR(directory.st_mode) and directory.st_uid == os.getuid() and
         stat.S_IMODE(directory.st_mode) == 0o700, 'Native load session lost private ownership')
    request_raw = _read_private(session / 'request')
    request = _decode_packet(request_raw, b'TPSE1Q\n', 15)
    need(hashlib.sha256(request_raw).hexdigest() == context['request_sha256'] and
         request == tuple(context['request_fields']), 'Native load request differs from retained fresh context')
    validate_declaration(manifest)
    need(request[5] == 'host-audit:' + manifest['identity']['game_id'] and request[7] == manifest['iso_sha256'] and
         request[8] == manifest['emulator_sha256'] and request[9] == str(output.resolve()) and
         request[10] == 'resume' and request[11] == str((output / 'starting.ppst').resolve()) and
         request[12] == manifest['starting_state_sha256'] and request[13] == FORMAT and
         request[14] == str(manifest['native_slot']) and context['disc_id'] == manifest['identity']['game_id'] and
         context['disc_version'] == manifest['native_disc_version'] and
         context['engine_version'] == manifest['identity']['emulator']['version'] and
         context['architecture'] == manifest['native_architecture'], 'Native load context differs from frozen manifest')
    result_raw = _read_private(session / 'result')
    result = _decode_packet(result_raw, b'TPSE1R\n', 27)
    need(result[:6] == request[:6], 'Native load acknowledgement belongs to another session')
    need(result[6:9] == ('load', '1', 'success'), 'Native starting-state load failed or has stale sequence')
    completed_raw = _read_private(session / 'load-completed')
    completed = _decode_packet(completed_raw, b'TPSE1R\n', 27)
    need(completed == result and completed_raw == result_raw,
         'Native load completion differs from final result or is incompletely published')
    expected = expected_result(context)
    need(all(wanted is None or observed == wanted for observed, wanted in zip(result, expected)),
         'Native load evidence differs from exact game/engine/state/slot/format identity')
    state = output / 'starting.ppst'
    need(state.is_file() and not state.is_symlink() and state.stat().st_size == context['state_size'] and
         sha(state) == request[12], 'Copied starting state changed after actual native load')
    return {'request_sha256': hashlib.sha256(request_raw).hexdigest(),
        'result_sha256': hashlib.sha256(result_raw).hexdigest(),
        'load_completed_sha256': hashlib.sha256(completed_raw).hexdigest(),
        'context_sha256': sha(session / 'context.json'), 'operation': 'load', 'sequence': 1, 'status': 'success',
        'state_sha256': request[12], 'native_slot': manifest['native_slot'], 'source_format': FORMAT,
        'grants_production_authority': False}
