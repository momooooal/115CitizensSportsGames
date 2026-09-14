#!/usr/bin/env python3
"""Make a portable offline preview with the exact same UI and data."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(destination):
    site = ROOT / 'site'
    page = (site / 'index.html').read_text(encoding='utf-8')
    page = page.replace('<html lang="zh-Hant">', '<html lang="zh-Hant" data-preview="true">')
    css = (site / 'styles.css').read_text(encoding='utf-8')
    page = page.replace('<link rel="stylesheet" href="./styles.css">', '<style>' + css + '</style>')
    scripts = []
    for name in ('data/snapshot.js', 'data/documents.js', 'app.js'):
        page = page.replace(f'<script src="./{name}" defer></script>', '')
        body = (site / name).read_text(encoding='utf-8').replace('</script', '<\\/script')
        scripts.append('<script>' + body + '</script>')
    # Inline scripts run after the complete document, preserving defer behavior.
    page = page.replace('</body>', '\n'.join(scripts) + '\n</body>')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(page, encoding='utf-8')
    print(f'Created {destination} ({destination.stat().st_size:,} bytes)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    build(parser.parse_args().output)
