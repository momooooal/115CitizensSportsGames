#!/usr/bin/env python3
"""Publish a complete update, or retain the previous data with a visible warning."""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sync_data import ROOT, validate_snapshot


def update(output, cache_dir, full=False, offline=False):
    output.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='sport115-update-') as temporary:
            stage = Path(temporary)
            for path in output.glob('*'):
                if path.is_file():
                    shutil.copy2(path, stage / path.name)
            base = [sys.executable, str(ROOT / 'scripts/sync_data.py'),
                    '--output', str(stage), '--cache-dir', str(cache_dir)]
            subprocess.run(base + (['--full'] if full else []) +
                           (['--offline'] if offline else []), check=True)
            if not offline:
                subprocess.run([sys.executable, str(ROOT / 'scripts/sync_documents.py'),
                                '--output', str(stage)] + (['--force'] if full else []), check=True)
            # Reuse this run's HTML cache to join the newly extracted PDFs.
            subprocess.run(base + ['--offline'], check=True)
            data = json.loads((stage / 'snapshot.json').read_text(encoding='utf-8'))
            validate_snapshot(data)
            docs = json.loads((stage / 'documents.json').read_text(encoding='utf-8'))
            if {d['url'] for d in docs['documents']} != {d['url'] for d in data['documents']}:
                raise ValueError('Schedule attachment coverage is incomplete')
            for name in ('snapshot.json', 'snapshot.js', 'documents.json', 'documents.js', 'sync-status.json'):
                temporary_path = output / (name + '.tmp')
                shutil.copyfile(stage / name, temporary_path)
                temporary_path.replace(output / name)
        return 0
    except Exception as exc:
        print(f'Update failed; previous data retained: {exc}', file=sys.stderr)
        old = output / 'snapshot.json'
        checked = json.loads(old.read_text(encoding='utf-8'))['meta']['checked_at'] if old.exists() else None
        status = {'status': 'error', 'attempted_at': datetime.now(timezone.utc).isoformat(),
                  'last_success_at': checked,
                  'message': '本次同步未完成，保留上次成功資料；請由官方依據確認最新結果。'}
        (output / 'sync-status.json').write_text(json.dumps(status, ensure_ascii=False), encoding='utf-8')
        return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'site/data')
    parser.add_argument('--cache-dir', type=Path, default=ROOT / '.cache')
    parser.add_argument('--full', action='store_true', help='Refresh the roster and every PDF too')
    parser.add_argument('--offline', action='store_true', help='Rebuild from existing local HTML and PDF text')
    args = parser.parse_args()
    raise SystemExit(update(args.output, args.cache_dir, args.full, args.offline))
