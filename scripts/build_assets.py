#!/usr/bin/env python3
"""Deterministic, dependency-free asset fingerprinting. Run --check in CI."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

def fingerprint(label, extension, content):
    digest = hashlib.sha256(content).hexdigest()[:16]
    return f'{label}.{digest}.{extension}'

def build(check=False):
    outputs = {}
    def asset(label, ext, content):
        name = fingerprint(label, ext, content)
        outputs[ROOT / 'assets' / name] = content
        return name
    css = asset('styles', 'css', (ROOT / 'styles.css').read_bytes())
    lib = asset('catalog-lib', 'mjs', (ROOT / 'lib/catalog.mjs').read_bytes())
    catalog = json.loads((ROOT / 'data/catalog.json').read_text())
    # Relocate the audit pointer with the generated catalog, leaving authored data intact.
    if catalog.get('meta', {}).get('provenanceFile') == 'provenance.json':
        catalog['meta']['provenanceFile'] = '../data/provenance.json'
    data = asset('catalog-data', 'json', (json.dumps(catalog, ensure_ascii=False, indent=2) + '\n').encode())
    source = (ROOT / 'app.js').read_text()
    source, imports = re.subn(r"from '\./lib/catalog\.mjs(?:\?v=[^']+)?'", f"from './{lib}'", source)
    source, fetches = re.subn(r"fetch\('\./data/catalog\.json(?:\?v=[^']+)?'\)", f"fetch(new URL('./{data}', import.meta.url))", source)
    if imports != 1 or fetches != 1:
        raise RuntimeError('Expected exactly one catalog module import and data fetch in authored app.js')
    app = asset('app', 'js', source.encode())
    original = (ROOT / 'index.html').read_text()
    html, styles = re.subn(r'href="\./(?:styles\.css(?:\?v=[^\"]+)?|assets/styles\.[0-9a-f]+\.css)"', f'href="./assets/{css}"', original)
    html, scripts = re.subn(r'src="\./(?:app\.js(?:\?v=[^\"]+)?|assets/app\.[0-9a-f]+\.js)"', f'src="./assets/{app}"', html)
    if styles != 1 or scripts != 1:
        raise RuntimeError('Expected exactly one generated stylesheet and app entry in index.html')
    outputs[ROOT / 'index.html'] = html.encode()
    stale = [str(path.relative_to(ROOT)) for path, content in outputs.items() if not path.exists() or path.read_bytes() != content]
    if check:
        if stale:
            print('Stale/missing generated assets: ' + ', '.join(stale), file=sys.stderr)
            return 1
        print('Generated assets match authored sources (4 fingerprinted assets + HTML).')
        return 0
    (ROOT / 'assets').mkdir(exist_ok=True)
    for path, content in outputs.items():
        path.write_bytes(content)
    print('Built: ' + ', '.join(path.name for path in outputs))
    return 0

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    sys.exit(build(parser.parse_args().check))
