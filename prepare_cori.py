"""Build a fresh Cori package from pinned upstream files; never deploy it."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import shutil
import stat
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def fetch(item, cache):
    name = item['filename']
    if Path(name).name != name or ':' in name:
        raise ValueError('Invalid locked download filename')
    target = cache / name
    if target.exists():
        if digest(target) != item['sha256']:
            raise ValueError('Cached file does not match lock: ' + name)
        return target
    if not item['url'].startswith('https://'):
        raise ValueError('Downloads require HTTPS')
    temp = cache / (name + '.' + uuid.uuid4().hex + '.part')
    with urllib.request.urlopen(item['url'], timeout=120) as response, temp.open('xb') as f:
        shutil.copyfileobj(response, f)
    if digest(temp) != item['sha256']:
        raise ValueError('Downloaded file does not match lock: ' + name)
    temp.rename(target)
    return target


def extract(archive, destination, wheel=False):
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError('Archive CRC failed')
        for info in z.infolist():
            name = PurePosixPath(info.filename.replace('\\', '/'))
            if name.is_absolute() or '..' in name.parts or any(':' in p for p in name.parts):
                raise ValueError('Unsafe archive member: ' + info.filename)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('Archive symlinks are not supported')
            parts = name.parts
            if wheel and parts and parts[0].endswith('.data'):
                if len(parts) < 3 or parts[1] not in ('purelib', 'platlib', 'data'):
                    raise ValueError('Unsupported wheel data layout: ' + info.filename)
                parts = parts[2:]
            if info.is_dir():
                continue
            target = destination.joinpath(*parts).resolve()
            if not target.is_relative_to(destination):
                raise ValueError('Archive escapes destination')
            data = z.read(info)
            if target.exists() and target.read_bytes() != data:
                raise ValueError('Conflicting wheel files: ' + str(target))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)


def build(output, cache, source=ROOT / 'Source'):
    output, cache, source = output.resolve(), cache.resolve(), source.resolve()
    if output.exists():
        raise ValueError('Output must be a new directory; existing packages are never overwritten')
    if cache == output or cache.is_relative_to(output) or output.is_relative_to(cache):
        raise ValueError('Cache and output must be separate directories')
    lock_path = source / 'cori-package-lock.json'
    lock = json.loads(lock_path.read_text(encoding='utf-8'))
    if lock['schema_version'] != 1:
        raise ValueError('Unknown package lock schema')
    cache.mkdir(parents=True, exist_ok=True)
    # Fetch and verify every upstream input before creating the package.
    downloads = [lock['python'], *lock['wheels'], *lock['voice']['files']]
    local = {i['filename']: fetch(i, cache) for i in downloads}
    output.mkdir(parents=True)
    extract(local[lock['python']['filename']], output / 'python')
    site = output / 'python/Lib/site-packages'
    for wheel in lock['wheels']:
        extract(local[wheel['filename']], site, wheel=True)
    (output / 'python/python312._pth').write_text('python312.zip\n.\nLib\\site-packages\n', encoding='utf-8')
    (output / 'voices').mkdir()
    for item in lock['voice']['files']:
        shutil.copy2(local[item['filename']], output / 'voices' / item['filename'])
    shutil.copy2(source / 'piper_worker.py', output / 'piper_worker.py')
    shutil.copy2(source / 'cori-package-README.txt', output / 'README.txt')
    shutil.copytree(source / 'cori-notices', output / 'licenses')
    files = {str(p.relative_to(output)): digest(p) for p in output.rglob('*') if p.is_file()}
    manifest = {
        'purpose': 'Maintainer-built Cori high package; public release review still required',
        'voice': 'Cori high', 'voice_repository': lock['voice']['repository'],
        'voice_revision': lock['voice']['revision'], 'voice_path': lock['voice']['path'],
        'python_source': lock['python']['url'], 'python_zip_sha256': lock['python']['sha256'],
        'dependencies': [{'Name': w['Name'], 'Version': w['Version']} for w in lock['wheels']],
        'cpu_threads': 2, 'lock_sha256': digest(lock_path), 'upstream_downloads': downloads,
        'files': files,
    }
    (output / 'package-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    if not all(digest(output / n) == h for n, h in files.items()):
        raise ValueError('Final package verification failed')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New package directory; never the installed package')
    parser.add_argument('--cache', type=Path, required=True, help='Separate reusable verified-download cache')
    args = parser.parse_args()
    result = build(args.output, args.cache)
    print(json.dumps({'output': str(args.output.resolve()), 'files_verified': len(result['files']),
                      'voice': result['voice'], 'deployment_changed': False}))


if __name__ == '__main__':
    main()
