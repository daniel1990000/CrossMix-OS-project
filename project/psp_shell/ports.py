"""Owner-selected port data imports; no game data or executable downloads.

The existing spruce/PortMaster launchers and engines remain authoritative.
Callers must hold the session's maintenance gate before confirming idle. Hashes
detect stale previews and external edits; they are not DRM or licence checks.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
import uuid

DEFAULT_PROFILES = Path(__file__).resolve().parents[1] / 'profiles/ports.json'
CHUNK = 1024 * 1024
MAX_FILES = 10000


class PortError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code

    def as_dict(self):
        return {'code': self.code, 'message': str(self)}


def _require(value, code, message):
    if not value:
        raise PortError(code, message)


def _safe(root: Path, relative: str) -> Path:
    _require(isinstance(relative, str) and relative and '\\' not in relative
             and ':' not in relative and '\0' not in relative
             and all(p not in ('', '.', '..') for p in relative.split('/')),
             'UNSAFE_PATH', 'A port path is not a safe relative path')
    target = root.joinpath(*relative.split('/'))
    _require(not relative.startswith('/'), 'UNSAFE_PATH', 'Absolute port paths are rejected')
    for part in (root, *target.relative_to(root).parents):
        candidate = part if part.is_absolute() else root / part
        _require(not candidate.is_symlink(), 'UNSAFE_PATH', 'Port paths cannot traverse symlinks')
    _require(not target.is_symlink(), 'UNSAFE_PATH', 'Port files cannot be symlinks')
    return target


def _fingerprint(path: Path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None, 0
    except OSError as error:
        raise PortError('UNSAFE_PATH', 'A port file cannot be opened safely') from error
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        _require(stat.S_ISREG(before.st_mode), 'UNSAFE_PATH', 'Only regular port files are supported')
        digest = hashlib.sha256()
        size = 0
        while chunk := stream.read(CHUNK):
            size += len(chunk)
            digest.update(chunk)
        after = os.fstat(stream.fileno())
    _require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
             'CONFLICT', 'A port file changed while it was read')
    return digest.hexdigest(), size


def _copy_checked(source: Path, destination: Path, expected: str):
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    digest = hashlib.sha256()
    with os.fdopen(fd, 'rb') as incoming, destination.open('xb') as outgoing:
        _require(stat.S_ISREG(os.fstat(incoming.fileno()).st_mode),
                 'UNSAFE_PATH', 'Only regular owner files are supported')
        while chunk := incoming.read(CHUNK):
            digest.update(chunk)
            outgoing.write(chunk)
        outgoing.flush()
        os.fsync(outgoing.fileno())
    _require(digest.hexdigest() == expected, 'CONFLICT', 'A port file changed after preview')


def _sync(directory: Path):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _json_write(path: Path, value):
    data = (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + '\n').encode()
    descriptor, temporary = tempfile.mkstemp(prefix='.receipt-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _install(source: Path, target: Path, digest: str):
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.port-data-', dir=target.parent)
    os.close(descriptor)
    os.unlink(temporary)
    try:
        _copy_checked(source, Path(temporary), digest)
        os.replace(temporary, target)
        _sync(target.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@dataclass(frozen=True)
class ImportFile:
    source: str
    target: str
    sha256: str
    size: int
    before_sha256: str | None
    before_size: int


@dataclass(frozen=True)
class ImportPreview:
    token: str
    port_id: str
    source: str
    sd_root: str
    single_source: bool
    files: tuple[ImportFile, ...]
    required_bytes: int
    free_bytes: int
    warnings: tuple[str, ...]

    def as_dict(self):
        result = asdict(self)
        result['overwrites'] = [f.target for f in self.files if f.before_sha256 is not None]
        result['validation'] = 'structure and selected-file hashes; runtime compatibility pending'
        result['requires_idle'] = True
        return result


class PortsManager:
    def __init__(self, sd_root, state_dir=None, profiles_file=None):
        given = Path(sd_root).absolute()
        _require(not any(p.is_symlink() for p in (given, *given.parents)),
                 'UNSAFE_PATH', 'The SD root cannot traverse a symlink')
        _require(given.is_dir(), 'MISSING_STORAGE', 'Select an existing SD-card root')
        self.root = given.resolve()
        self.state = Path(state_dir) if state_dir else self.root / 'Saves/psp-shell/port-imports'
        self.state = self.state.absolute()
        _require(self.state.is_relative_to(self.root), 'UNSAFE_PATH', 'Port receipts must stay on the selected card')
        payload = json.loads(Path(profiles_file or DEFAULT_PROFILES).read_text())
        _require(payload.get('schema') == 1, 'UNSUPPORTED_SCHEMA', 'Unsupported port-profile schema')
        self._profiles = {p['id']: p for p in payload['ports']}
        self._previews = {}

    def profiles(self):
        return json.loads(json.dumps(list(self._profiles.values())))

    def _profile(self, port_id):
        _require(port_id in self._profiles, 'UNKNOWN_PORT', 'Unknown port profile')
        profile = self._profiles[port_id]
        _require(profile.get('enabled') is True, 'EXPERIMENTAL', 'This experimental port has no supported import contract')
        _safe(self.root, profile['directory'])
        return profile

    @contextmanager
    def _lock(self):
        relative = self.state.relative_to(self.root).as_posix()
        _safe(self.root, relative)
        self.state.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.state / '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'rb') as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def preview_import(self, port_id, source) -> ImportPreview:
        profile = self._profile(port_id)
        source = Path(source).absolute()
        _require(not any(p.is_symlink() for p in (source, *source.parents)),
                 'UNSAFE_PATH', 'Owner files cannot traverse symlinks')
        _require(source.exists(), 'MISSING_OWNER_FILES', 'Select your own supported game files')
        source = source.resolve()
        destination = _safe(self.root, profile['directory'])
        _require(not source.is_relative_to(destination) and not destination.is_relative_to(source),
                 'UNSAFE_PATH', 'Owner source and installed port must be separate trees')
        single = source.is_file()
        selected = []
        if profile['layout'] == 'single_file':
            candidate = source if single else _safe(source, profile['import_name'])
            _require(candidate.is_file(), 'MISSING_OWNER_FILES', f"Select {profile['import_name']}")
            selected = [(candidate.name if single else profile['import_name'], profile['import_name'])]
        else:
            _require(source.is_dir(), 'MISSING_OWNER_FILES', 'Select the original game-data directory')
            for folder, directories, filenames in os.walk(source, followlinks=False):
                _require(not any((Path(folder) / d).is_symlink() for d in directories),
                         'UNSAFE_PATH', 'Owner data contains a symlink directory')
                for filename in filenames:
                    path = Path(folder) / filename
                    relative = path.relative_to(source).as_posix()
                    _safe(source, relative)
                    if profile['layout'] == 'classic_gta' and relative.split('/')[0].lower() not in profile['allowed_roots']:
                        continue
                    selected.append((relative, relative))
                    _require(len(selected) <= MAX_FILES, 'TOO_MANY_FILES', 'Too many owner files in this selection')
        _require(selected, 'MISSING_OWNER_FILES', 'The selection contains no supported owner files')
        names = {target.casefold() for _, target in selected}
        _require(len(names) == len(selected), 'CASE_COLLISION', 'FAT32 names would collide in this selection')
        for required in profile.get('required_files', []):
            _require(required.casefold() in names, 'MISSING_OWNER_FILES', f'Missing required owner file: {required}')
        for required in profile.get('required_directories', []):
            _require(any(n.startswith(required.casefold() + '/') for n in names),
                     'MISSING_OWNER_FILES', f'Missing nonempty owner directory: {required}')
        records = []
        for relative, target_name in sorted(selected):
            src = source if single else _safe(source, relative)
            digest, size = _fingerprint(src)
            _require(digest is not None and size <= 0xffffffff,
                     'INVALID_OWNER_FILE', 'Owner files must be regular files within FAT32 limits')
            if single or target_name.casefold() in {n.casefold() for n in profile.get('required_files', [])}:
                _require(size > 0, 'INVALID_OWNER_FILE', 'A required owner file is empty')
            if profile.get('md5') or profile.get('sha1'):
                with src.open('rb') as stream:
                    data_hashes = {'md5': hashlib.md5(), 'sha1': hashlib.sha1()}
                    while chunk := stream.read(CHUNK):
                        for value in data_hashes.values():
                            value.update(chunk)
                for name in ('md5', 'sha1'):
                    if profile.get(name):
                        _require(data_hashes[name].hexdigest() == profile[name], 'WRONG_GAME_VERSION',
                                 'The selected ROM does not match the documented US version')
            target = profile['directory'] + '/' + target_name
            previous, previous_size = _fingerprint(_safe(self.root, target))
            records.append(ImportFile(relative, target, digest, size, previous, previous_size))
        required_bytes = sum(f.size + f.before_size for f in records) + profile.get('workspace_bytes', 0) + 5 * CHUNK
        free = shutil.disk_usage(self.root).free
        _require(free >= required_bytes, 'STORAGE_FULL', 'Not enough space for staged data, backups and first-launch workspace')
        preview = ImportPreview(uuid.uuid4().hex, port_id, str(source), str(self.root), single,
                                tuple(records), required_bytes, free, tuple(profile.get('warnings', [])))
        self._previews[preview.token] = preview
        return preview

    def cancel_import(self, preview):
        self._previews.pop(preview.token, None)

    def apply_import(self, preview, confirm_overwrite=False, confirm_idle=False) -> Path:
        _require(confirm_idle, 'BUSY', 'Enter idle maintenance mode before importing owner files')
        _require(self._previews.get(preview.token) is preview and preview.sd_root == str(self.root),
                 'STALE_PREVIEW', 'Preview this owner-data import again')
        _require(confirm_overwrite or not any(f.before_sha256 for f in preview.files),
                 'CONFIRM_OVERWRITE', 'Review and confirm replacement of existing port data')
        profile = self._profile(preview.port_id)
        with self._lock():
            _require(shutil.disk_usage(self.root).free >= preview.required_bytes,
                     'STORAGE_FULL', 'Storage changed after preview; free space and preview again')
            records, sources = [], []
            for item in preview.files:
                target = _safe(self.root, item.target)
                _require(item.target.startswith(profile['directory'] + '/'), 'UNSAFE_PATH', 'Import escaped its port')
                _require(_fingerprint(target)[0] == item.before_sha256,
                         'CONFLICT', 'Installed port data changed after preview')
                src = Path(preview.source) if preview.single_source else _safe(Path(preview.source), item.source)
                _require(_fingerprint(src)[0] == item.sha256, 'CONFLICT', 'Owner data changed after preview')
                records.append({'target': item.target, 'before': item.before_sha256, 'after': item.sha256})
                sources.append(src)
            transaction = self._transaction(preview.port_id, 'owner-import', records, sources)
            self._previews.pop(preview.token, None)
            return transaction

    def _transaction(self, port_id, kind, records, sources):
        folder = self.state / (str(time.time_ns()) + '-' + uuid.uuid4().hex)
        folder.mkdir(mode=0o700)
        receipt = {'schema': 1, 'root': str(self.root), 'port_id': port_id, 'kind': kind,
                   'phase': 'preparing', 'files': records}
        _json_write(folder / 'receipt.json', receipt)
        try:
            for index, (record, source) in enumerate(zip(records, sources)):
                target = _safe(self.root, record['target'])
                _require(_fingerprint(target)[0] == record['before'], 'CONFLICT', 'Port data changed while staging')
                if record['before'] is not None:
                    _copy_checked(target, folder / f'backup/{index}', record['before'])
                if record['after'] is not None:
                    _copy_checked(source, folder / f'incoming/{index}', record['after'])
            receipt['phase'] = 'applying'
            _json_write(folder / 'receipt.json', receipt)
            for index, record in enumerate(records):
                target = _safe(self.root, record['target'])
                _require(_fingerprint(target)[0] == record['before'], 'CONFLICT', 'Port data changed before replacement')
                if record['after'] is None:
                    if target.exists():
                        target.unlink()
                        _sync(target.parent)
                else:
                    _install(folder / f'incoming/{index}', target, record['after'])
            receipt['phase'] = 'applied'
            _json_write(folder / 'receipt.json', receipt)
            return folder
        except Exception as error:
            if receipt['phase'] == 'applying':
                try:
                    self._rollback(folder, receipt)
                except Exception as rollback_error:
                    raise PortError('RECOVERY_REQUIRED', 'Import stopped; retain its receipt and backups for recovery') from rollback_error
            else:
                receipt['phase'] = 'aborted-before-apply'
                _json_write(folder / 'receipt.json', receipt)
            if isinstance(error, PortError):
                raise
            raise PortError('STORAGE_ERROR', 'Import failed; previously applied files were restored') from error

    def _receipt(self, folder):
        folder = Path(folder).absolute()
        _require(folder.parent == self.state and not folder.is_symlink(),
                 'UNSAFE_PATH', 'Select a receipt from this card')
        receipt_path = _safe(folder, 'receipt.json')
        descriptor = os.open(receipt_path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'rb') as stream:
            _require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'INVALID_RECEIPT', 'Receipt must be a regular file')
            data = stream.read(8 * CHUNK + 1)
        _require(len(data) <= 8 * CHUNK, 'INVALID_RECEIPT', 'Receipt is too large')
        value = json.loads(data)
        _require(value.get('schema') == 1 and value.get('root') == str(self.root),
                 'INVALID_RECEIPT', 'Receipt belongs to another card or schema')
        profile = self._profile(value.get('port_id'))
        _require(isinstance(value.get('files'), list) and len(value['files']) <= MAX_FILES,
                 'INVALID_RECEIPT', 'Invalid receipt file list')
        settings = self._setting_targets(profile)
        for record in value['files']:
            _safe(self.root, record['target'])
            if value.get('kind') == 'owner-import':
                _require(record['target'].startswith(profile['directory'] + '/'), 'UNSAFE_PATH', 'Receipt escaped its port')
            else:
                _require(record['target'] in settings, 'UNSAFE_PATH', 'Receipt escaped its settings profile')
        return folder, value

    def _rollback(self, folder, receipt):
        _require(receipt['phase'] in ('applying', 'applied'), 'INVALID_STATE', 'This import is not active')
        # Validate every live file and every backup before the first undo write.
        for index, record in enumerate(receipt['files']):
            current = _fingerprint(_safe(self.root, record['target']))[0]
            _require(current in (record['before'], record['after']),
                     'CONFLICT', 'Port data changed externally; undo would overwrite it')
            if record['before'] is not None:
                backup = _safe(folder, f'backup/{index}')
                _require(_fingerprint(backup)[0] == record['before'], 'INVALID_BACKUP', 'An import backup is missing or damaged')
        for index, record in reversed(list(enumerate(receipt['files']))):
            target = _safe(self.root, record['target'])
            if _fingerprint(target)[0] == record['before']:
                continue
            if record['before'] is None:
                target.unlink()
                _sync(target.parent)
            else:
                _install(folder / f'backup/{index}', target, record['before'])
        receipt['phase'] = 'rolled-back'
        _json_write(folder / 'receipt.json', receipt)

    def rollback_import(self, transaction, confirm_idle=False):
        _require(confirm_idle, 'BUSY', 'Enter idle maintenance mode before undoing an import')
        with self._lock():
            folder, receipt = self._receipt(transaction)
            self._rollback(folder, receipt)

    def _setting_targets(self, profile):
        base = profile.get('settings_directory', profile['directory'])
        return [base + '/' + name for name in profile.get('settings', [])]

    def snapshot_profile(self, port_id, confirm_idle=False) -> Path:
        _require(confirm_idle, 'BUSY', 'Enter idle maintenance mode before snapshotting port settings')
        profile = self._profile(port_id)
        with self._lock():
            folder = self.state / ('profile-' + uuid.uuid4().hex)
            folder.mkdir(mode=0o700)
            records = []
            for index, target_name in enumerate(self._setting_targets(profile)):
                target = _safe(self.root, target_name)
                digest, size = _fingerprint(target)
                if digest is not None:
                    _copy_checked(target, folder / f'files/{index}', digest)
                records.append({'target': target_name, 'sha256': digest, 'size': size})
            _json_write(folder / 'receipt.json', {'schema': 1, 'root': str(self.root),
                        'port_id': port_id, 'kind': 'profile-snapshot', 'phase': 'snapshot', 'files': records})
            return folder

    def preview_profile_restore(self, snapshot):
        folder, receipt = self._receipt(snapshot)
        _require(receipt['kind'] == 'profile-snapshot', 'INVALID_RECEIPT', 'Select a port-settings snapshot')
        return {'snapshot': folder.name, 'files': [
            {'target': r['target'], 'current': _fingerprint(_safe(self.root, r['target']))[0],
             'snapshot': r['sha256']} for r in receipt['files']]}

    def restore_profile(self, snapshot, preview, confirm_overwrite=False, confirm_idle=False):
        _require(confirm_idle, 'BUSY', 'Enter idle maintenance mode before restoring port settings')
        _require(confirm_overwrite, 'CONFIRM_OVERWRITE', 'Review and confirm the port-settings restore')
        with self._lock():
            folder, receipt = self._receipt(snapshot)
            _require(preview == self.preview_profile_restore(folder), 'CONFLICT', 'Port settings changed after restore preview')
            records, sources = [], []
            for index, (record, live) in enumerate(zip(receipt['files'], preview['files'])):
                source = _safe(folder, f'files/{index}')
                if record['sha256'] is not None:
                    _require(_fingerprint(source)[0] == record['sha256'], 'INVALID_BACKUP', 'Settings snapshot is damaged')
                records.append({'target': record['target'], 'before': live['current'], 'after': record['sha256']})
                sources.append(source)
            return self._transaction(receipt['port_id'], 'profile-restore', records, sources)
