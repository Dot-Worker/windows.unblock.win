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
    status_path = ROOT / 'data/update-status.json'
    status_content = status_path.read_bytes() if status_path.exists() else b'{"schemaVersion":1,"status":"not-run","attemptedAt":null,"checkedAt":null,"updatedAt":null}\n'
    status = asset('update-status', 'json', status_content)
    source = (ROOT / 'app.js').read_text()
    source, imports = re.subn(r"from '\./lib/catalog\.mjs(?:\?v=[^']+)?'", f"from './{lib}'", source)
    source, fetches = re.subn(r"fetch\('\./data/catalog\.json(?:\?v=[^']+)?'\)", f"fetch(new URL('./{data}', import.meta.url))", source)
    source, status_fetches = re.subn(r"fetch\('\./data/update-status\.json'\)", f"fetch(new URL('./{status}', import.meta.url))", source)
    if imports != 1 or fetches != 1 or status_fetches != 1:
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
        print('Generated assets match authored sources (5 fingerprinted assets + HTML).')
        return 0
    # Keep complete current + previous HTML dependency graphs, never per-label files.
    # Repeated identical builds do not displace the previous release.
    asset_dir = ROOT / 'assets'
    asset_dir.mkdir(exist_ok=True)
    graph = sorted(path.name for path in outputs if path.parent == asset_dir)
    manifest_path = asset_dir / 'releases.json'
    try:
        history = json.loads(manifest_path.read_text())
        if not isinstance(history, list) or not all(isinstance(g, list) and all(isinstance(n, str) for n in g) for g in history):
            history = []
    except (OSError, ValueError):
        history = []
    if not history:
        # Bootstrap from the pre-build HTML so a deployment's cached entry still works.
        prior = set(re.findall(r'assets/([\w.-]+\.(?:css|js))', original))
        for name in list(prior):
            path = asset_dir / name
            if name.endswith('.js') and path.is_file():
                prior.update(re.findall(r"\./([\w.-]+\.(?:mjs|json))", path.read_text()))
        if prior:
            history = [sorted(prior)]
    history = [graph] + [g for g in history if g != graph][:1]

    for path, content in outputs.items():
        path.write_bytes(content)
    manifest_path.write_text(json.dumps(history, indent=2) + '\n')
    keep = {name for release in history for name in release}
    for path in asset_dir.iterdir():
        if re.fullmatch(r'(?:styles|catalog-lib|catalog-data|update-status|app)\.[0-9a-f]{16}\.(?:css|mjs|json|js)', path.name) and path.name not in keep:
            path.unlink()
    print('Built: ' + ', '.join(path.name for path in outputs))
    return 0

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--prune', action='store_true', help='Explicitly request the current + previous graph retention used by every build')
    sys.exit(build(parser.parse_args().check))
