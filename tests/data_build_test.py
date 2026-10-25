"""Verify a catalog refresh reaches the browser's content-addressed assets."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CatalogAssetRefreshTests(unittest.TestCase):
    def test_changed_catalog_rotates_data_app_and_entry_but_no_change_is_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('scripts/build_assets.py', 'index.html', 'app.js', 'styles.css',
                         'lib/catalog.mjs', 'data/catalog.json'):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)

            def build(*args):
                return subprocess.run(['python3', 'scripts/build_assets.py', *args],
                                      cwd=root, check=True, capture_output=True)

            def entry():
                html = (root / 'index.html').read_text()
                app_name = re.search(r'src="\./(assets/app\.[a-f0-9]+\.js)"', html)[1]
                app = (root / app_name).read_text()
                data_name = re.search(r"new URL\('\./(catalog-data\.[a-f0-9]+\.json)'", app)[1]
                return html, app_name, data_name

            build()
            before = entry()
            catalog = json.loads((root / 'data/catalog.json').read_text())
            catalog['resources'][0]['title'] += ' updated upstream'
            (root / 'data/catalog.json').write_text(json.dumps(catalog))
            stale = subprocess.run(['python3', 'scripts/build_assets.py', '--check'],
                                   cwd=root, capture_output=True)
            self.assertNotEqual(stale.returncode, 0)
            build()
            after = entry()
            for old, new in zip(before, after):
                self.assertNotEqual(old, new)
            generated = json.loads((root / 'assets' / after[2]).read_text())
            self.assertEqual(generated['resources'], catalog['resources'])
            build('--check')
            build()
            self.assertEqual(entry(), after)


if __name__ == '__main__':
    unittest.main()
