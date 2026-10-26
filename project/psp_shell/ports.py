"""Owner-selected port data imports; no game data or executable downloads.

The existing spruce/PortMaster launchers and engines remain authoritative.
Callers must hold the session's maintenance gate before confirming idle. Hashes
detect stale previews and external edits; they are not DRM or licence checks.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import ast
import fnmatch
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import tempfile
import time
import uuid

from .controls import _open_regular

DEFAULT_PROFILES = Path(__file__).resolve().parents[1] / 'profiles/ports.json'
CHUNK = 1024 * 1024
MAX_FILES = 10000
MAX_OWNER_FILE = 0xffffffff


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


def _fingerprint(path: Path, *, read_header=False):
    try:
        fd = _open_regular(path)
    except FileNotFoundError:
        return (None, 0, b'') if read_header else (None, 0)
    except OSError as error:
        raise PortError('UNSAFE_PATH', 'A port file cannot be opened safely') from error
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        _require(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_OWNER_FILE,
                 'UNSAFE_PATH', 'Only bounded regular port files are supported')
        digest = hashlib.sha256()
        size = 0
        header = b''
        while size < before.st_size:
            chunk = stream.read(min(CHUNK, before.st_size - size))
            _require(chunk, 'CONFLICT', 'A port file shrank while it was read')
            size += len(chunk)
            if not header:
                header = chunk[:64]
            digest.update(chunk)
        _require(not stream.read(1), 'CONFLICT', 'A port file grew while it was read')
        after = os.fstat(stream.fileno())
        named = path.lstat()
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    _require(identity(before) == identity(after) == identity(named),
             'CONFLICT', 'A port file changed while it was read')
    return (digest.hexdigest(), size, header) if read_header else (digest.hexdigest(), size)


def _copy_checked(source: Path, destination: Path, expected: str):
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = _open_regular(source)
    digest = hashlib.sha256()
    with os.fdopen(fd, 'rb') as incoming, destination.open('xb') as outgoing:
        before = os.fstat(incoming.fileno())
        _require(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_OWNER_FILE,
                 'UNSAFE_PATH', 'Only bounded regular owner files are supported')
        size = 0
        while size < before.st_size:
            chunk = incoming.read(min(CHUNK, before.st_size - size))
            _require(chunk, 'CONFLICT', 'An owner file shrank while it was copied')
            size += len(chunk)
            digest.update(chunk)
            outgoing.write(chunk)
        _require(not incoming.read(1), 'CONFLICT', 'An owner file grew while it was copied')
        after, named = os.fstat(incoming.fileno()), source.lstat()
        identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        _require(identity(before) == identity(after) == identity(named), 'CONFLICT', 'An owner file changed during copying')
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
        self._source_contract = payload.get('portmaster_surface', {})
        self._previews = {}

    def profiles(self):
        return json.loads(json.dumps(list(self._profiles.values())))

    def _installed_file(self, relative, kind='file', source_sha256=None):
        """Observe a named file without sourcing scripts, mounting or executing."""
        result = {'path': relative, 'present': False, 'kind': kind}
        try:
            digest, size, header = _fingerprint(_safe(self.root, relative), read_header=True)
            result.update(present=digest is not None and size > 0, sha256=digest, size=size)
            if source_sha256:
                result['pinned_text_matches'] = digest == source_sha256
            if kind == 'aarch64_elf':
                elf = len(header) >= 20 and header[:6] == b'\x7fELF\x02\x01'
                result['aarch64_elf'] = bool(elf and struct.unpack_from('<H', header, 18)[0] == 183)
            elif kind == 'squashfs':
                result['squashfs_magic'] = header[:4] in (b'hsqs', b'sqsh')
        except (PortError, OSError) as error:
            result['error'] = {'code': getattr(error, 'code', 'STORAGE_ERROR'), 'message': str(error)}
        return result

    def portmaster_status(self):
        """Card-local inputs of the existing spruce PortMaster authority."""
        contract = self._source_contract
        observations = [self._installed_file(item['path'], source_sha256=item.get('source_sha256'))
                        for item in contract.get('files', [])]
        base = 'Persistent/portmaster/PortMaster/'
        def syntax(relative):
            try:
                path = _safe(self.root, base + relative)
                with os.fdopen(_open_regular(path), 'rb') as stream:
                    raw = stream.read(128 * 1024 + 1)
                _require(len(raw) <= 128 * 1024, 'TOO_LARGE', 'Platform source exceeds its read budget')
                return ast.parse(raw.decode('utf-8'))
            except (OSError, PortError, SyntaxError, UnicodeError, ValueError):
                return None
        legacy = syntax('pylibs/harbourmaster/platform.py')
        package = syntax('pylibs/harbourmaster/platform/miyoo.py')
        registration = syntax('pylibs/harbourmaster/platform/__init__.py')
        has_class = lambda tree: tree is not None and any(isinstance(n, ast.ClassDef) and n.name == 'PlatformSpruce' for n in ast.walk(tree))
        registered = registration is not None and any(
            isinstance(node, ast.Dict) and any(isinstance(k, ast.Constant) and k.value == 'spruce'
                and isinstance(v, ast.Name) and v.id == 'PlatformSpruce' for k, v in zip(node.keys, node.values))
            for node in ast.walk(registration))
        generation = ('native-package' if has_class(package) and registered else
                      'legacy-single-file' if has_class(legacy) else 'compatibility-or-incomplete')
        pending = any(r['path'] == base + 'pylibs.zip' and r['present'] for r in observations)
        return {'schema': 1, 'authority': 'existing spruce App/PortMaster and initialized PyUI tool callback',
                'files': observations, 'native_platform_support_observed': False,
                'detected_source_generation': generation,
                'installed_generation': 'self-update-pending' if pending else generation,
                'package_registration_observed': bool(has_class(package) and registered),
                'legacy_marker_only': legacy is not None and not legacy.body,
                'self_update_pending': pending,
                'runtime_qualified': False, 'executed': False,
                'notes': ['Presence and text hashes do not evaluate control.txt or PlatformSpruce.',
                          'Existing PortMaster chooses and prepares its control/GUI route at launch.']}

    def _directory_status(self, relative):
        result = {'path': relative, 'nonempty_directory': False}
        try:
            path = _safe(self.root, relative)
            if path.is_dir():
                with os.scandir(path) as children:
                    child = next(children, None)
                    if child is not None:
                        _safe(self.root, relative + '/' + child.name)
                        result['nonempty_directory'] = True
        except (PortError, OSError) as error:
            result['error'] = {'code': getattr(error, 'code', 'STORAGE_ERROR'), 'message': str(error)}
        return result

    def _library_directory(self, relative):
        result = {'path': relative, 'files': [], 'complete': True}
        try:
            path = _safe(self.root, relative)
            if not path.is_dir():
                result['complete'] = False
                return result
            with os.scandir(path) as entries:
                # Fixed enumeration budget, before sorting or hashing.
                children = []
                for entry in entries:
                    _require(len(children) < 256, 'TOO_MANY_FILES', 'Library directory exceeded its inventory budget')
                    children.append(entry.name)
            for name in sorted(children):
                target = relative + '/' + name
                if _safe(self.root, target).is_dir():
                    result['complete'] = False  # Nested libraries require separate inspection.
                    continue
                result['files'].append(self._installed_file(target))
            result['complete'] = result['complete'] and bool(result['files']) and all(r['present'] for r in result['files'])
        except (PortError, OSError) as error:
            result['complete'] = False
            result['error'] = {'code': getattr(error, 'code', 'STORAGE_ERROR'), 'message': str(error)}
        return result

    def installed_status(self, port_id):
        """Read-only owner-data, installed launcher, engine and runtime inventory.

        File names and engine alternatives come from exact pinned text sources.
        An AArch64 ELF header or squashfs magic establishes file form only; it
        does not prove the loader, graphics driver, libraries or game behavior.
        """
        profile = self._profile(port_id)
        installation = profile.get('installation', {})
        _require(isinstance(installation, dict), 'UNSUPPORTED_SCHEMA', 'Port installation contract is invalid')
        owner = [self._installed_file(profile['directory'] + '/' + name)
                 for name in profile.get('required_files', [])]
        directories = []
        for name in profile.get('required_directories', []):
            relative = profile['directory'] + '/' + name
            entry = {'path': relative, 'nonempty_directory': False}
            try:
                path = _safe(self.root, relative)
                if path.is_dir():
                    with os.scandir(path) as children:
                        entry['nonempty_directory'] = next(children, None) is not None
            except (PortError, OSError) as error:
                entry['error'] = {'code': getattr(error, 'code', 'STORAGE_ERROR'), 'message': str(error)}
            directories.append(entry)
        launcher = self._installed_file(installation['launcher'], source_sha256=installation.get('launcher_source_sha256')) \
            if installation.get('launcher') else None
        engines = [self._installed_file(path, 'aarch64_elf') for path in installation.get('engine_alternatives', [])]
        support = [self._installed_file(path) for path in installation.get('support_files', [])]
        runtimes = [self._installed_file(path, 'squashfs') for path in installation.get('runtime_files', [])]
        libraries = [self._library_directory(path) for path in installation.get('library_directories', [])]
        preparation = installation.get('preparation', {})
        prepared_files = [self._installed_file(path) for path in preparation.get('files', [])]
        prepared_directories = [self._directory_status(path) for path in preparation.get('directories', [])]
        # Celeste's completion marker is intentionally empty; file existence is
        # an observation only, never successful texture/runtime qualification.
        prepared = bool(preparation) and all(r['present'] or (r['path'].endswith('/.astc_done') and
            r.get('sha256') is not None) for r in prepared_files) and all(
            r['nonempty_directory'] for r in prepared_directories)
        owner_present = all(item['present'] for item in owner) and all(item['nonempty_directory'] for item in directories)
        components = all(r['present'] for r in support) and all(r.get('squashfs_magic') is True for r in runtimes)
        engine = any(r.get('aarch64_elf') is True for r in engines) if engines else any(r.get('squashfs_magic') is True for r in runtimes)
        data_available = owner_present or (prepared and preparation.get('replaces_owner_input') is True)
        stage = ('prepared-inputs-observed' if prepared and data_available else
                 'owner-inputs-observed' if owner_present else 'owner-inputs-missing')
        blockers = []
        if not launcher or not launcher['present']: blockers.append('LAUNCHER_MISSING')
        if not engine: blockers.append('ENGINE_OR_MANAGED_RUNTIME_MISSING')
        if not components: blockers.append('SUPPORT_OR_RUNTIME_MISSING')
        if libraries and not all(v['complete'] for v in libraries): blockers.append('LIBRARY_INVENTORY_INCOMPLETE')
        if not data_available: blockers.append('OWNER_INPUTS_OR_PREPARATION_MISSING')
        if preparation and not prepared: blockers.append('PREPARATION_NOT_OBSERVED')
        return {'schema': 1, 'port_id': port_id, 'title': profile['title'], 'owner_files': owner,
                'owner_directories': directories, 'owner_input_structure_present':
                    all(item['present'] for item in owner) and all(item['nonempty_directory'] for item in directories),
                'launcher': launcher, 'engine_alternatives': engines,
                'native_engine_header_present': any(item.get('aarch64_elf') is True for item in engines),
                'support_files': support, 'runtime_files': runtimes,
                'library_directories': libraries,
                'readiness': {'stage': stage, 'blockers': blockers, 'launch_qualified': False,
                              'prepared_files': prepared_files, 'prepared_directories': prepared_directories,
                              'preparation_observed': prepared},
                'resume_capability': profile.get('resume_capability', 'launch-only'),
                'save_registry': profile.get('save_registry', {}),
                'portmaster': self.portmaster_status(), 'runtime_qualified': False, 'measured_fps': None,
                'source_binary_correspondence_verified': False, 'distribution_cleared': False,
                'executed': False, 'inventory_scope': 'named inputs and bounded local library inventory; no loader or mount qualification',
                'existing_launch_surface': {'system_id': 'PORTS', 'launcher': installation.get('launcher'),
                    'tool_id': 'app:PortMaster', 'authority': 'existing initialized SpruceBackend callbacks'}}

    def resolve_existing_port(self, port_id, backend):
        """Resolve the installed library item through the existing token owner.

        Returns its original context unchanged. Inventory never creates a
        launch permission or substitutes a shell command/process authority.
        The caller hands that context to its existing Coordinator as usual.
        """
        from .adapters.spruce import SpruceBackend
        _require(isinstance(backend, SpruceBackend) and backend.provider.root == self.root,
                 'INVALID_BACKEND', 'Use the existing backend for this exact card')
        profile = self._profile(port_id)
        relative = profile.get('installation', {}).get('launcher')
        _require(isinstance(relative, str), 'UNSUPPORTED_SCHEMA', 'No source-backed installed launcher is declared')
        matches = []
        for offset in range(0, MAX_FILES, 200):
            page = backend.games('PORTS', offset=offset, limit=200)
            matches.extend(item for item in page['items'] if item.get('relative_path') == relative)
            if offset + 200 >= page['total']:
                break
        else:
            raise PortError('TOO_MANY_FILES', 'The existing ports collection exceeds its lookup budget')
        _require(len(matches) == 1, 'EXISTING_PORT_UNAVAILABLE', 'Install and refresh this port through existing PortMaster first')
        return backend.resolve_game(matches[0]['id'], mode='normal')

    def resolve_existing_portmaster(self, backend):
        """Reuse the existing app tool token; never execute its script here."""
        from .adapters.spruce import SpruceBackend
        _require(isinstance(backend, SpruceBackend) and backend.provider.root == self.root,
                 'INVALID_BACKEND', 'Use the existing backend for this exact card')
        return backend.resolve_tool('app:PortMaster')

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
            elif value.get('kind') == 'save-restore':
                _require(self._save_allowed(profile, record['target']), 'UNSAFE_PATH', 'Receipt escaped its save registry')
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
            current = _fingerprint(target)[0]
            _require(current in (record['before'], record['after']),
                     'CONFLICT', 'Port data changed during undo; retain the receipt and backups')
            if current == record['before']:
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

    def _save_allowed(self, profile, relative):
        registry = profile.get('save_registry', {})
        return any(relative.startswith(directory + '/') for directory in registry.get('directories', [])) or any(
            relative.rsplit('/', 1)[0] == pattern.rsplit('/', 1)[0]
            and fnmatch.fnmatchcase(relative.rsplit('/', 1)[1].casefold(), pattern.rsplit('/', 1)[1].casefold())
            for pattern in registry.get('file_patterns', []))

    def save_inventory(self, port_id):
        """Inspect only the declared preservation scope; do not infer completeness."""
        profile = self._profile(port_id)
        registry = profile.get('save_registry', {})
        names, visited = set(), 0
        for directory in registry.get('directories', []):
            root = _safe(self.root, directory)
            if not root.exists():
                continue
            _require(root.is_dir(), 'UNSAFE_PATH', 'A declared save directory is not a directory')
            def walk_error(error):
                raise PortError('STORAGE_ERROR', 'Save directory could not be fully inventoried') from error
            for folder, directories, filenames in os.walk(root, followlinks=False, onerror=walk_error):
                visited += len(directories) + len(filenames)
                _require(visited <= MAX_FILES, 'TOO_MANY_FILES', 'Save inventory exceeded its entry budget')
                for name in directories + filenames:
                    relative = (Path(folder) / name).relative_to(self.root).as_posix()
                    _safe(self.root, relative)
                    if name in filenames:
                        names.add(relative)
        for pattern in registry.get('file_patterns', []):
            parent, wildcard = pattern.rsplit('/', 1)
            directory = _safe(self.root, parent)
            if not directory.exists():
                continue
            with os.scandir(directory) as entries:
                for entry in entries:
                    visited += 1
                    _require(visited <= MAX_FILES, 'TOO_MANY_FILES', 'Save inventory exceeded its entry budget')
                    if fnmatch.fnmatchcase(entry.name.casefold(), wildcard.casefold()):
                        relative = parent + '/' + entry.name
                        _safe(self.root, relative)
                        names.add(relative)
        files = []
        for relative in sorted(names):
            digest, size = _fingerprint(_safe(self.root, relative))
            _require(digest is not None, 'CONFLICT', 'A save disappeared during inventory')
            files.append({'target': relative, 'sha256': digest, 'size': size})
        return {'schema': 1, 'port_id': port_id, 'files': files, 'registry': registry,
                'device_paths_verified': False, 'resume_capability': profile.get('resume_capability', 'launch-only'),
                'uninstall_enabled': False,
                'uninstall_contract': 'Retain a verified external backup and owner originals. Use PortMaster for removal; verify actual device save paths first. No deletion is performed here.'}

    def snapshot_saves(self, port_id, output, *, confirm_idle=False):
        _require(confirm_idle, 'BUSY', 'Stop the game and enter idle maintenance mode before backing up saves')
        output = Path(output).absolute()
        _require(not any(p.is_symlink() for p in (output, *output.parents)) and not output.exists(),
                 'UNSAFE_PATH', 'Use a new external backup directory without symlinks')
        output = output.resolve(strict=False)
        _require(not output.is_relative_to(self.root) and not self.root.is_relative_to(output),
                 'UNSAFE_PATH', 'Save backups must be outside the selected card')
        with self._lock():
            inventory = self.save_inventory(port_id)
            _require(inventory['files'], 'NO_SAVES', 'No saves were found in the declared preservation scope')
            new_parents = []
            parent = output.parent
            while not parent.exists():
                new_parents.append(parent)
                parent = parent.parent
            output.mkdir(parents=True, mode=0o700)
            try:
                for index, record in enumerate(inventory['files']):
                    _copy_checked(_safe(self.root, record['target']), output / f'files/{index}', record['sha256'])
                _sync(output / 'files')
                _sync(output)
                for created in (output, *new_parents):
                    _sync(created.parent)
                _require(self.save_inventory(port_id)['files'] == inventory['files'],
                         'CONFLICT', 'Saves changed while they were backed up')
                receipt = {'schema': 1, 'kind': 'port-save-backup', 'root': str(self.root),
                           'port_id': port_id, 'files': inventory['files'], 'complete': True,
                           'registry': inventory['registry'], 'device_paths_verified': False}
                _json_write(output / 'receipt.json', receipt)
                _sync(output)
            except BaseException:
                shutil.rmtree(output)
                raise
        return output

    def _save_backup(self, backup):
        backup = Path(backup).absolute()
        _require(not any(p.is_symlink() for p in (backup, *backup.parents)),
                 'UNSAFE_PATH', 'Select an external save backup without symlinks')
        backup = backup.resolve(strict=True)
        _require(not backup.is_relative_to(self.root), 'UNSAFE_PATH', 'Select a backup outside the card')
        with os.fdopen(_open_regular(_safe(backup, 'receipt.json')), 'rb') as stream:
            data = stream.read(8 * CHUNK + 1)
        _require(len(data) <= 8 * CHUNK, 'INVALID_BACKUP', 'Save manifest exceeds its limit')
        try:
            receipt = json.loads(data)
        except (ValueError, UnicodeError, RecursionError) as error:
            raise PortError('INVALID_BACKUP', 'Cannot read the save manifest') from error
        _require(isinstance(receipt, dict) and type(receipt.get('schema')) is int and receipt['schema'] == 1 and
                 receipt.get('kind') == 'port-save-backup' and receipt.get('complete') is True and
                 receipt.get('root') == str(self.root), 'INVALID_BACKUP', 'Save manifest does not match this card contract')
        profile = self._profile(receipt.get('port_id'))
        _require(receipt.get('registry') == profile.get('save_registry'), 'INVALID_BACKUP', 'Save registry changed; review the backup mapping')
        records = receipt.get('files')
        _require(isinstance(records, list) and 0 < len(records) <= MAX_FILES, 'INVALID_BACKUP', 'Invalid save file list')
        names = set()
        for index, record in enumerate(records):
            _require(isinstance(record, dict), 'INVALID_BACKUP', 'Invalid save record')
            relative, digest = record.get('target'), record.get('sha256')
            _safe(self.root, relative)
            _require(self._save_allowed(profile, relative) and relative.casefold() not in names,
                     'UNSAFE_PATH', 'Backup path is outside the save registry or duplicated')
            names.add(relative.casefold())
            _require(isinstance(digest, str) and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest),
                     'INVALID_BACKUP', 'Invalid save checksum')
            _require(type(record.get('size')) is int and 0 <= record['size'] <= MAX_OWNER_FILE,
                     'INVALID_BACKUP', 'Invalid save file size')
            _require(_fingerprint(_safe(backup, f'files/{index}')) == (digest, record.get('size')),
                     'INVALID_BACKUP', 'A saved file is missing or damaged')
        return backup, receipt

    def preview_save_restore(self, backup):
        folder, receipt = self._save_backup(backup)
        return {'backup': str(folder), 'port_id': receipt['port_id'], 'files': [
            {'target': r['target'], 'current': _fingerprint(_safe(self.root, r['target']))[0],
             'snapshot': r['sha256']} for r in receipt['files']],
                'preserve_unlisted_files': True}

    def restore_saves(self, backup, preview, *, confirm_idle=False, confirm_overwrite=False):
        _require(confirm_idle, 'BUSY', 'Stop the game and enter idle maintenance mode before restoring saves')
        _require(confirm_overwrite, 'CONFIRM_OVERWRITE', 'Review and confirm the exact save restore')
        with self._lock():
            folder, receipt = self._save_backup(backup)
            _require(preview == self.preview_save_restore(folder), 'CONFLICT', 'Saves changed after the restore preview')
            records = [{'target': r['target'], 'before': live['current'], 'after': r['sha256']}
                       for r, live in zip(receipt['files'], preview['files'])]
            return self._transaction(receipt['port_id'], 'save-restore', records,
                                     [folder / f'files/{index}' for index in range(len(records))])
