"""Independent regression: a promotion error must preserve the last good pair."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import update_catalog as updater

HTML = '''<h1 class="sppb-addon-title">Windows Test</h1>
<section><div><h3>English 64-bit</h3><br>文件名：en_test_x64.iso<br>SHA1：aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa</div>
<div><strong>HTTP</strong><span class="dl-link">https://example.com/en_test_x64.iso</span></div></section>'''
PRODUCT = 'windows-11/test'


class FakeFetcher:
    def load_robots(self):
        pass

    def fetch(self, url):
        if url == updater.SOURCE + '/' + PRODUCT:
            return HTML.replace('English 64-bit', 'English 64-bit updated')
        return '<a href="/' + PRODUCT + '">Product</a>'


class PromotionFailureTests(unittest.TestCase):
    def test_second_file_write_failure_restores_catalog_and_provenance(self):
        self.check_failure('catalog.json')

    def test_status_write_failure_does_not_advance_last_success(self):
        self.check_failure('update-status.json')

    def check_failure(self, failure_target):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            document = updater.parse_product(HTML, updater.SOURCE + '/' + PRODUCT)
            updater.atomic_json(source / 'docs' / PRODUCT / 'data.json', document)
            catalog, provenance = updater.build(source, 'https://example.com/repository')
            output = root / 'data'
            updater.atomic_json(output / 'catalog.json', catalog)
            updater.atomic_json(output / 'provenance.json', provenance)
            before = {name: (output / name).read_bytes() for name in ('catalog.json', 'provenance.json')}
            old_status = {'status': 'unchanged', 'checkedAt': '2026-10-24T19:00:00Z',
                          'updatedAt': '2026-10-23T19:00:00Z', 'catalogDigest': updater.digest(catalog)}
            updater.atomic_json(output / 'update-status.json', old_status)
            original = updater.atomic_json
            failed = False

            def fail_catalog(path, value):
                nonlocal failed
                if path == output / failure_target and not failed:
                    failed = True
                    raise OSError('injected promotion failure')
                return original(path, value)

            with patch.object(updater, 'atomic_json', side_effect=fail_catalog):
                with self.assertRaises(OSError):
                    updater.run(output, FakeFetcher(), '2026-10-25T19:00:00Z')
            for name, content in before.items():
                self.assertEqual((output / name).read_bytes(), content, name + ' changed after failed promotion')
            status = json.loads((output / 'update-status.json').read_text())
            self.assertEqual(status['status'], 'failed')
            for key in ('checkedAt', 'updatedAt', 'catalogDigest'):
                self.assertEqual(status[key], old_status[key], key + ' advanced on failed promotion')


if __name__ == '__main__':
    unittest.main()
