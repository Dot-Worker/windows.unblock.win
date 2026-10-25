"""Offline live-update contracts. No network or downloaded executables."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import update_catalog as updater
from import_catalog import build

HTML = (ROOT / 'tests/fixtures/live-product.html').read_text()
PATH = 'windows-11/test'
URL = updater.SOURCE + '/' + PATH


class FakeFetcher:
    def __init__(self, pages=None):
        self.pages = pages or {PATH: HTML}
        self.calls = []

    def load_robots(self):
        self.calls.append('robots')

    def fetch(self, url):
        self.calls.append(url)
        path = url.removeprefix(updater.SOURCE).strip('/')
        if path in ('', *updater.CATEGORIES):
            return ''.join(f'<a href="/{key}">Product</a>' for key in self.pages)
        return self.pages[path]


def seed(directory):
    source = directory / 'source'
    updater.atomic_json(source / 'docs' / PATH / 'data.json', updater.parse_product(HTML, URL))
    catalog, provenance = build(source, 'https://github.com/example/reference', imported_at='2026-10-01T00:00:00Z')
    # Existing old source data differs; first live run must perform a real update.
    catalog['products'][0]['intro'] = 'Earlier source text'
    output = directory / 'data'
    updater.atomic_json(output / 'catalog.json', catalog)
    updater.atomic_json(output / 'provenance.json', provenance)
    return output


class UpdateTests(unittest.TestCase):
    def test_parse_leaf_sections_only_and_entity_decoding(self):
        data = updater.parse_product(HTML, URL)
        self.assertEqual(len(data['versions']), 2)
        self.assertEqual(sum(len(r['downloads']) for r in data['versions']), 4)
        self.assertIn('&dn=', data['versions'][0]['downloads'][1]['download_url'])
        self.assertEqual(data['versions'][0]['attributes'][0], '文件名：cn_test_x64.iso')
        compact = updater.parse_product(HTML.replace('</h3>\n', '</h3>'), URL)
        self.assertEqual(compact['versions'][0]['attributes'][0], '文件名：cn_test_x64.iso')

    def test_discovery_new_products_and_origin_boundary(self):
        html = '<a href="/windows-11/new-2027">new</a><a href="https://evil.test/windows-11/evil">bad</a><a href="/windows-11/../../secret">bad</a><a href="/windows-11/new-2027?bad=1">bad</a>'
        self.assertEqual(updater.discover(html), {'windows-11/new-2027'})

    def test_grouped_metadata_not_borrowed(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            updater.atomic_json(source / 'docs' / PATH / 'data.json', updater.parse_product(HTML, URL))
            catalog, _ = build(source, updater.SOURCE)
            third = next(r for r in catalog['resources'] if r['filename'] == 'zh-tw_third_arm64.iso')
            self.assertIsNone(third['sha1'])
            self.assertEqual(third['architecture'], 'ARM64')
            self.assertEqual(third['language'], 'Traditional Chinese')
            self.assertEqual(len(catalog['resources']), 3)

    def test_changed_then_unchanged_preserves_catalog_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            output = seed(Path(temp))
            fetcher = FakeFetcher()
            first = updater.run(output, fetcher, '2026-10-25T01:00:00Z')
            self.assertEqual(first['status'], 'updated')
            self.assertEqual(len(fetcher.calls), 9)  # robots, home, six categories, product
            before = [(output / file).read_bytes() for file in ('catalog.json', 'provenance.json')]
            second = updater.run(output, FakeFetcher(), '2026-10-25T02:00:00Z')
            self.assertEqual(second['status'], 'unchanged')
            self.assertEqual(first['catalogDigest'], second['catalogDigest'])
            self.assertEqual(first['updatedAt'], second['updatedAt'])
            self.assertNotEqual(first['checkedAt'], second['checkedAt'])
            self.assertEqual(before, [(output / file).read_bytes() for file in ('catalog.json', 'provenance.json')])

    def test_identical_snapshot_migrates_once_without_fake_content_change(self):
        with tempfile.TemporaryDirectory() as temp:
            output = seed(Path(temp))
            catalog = json.loads((output / 'catalog.json').read_text())
            catalog['products'][0]['intro'] = ''
            updater.atomic_json(output / 'catalog.json', catalog)
            first = updater.run(output, FakeFetcher(), '2026-10-25T01:00:00Z')
            self.assertTrue(first['sourceMigration'])
            self.assertFalse(first['contentChanged'])
            self.assertEqual(json.loads((output / 'catalog.json').read_text())['meta']['sourceMode'], 'live-html')
            before = [(output / name).read_bytes() for name in ('catalog.json', 'provenance.json')]
            second = updater.run(output, FakeFetcher(), '2026-10-25T02:00:00Z')
            self.assertEqual(second['status'], 'unchanged')
            self.assertEqual(before, [(output / name).read_bytes() for name in ('catalog.json', 'provenance.json')])

    def test_completion_timestamp_is_distinct_from_attempt_start(self):
        with tempfile.TemporaryDirectory() as temp:
            output = seed(Path(temp))
            result = updater.run(output, FakeFetcher(), '2026-10-25T01:00:00Z', completed_at=lambda: '2026-10-25T01:04:00Z')
            self.assertEqual(result['attemptedAt'], '2026-10-25T01:00:00Z')
            self.assertEqual(result['checkedAt'], '2026-10-25T01:04:00Z')
            self.assertEqual(result['updatedAt'], result['checkedAt'])

    def test_new_product_is_imported(self):
        with tempfile.TemporaryDirectory() as temp:
            output = seed(Path(temp))
            status = updater.run(output, FakeFetcher({PATH: HTML, 'windows-11/new-2027': HTML.replace('Windows Test', 'New Product')}), '2026-10-25T01:00:00Z')
            self.assertEqual(status['counts']['products'], 2)
            self.assertEqual(status['status'], 'updated')

    def test_failed_page_keeps_last_good_and_last_success_timestamp(self):
        with tempfile.TemporaryDirectory() as temp:
            output = seed(Path(temp))
            good = updater.run(output, FakeFetcher(), '2026-10-25T01:00:00Z')
            before = [(output / file).read_bytes() for file in ('catalog.json', 'provenance.json')]
            with self.assertRaises(updater.UpdateError):
                updater.run(output, FakeFetcher({PATH: '<h1>Challenge</h1>'}), '2026-10-25T02:00:00Z')
            status = json.loads((output / 'update-status.json').read_text())
            self.assertEqual(status['status'], 'failed')
            self.assertEqual(status['checkedAt'], good['checkedAt'])
            self.assertEqual(before, [(output / file).read_bytes() for file in ('catalog.json', 'provenance.json')])

    def test_missing_product_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            output = seed(Path(temp))
            with self.assertRaisesRegex(updater.UpdateError, 'Discovery missing'):
                updater.run(output, FakeFetcher({'windows-11/other': HTML}), '2026-10-25T02:00:00Z')

    def test_ambiguous_and_unsafe_download_sections_refused(self):
        for bad in (HTML.replace('</h3>', '</h3><h3>Ambiguous</h3>', 1), HTML.replace('https://example.com/en_second_x86.iso', 'javascript:alert(1)'), '<h1 class="sppb-addon-title">Empty</h1>'):
            with self.assertRaises(updater.UpdateError):
                updater.parse_product(bad, URL)

    def test_link_only_section_never_borrows_metadata(self):
        html = HTML.replace('<h3>Grouped downloads</h3>', '')
        parsed = updater.parse_product(html, URL)
        self.assertEqual(parsed['versions'][1]['attributes'], [])
        self.assertEqual(len(parsed['versions'][1]['downloads']), 2)

    def test_redirect_rejected_before_follow(self):
        from urllib.request import Request
        handler = updater.SourceRedirectHandler()
        for target in ('https://evil.example/resource', 'http://www.imsdn.cn/resource'):
            with self.assertRaises(updater.UpdateError):
                handler.redirect_request(Request(URL), None, 302, 'Found', {}, target)

    def test_network_failure_keeps_previous_data(self):
        class Broken(FakeFetcher):
            def fetch(self, url):
                raise TimeoutError('source timeout')
        with tempfile.TemporaryDirectory() as temp:
            output = seed(Path(temp))
            before = (output / 'catalog.json').read_bytes()
            with self.assertRaises(TimeoutError):
                updater.run(output, Broken(), '2026-10-25T02:00:00Z')
            self.assertEqual(before, (output / 'catalog.json').read_bytes())
            self.assertEqual(json.loads((output / 'update-status.json').read_text())['status'], 'failed')

    def test_lost_alternate_link_refused_even_if_resource_count_same(self):
        with tempfile.TemporaryDirectory() as temp:
            output = seed(Path(temp))
            old = json.loads((output / 'catalog.json').read_text())
            candidate = json.loads(json.dumps(old))
            resource = next(r for r in candidate['resources'] if len(r['downloads']) > 1)
            resource['downloads'].pop()
            with self.assertRaisesRegex(updater.UpdateError, 'Suspicious download loss'):
                updater.validate(candidate, old)

    def test_large_per_product_loss_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            output = seed(Path(temp))
            old = json.loads((output / 'catalog.json').read_text())
            candidate = json.loads(json.dumps(old))
            candidate['resources'] = candidate['resources'][:1]
            with self.assertRaisesRegex(updater.UpdateError, 'Suspicious resource loss'):
                updater.validate(candidate, old)


if __name__ == '__main__':
    unittest.main()
