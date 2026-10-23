#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""One-time publication of fixed, independently verified original-only host bytes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

REPO = 'daniel1990000/CrossMix-OS-project'
SOURCE = 'ab644b93a463fe71d10cd32bb9f7fa113b30c771'
INVENTORY = 'b796a5e796e1de1cb180bf8769e4a45f34b551e418b389c70fd0750ba9e79eda'
RUN = 39893214010
RELEASE = 421412257
TAG = 'smartpro-host-0.1.0-dev14'
ARTIFACTS = [(12475702753, 'e7a4be34153ac6135c3920a7bfbf238ae52ecd368ef098c4fa7b14dab0feab4a'),
             (12475598120, '52bfefd8e040965c55fc3eec273ed018b0b855ba8c390cbad8b98a87a47104b0')]


def gh(*args):
    return subprocess.check_output(['gh', *args])


def api(path):
    return json.loads(gh('api', f'repos/{REPO}/{path}'))


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def tag_commit():
    refs = api('git/matching-refs/tags/' + TAG)
    exact = [item for item in refs if item['ref'] == 'refs/tags/' + TAG]
    require(len(exact) <= 1, 'Duplicate release tag')
    if not exact:
        return None
    item = exact[0]['object']
    for _ in range(4):
        if item['type'] == 'commit':
            return item['sha']
        require(item['type'] == 'tag', 'Unsupported tag object')
        item = api('git/tags/' + item['sha'])['object']
    raise ValueError('Excessive nested tags')


def main():
    run = api(f'actions/runs/{RUN}')
    require(run['status'] == 'completed' and run['conclusion'] == 'success' and
            run['head_sha'] == SOURCE and run['event'] == 'workflow_dispatch' and
            run['head_branch'] == 'build/spruce-psp-experience' and
            run['path'] == '.github/workflows/smartpro-offshoot.yml', 'Wrong certified workflow/run')
    release = api(f'releases/{RELEASE}')
    require(release['draft'] is True and release['prerelease'] is True and
            release['tag_name'] == TAG and release['target_commitish'] == SOURCE and
            release['assets'] == [], 'Require the empty original-only draft; never overwrite a release')
    with tempfile.TemporaryDirectory(prefix='verified-host-delivery-') as temporary:
        work = Path(temporary)
        archives = []
        for identity, expected in ARTIFACTS:
            meta = api(f'actions/artifacts/{identity}')
            require(meta['digest'] == 'sha256:' + expected and
                    meta['workflow_run']['id'] == RUN and not meta['expired'], 'Artifact identity differs')
            raw = gh('api', f'repos/{REPO}/actions/artifacts/{identity}/zip')
            require(digest(raw) == expected, 'Artifact download checksum differs')
            path = work / f'{identity}.zip'
            path.write_bytes(raw)
            archives.append(path)
        helper = Path(__file__).parents[1] / 'artifact-custody/verify-host-artifacts.py'
        spec = importlib.util.spec_from_file_location('verify_host_artifacts', helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        evidence = module.verify(archives[0], ARTIFACTS[0][1], SOURCE, INVENTORY)
        # The verifier has already bounded and checked every original CI ZIP member.
        with zipfile.ZipFile(archives[0]) as archive:
            archive.extractall(work / 'ci')
        with zipfile.ZipFile(archives[1]) as archive:
            require(len(archive.infolist()) == 1 and archive.infolist()[0].file_size <= 1024 * 1024,
                    'Unexpected provenance bundle inventory')
            bundle = work / 'host-preview-provenance.jsonl'
            bundle.write_bytes(archive.read(archive.infolist()[0]))
        files = sorted((work / 'ci/development').iterdir()) + [work / 'ci/certification.json']
        for path in files:
            gh('attestation', 'verify', str(path), '--bundle', str(bundle), '--repo', REPO,
               '--signer-workflow', f'{REPO}/.github/workflows/smartpro-offshoot.yml',
               '--source-ref', 'refs/heads/build/spruce-psp-experience', '--source-digest', SOURCE,
               '--deny-self-hosted-runners')
        files.append(bundle)
        expected = {path.name: digest(path.read_bytes()) for path in files}
        gh('release', 'upload', TAG, '--repo', REPO, *map(str, files))
        uploaded = api(f'releases/{RELEASE}')
        require(uploaded['draft'] is True and
                {item['name'] for item in uploaded['assets']} == set(expected), 'Uploaded inventory differs')
        readback = work / 'readback'
        readback.mkdir()
        gh('release', 'download', TAG, '--repo', REPO, '--pattern', '*', '--dir', str(readback))
        observed = {path.name: digest(path.read_bytes()) for path in readback.iterdir()}
        require(observed == expected, 'Fresh release asset bytes differ')
        existing_tag = tag_commit()
        if existing_tag is None:
            gh('api', '--method', 'POST', f'repos/{REPO}/git/refs',
               '-f', 'ref=refs/tags/' + TAG, '-f', 'sha=' + SOURCE)
        require(tag_commit() == SOURCE, 'Actual tag does not select certified source')
        # Publish only after the fixed CI identity, scope, provenance and actual uploaded bytes pass.
        gh('release', 'edit', TAG, '--repo', REPO, '--draft=false', '--latest=false')
        final = api(f'releases/{RELEASE}')
        require(final['draft'] is False and final['prerelease'] is True and
                final['tag_name'] == TAG and final['target_commitish'] == SOURCE,
                'Publication metadata differs')
        require(tag_commit() == SOURCE, 'Published tag identity differs')
        receipt = {'schema': 1, 'kind': 'verified-original-only-host-publication',
                   'source_commit': SOURCE, 'run_id': RUN, 'release_id': RELEASE,
                   'release_url': final['html_url'], 'tag': TAG,
                   'asset_sha256': expected, 'all_assets_freshly_read_back_before_publication': True,
                   'all_ten_host_subjects_provenance_verified': True,
                   'actual_tag_commit_before_and_after_publication': SOURCE,
                   'payload_files': evidence['payload_files'], 'source_inventory_sha256': INVENTORY,
                   'hardware_qualified': False, 'production_ed25519_trust_established': False}
        Path('host-delivery-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps({'published': final['html_url'], 'assets': len(expected)}))


if __name__ == '__main__':
    main()
