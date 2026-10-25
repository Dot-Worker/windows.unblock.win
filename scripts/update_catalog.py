#!/usr/bin/env python3
"""Fetch live public HTML, independently parse it, validate, then atomically import.
Only HTML/robots are fetched: download URLs are data, never network targets.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
from urllib.robotparser import RobotFileParser

from import_catalog import build, clean

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://www.imsdn.cn'
CATEGORIES = ('applications', 'operating-systems', 'servers', 'windows-10', 'windows-11', 'windows-server')
USER_AGENT = 'WindowsResourceCatalog/1.0 (+https://github.com/Dot-Worker/windows.unblock.win)'
VOID = set('area base br col embed hr img input link meta param source track wbr'.split())


class UpdateError(ValueError):
    pass


class Node:
    def __init__(self, tag='', attrs=(), parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def text(self):
        return ''.join(('\n' if c.tag == 'br' else c.text()) if isinstance(c, Node) else c for c in self.children)

    def has_class(self, value):
        return value in self.attrs.get('class', '').split()


class DOM(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.current = self.root
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent is not None:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def product_path(url):
    parts = urlsplit(url)
    path = parts.path.strip('/')
    if parts.scheme != 'https' or parts.netloc != urlsplit(SOURCE).netloc or parts.query:
        return None
    if re.fullmatch(r'(?:' + '|'.join(CATEGORIES) + r')/[a-z0-9][a-z0-9-]*', path):
        return path
    return None


def discover(html, page_url=SOURCE + '/'):
    return {p for node in DOM(html).root.walk() if node.tag == 'a'
            if (p := product_path(urljoin(page_url, node.attrs.get('href', ''))))}


def parse_product(html, url):
    root = DOM(html).root
    headings = [n for n in root.walk() if n.tag == 'h1' and n.has_class('sppb-addon-title')]
    if len(headings) != 1 or not clean(headings[0].text()):
        raise UpdateError(f'Missing/ambiguous product title: {url}')
    title = clean(headings[0].text())
    intro = next((clean(n.text()) for n in headings[0].parent.walk() if n.has_class('sppb-addon-content')), '')
    # A download belongs to its nearest section, never the enclosing page section.
    grouped = {}
    all_links = [n for n in root.walk() if n.has_class('dl-link')]
    for link in all_links:
        section = link.parent
        while section and section.tag != 'section':
            section = section.parent
        if section is None:
            raise UpdateError(f'Download outside a section: {url}')
        grouped.setdefault(section, []).append(link)
    rows = []
    for section, nodes in grouped.items():
        titles = [n for n in section.walk() if n.tag == 'h3']
        if len(titles) > 1:
            raise UpdateError(f'Ambiguous download section ({len(titles)} headings): {url}')
        heading = titles[0] if titles else None
        # Metadata comes only from the heading's own block, not adjacent downloads.
        attributes = []
        metadata_block = Node()
        if heading:
            siblings = heading.parent.children
            metadata_block.children = siblings[siblings.index(heading) + 1:]
        for line in metadata_block.text().splitlines():
            line = clean(line)
            if re.match(r'^(?:文件名|文件|文件大小|大小|发布时间|SHA-?1|MD5)\s*[:：]', line, re.I):
                attributes.append(line)
        downloads = []
        for node in nodes:
            value = node.text().strip()
            if not value.startswith(('https://', 'http://', 'ed2k://', 'magnet:?')) or any(c in value for c in '\r\n\x00'):
                raise UpdateError(f'Unsupported/malformed download data: {url}')
            label = next((clean(n.text()) for n in node.parent.walk() if n.tag == 'strong'), '下载')
            downloads.append({'download_url': value, 'download_type': label})
        rows.append({'version_text': clean(heading.text()) if heading else title + ' — source links', 'attributes': attributes, 'downloads': downloads})
    if not rows:
        raise UpdateError(f'No downloads parsed: {url}')
    return {'title': title, 'intro_text': intro, 'url': url, 'versions': rows}


class SourceRedirectHandler(HTTPRedirectHandler):
    def __init__(self, robots=None):
        super().__init__()
        self.robots = robots

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if target.scheme != 'https' or target.netloc != urlsplit(SOURCE).netloc:
            raise UpdateError('Refusing off-origin or insecure redirect before following it')
        if self.robots is not None and not self.robots.can_fetch(USER_AGENT, newurl):
            raise UpdateError('robots.txt disallows redirect target')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Fetcher:
    def __init__(self, delay=0.5):
        self.delay = delay
        self.robots = None

    def fetch(self, url):
        parts = urlsplit(url)
        if parts.scheme != 'https' or parts.netloc != urlsplit(SOURCE).netloc:
            raise UpdateError('Fetch target outside configured public source')
        if self.robots is not None and not self.robots.can_fetch(USER_AGENT, url):
            raise UpdateError(f'robots.txt disallows {url}')
        for attempt in range(3):
            try:
                time.sleep(self.delay)
                request = Request(url, headers={'User-Agent': USER_AGENT, 'Cache-Control': 'no-cache', 'Accept': 'text/html,text/plain'})
                with build_opener(SourceRedirectHandler(self.robots)).open(request, timeout=40) as response:
                    if urlsplit(response.url).netloc != parts.netloc:
                        raise UpdateError('Unexpected cross-origin redirect')
                    if response.headers.get_content_type() not in ('text/html', 'text/plain'):
                        raise UpdateError('Unexpected non-HTML response')
                    body = response.read(5_000_001)
                    if len(body) > 5_000_000:
                        raise UpdateError('HTML response too large')
                    return body.decode(response.headers.get_content_charset() or 'utf-8', errors='strict')
            except UpdateError:
                raise
            except Exception as exc:
                if attempt == 2:
                    raise UpdateError(f'Fetch failed for {url}: {type(exc).__name__}: {exc}') from exc
                time.sleep(2 ** attempt)

    def load_robots(self):
        robots = RobotFileParser()
        robots.parse(self.fetch(SOURCE + '/robots.txt').splitlines())
        self.robots = robots


def digest(catalog):
    # Fetch timestamps, formatting and provenance metadata do not create content changes.
    payload = {key: catalog[key] for key in ('products', 'resources')}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def validate(catalog, previous):
    products, resources = catalog['products'], catalog['resources']
    if not products or not resources:
        raise UpdateError('Empty catalog')
    ids = [p['id'] for p in products]
    if len(ids) != len(set(ids)):
        raise UpdateError('Duplicate product IDs')
    if len({r['id'] for r in resources}) != len(resources):
        raise UpdateError('Duplicate resource IDs')
    if any(r['productId'] not in ids or not r['downloads'] for r in resources):
        raise UpdateError('Orphan/empty resource')
    previous_ids = {p['id'] for p in previous['products']}
    if previous_ids - set(ids):
        raise UpdateError('Missing existing products: ' + ', '.join(sorted(previous_ids - set(ids))))
    before = Counter(r['productId'] for r in previous['resources'])
    after = Counter(r['productId'] for r in resources)
    for product, count in before.items():
        if after[product] < count:
            raise UpdateError(f'Suspicious resource loss: {product}: {count} -> {after[product]}')
    before_links = Counter()
    after_links = Counter()
    for resource in previous['resources']:
        before_links[resource['productId']] += len(resource['downloads'])
    for resource in resources:
        after_links[resource['productId']] += len(resource['downloads'])
    for product, count in before_links.items():
        if after_links[product] < count:
            raise UpdateError(f'Suspicious download loss: {product}: {count} -> {after_links[product]}')
    for key in ('resourceCount', 'downloadCount', 'productCount'):
        expected = {'resourceCount':len(resources), 'productCount':len(products), 'downloadCount':sum(len(r['downloads']) for r in resources)}[key]
        if catalog['meta'][key] != expected:
            raise UpdateError(f'Inconsistent {key}')


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def run(output, fetcher, now, run_url='', completed_at=None):
    original = {name: (output / name).read_bytes() for name in ('catalog.json', 'provenance.json')}
    previous = json.loads(original['catalog.json'])
    status_path = output / 'update-status.json'
    old_status = json.loads(status_path.read_text()) if status_path.exists() else {}
    status = {**old_status, 'schemaVersion':1, 'sourceUrl':SOURCE, 'attemptedAt':now, 'workflowRunUrl':run_url}
    try:
        fetcher.load_robots()
        paths = discover(fetcher.fetch(SOURCE + '/'))
        for category in CATEGORIES:
            paths.update(discover(fetcher.fetch(SOURCE + '/' + category)))
        expected = {p['sourcePath'].removeprefix('docs/').removesuffix('/data.json') for p in previous['products']}
        if not paths or expected - paths:
            raise UpdateError('Discovery missing existing products: ' + ', '.join(sorted(expected - paths)))
        with tempfile.TemporaryDirectory(prefix='catalog-live-') as temp:
            source = Path(temp)
            for index, path in enumerate(sorted(paths), 1):
                print(f'Fetching product {index}/{len(paths)}: {path}', file=sys.stderr, flush=True)
                document = parse_product(fetcher.fetch(SOURCE + '/' + path), SOURCE + '/' + path)
                atomic_json(source / 'docs' / path / 'data.json', document)
            catalog, provenance = build(source, previous['meta'].get('sourceRepository'), imported_at=now)
        validate(catalog, previous)
        content_digest = digest(catalog)
        content_changed = content_digest != digest(previous)
        migration = previous['meta'].get('sourceMode') != 'live-html'
        changed = content_changed or migration
        if changed:
            catalog['meta'].update(sourceMode='live-html', sourceSite=SOURCE, sourceContentDigest=content_digest,
                notice='Live third-party HTML catalog. Links, dates, sizes and hashes are source-reported, not independently verified. Availability and authenticity are not guaranteed.')
            provenance['meta'] = catalog['meta'].copy()
            # Every fetch, parse and safety check completes before touching published data.
            atomic_json(output / 'provenance.json', provenance)
            atomic_json(output / 'catalog.json', catalog)
        checked_at = completed_at() if completed_at else now
        status.update(status='updated' if changed else 'unchanged', checkedAt=checked_at,
                      updatedAt=checked_at if changed else (old_status.get('updatedAt') or previous['meta'].get('importedAt')),
                      catalogDigest=content_digest, contentChanged=content_changed, sourceMigration=migration, counts={'products':len(catalog['products']), 'resources':len(catalog['resources']), 'downloads':catalog['meta']['downloadCount']})
        status.pop('error', None)
        atomic_json(status_path, status)
        return status
    except Exception as exc:
        # Roll back BOTH published documents if promotion or status writing failed.
        # Validation/network errors never touch these files.
        for name, old_bytes in original.items():
            path = output / name
            if path.read_bytes() != old_bytes:
                rollback = path.with_suffix('.rollback')
                rollback.write_bytes(old_bytes)
                rollback.replace(path)
        status = {**old_status, 'schemaVersion':1, 'sourceUrl':SOURCE, 'attemptedAt':now,
                  'workflowRunUrl':run_url, 'status':'failed', 'error':clean(str(exc))[:1000],
                  'contentChanged':False, 'sourceMigration':False}
        atomic_json(status_path, status)
        raise


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--run-url', default='')
    args = parser.parse_args()
    now = utc_now()
    try:
        print(json.dumps(run(args.output_dir, Fetcher(), now, args.run_url, completed_at=utc_now), ensure_ascii=False))
    except Exception as exc:
        print(f'Update refused; previous catalog preserved: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
