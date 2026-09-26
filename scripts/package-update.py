"""Build a signed, configuration-free portable update from a completed edition."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlparse, quote
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path, help='Completed green edition folder')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--base-url', required=True, help='HTTPS directory for published ZIP files')
    parser.add_argument('--notes', default='')
    args = parser.parse_args()
    proto = Path(__file__).resolve().parents[1]
    version = json.loads((proto / 'src-tauri/tauri.conf.json').read_text(encoding='utf-8'))['version']
    trust = json.loads((proto / 'src-tauri/update-source.json').read_text(encoding='utf-8'))
    if not trust['pubkey'] or not trust['endpoint']:
        raise SystemExit('Configure the publisher public key and HTTPS endpoint, then rebuild before publishing.')
    if urlparse(args.base_url).scheme != 'https':
        raise SystemExit('Use an HTTPS download URL.')
    if not os.environ.get('TAURI_SIGNING_PRIVATE_KEY') and not os.environ.get('TAURI_SIGNING_PRIVATE_KEY_PATH'):
        raise SystemExit('Set TAURI_SIGNING_PRIVATE_KEY_PATH to your private signing key. Never distribute that key.')
    source = args.source.resolve()
    required = [source / 'ApprovalTool.exe', source / 'python/dist/ApprovalRunner/ApprovalRunner.exe']
    internal = source / 'python/dist/ApprovalRunner/_internal'
    if not all(p.is_file() for p in required) or not internal.is_dir():
        raise SystemExit('Source is not a complete portable edition.')
    args.output.mkdir(parents=True, exist_ok=True)
    archive = args.output.resolve() / f'ApprovalTool-{version}-windows-x86_64.zip'
    if archive.exists():
        raise SystemExit('This release file exists; use a new version or another output directory.')
    with ZipFile(archive, 'x', ZIP_DEFLATED) as out:
        out.writestr('release.json', json.dumps({'version': version}))
        for path in required + sorted(p for p in internal.rglob('*') if p.is_file()):
            if path.is_symlink() or not path.resolve().is_relative_to(source):
                raise SystemExit('Linked files are not allowed in updates.')
            out.write(path, path.relative_to(source).as_posix())
    subprocess.run(['node', str(proto / 'node_modules/@tauri-apps/cli/tauri.js'), 'signer', 'sign', str(archive)], check=True, cwd=proto)
    signature = archive.with_suffix(archive.suffix + '.sig').read_text(encoding='utf-8').strip()
    manifest = {'version': version, 'notes': args.notes, 'platforms': {'windows-x86_64': {
        'url': args.base_url.rstrip('/') + '/' + quote(archive.name), 'signature': signature}}}
    (args.output / 'latest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Upload ZIP first, then latest.json: {archive.parent}')


if __name__ == '__main__':
    main()
