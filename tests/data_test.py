"""Run with: python -m unittest discover -s tests -p 'data*.py'"""
import importlib.util
import json
from datetime import date, datetime
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('import_catalog',ROOT/'scripts/import_catalog.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=json.loads((ROOT/'data/catalog.json').read_text())
        cls.provenance=json.loads((ROOT/'data/provenance.json').read_text())
        cls.regressions=module.build(ROOT/'tests/fixtures/catalog-regressions',
                                     'https://example.com/frozen-regression-source')[0]

    def test_counts_ids_and_families(self):
        c=self.catalog
        self.assertGreater(len(c['products']),0)
        self.assertGreater(len(c['resources']),0)
        self.assertEqual(c['meta']['productCount'],len(c['products']))
        self.assertEqual(c['meta']['schemaVersion'],1)
        self.assertEqual(c['meta'],self.provenance['meta'])
        self.assertEqual(c['meta']['sourceRowCount'],len(self.provenance['rows']))
        self.assertEqual(c['meta']['sourceDownloadOccurrences'],
                         sum(len(row['downloads']) for row in self.provenance['rows']))
        self.assertEqual(c['meta']['downloadCount'],
                         sum(len(r['downloads']) for r in c['resources']))
        datetime.fromisoformat(c['meta']['importedAt'].replace('Z','+00:00'))
        if c['meta'].get('sourceSnapshotDate') is not None:
            date.fromisoformat(c['meta']['sourceSnapshotDate'])
        self.assertEqual(c['meta']['resourceCount'],len(c['resources']))
        self.assertEqual(len({r['id'] for r in c['resources']}),len(c['resources']))
        expected_families={'Windows 11','Windows 10','Windows','Windows Server','Office','SQL Server'}
        self.assertTrue(expected_families.issubset({r['family'] for r in c['resources']}))
        products={p['id']:p for p in c['products']}
        self.assertEqual(len(products),len(c['products']))
        self.assertEqual(len({row['id'] for row in self.provenance['rows']}),len(self.provenance['rows']))
        for r in c['resources']:
            self.assertIn(r['productId'],products)
            self.assertEqual(r['family'],products[r['productId']]['family'])
            self.assertTrue(r['downloads'])
            self.assertTrue(r['provenance'])

    def test_every_source_url_preserved_without_duplicate_downloads(self):
        expected={d['download_url'].strip() for row in self.provenance['rows'] for d in row['downloads']}
        actual={d['url'] for r in self.catalog['resources'] for d in r['downloads']}
        self.assertEqual(expected,actual)
        for r in self.catalog['resources']:
            self.assertEqual(len(r['downloads']),len({d['url'] for d in r['downloads']}))

    def test_metadata_is_traceable_not_verified(self):
        rows={row['id']:row for row in self.provenance['rows']}
        for r in self.catalog['resources']:
            self.assertTrue(all(p['rowId'] in rows for p in r['provenance']))
            evidence=[rows[p['rowId']] for p in r['provenance']]
            evidenced_urls={d['download_url'].strip() for row in evidence for d in row['downloads']}
            self.assertTrue({d['url'] for d in r['downloads']}.issubset(evidenced_urls))
            self.assertTrue(all(row['path']==next(product['sourcePath'] for product in self.catalog['products']
                                                if product['id']==r['productId']) for row in evidence))
            if r['metadataStatus']=='source-reported':
                self.assertTrue(any(p['metadataApplied'] for p in r['provenance']))
            if r['sha1']:
                self.assertRegex(r['sha1'],r'^[0-9a-fA-F]{40}$')
                self.assertEqual(r['hashStatus'],'unverified')
            if r['metadataStatus']=='link-only':
                self.assertIsNone(r['sha1'])
                self.assertIsNone(r['publishedAt'])
                self.assertIsNone(r['size'])

    def test_office_locales_not_merged_by_generic_filename(self):
        for product in ('office-2021','office-2024'):
            rows=[r for r in self.regressions['resources'] if r['productId']==product]
            self.assertEqual(len(rows),9)
            self.assertEqual({r['language'] for r in rows},{'Simplified Chinese','Traditional Chinese','English'})
            self.assertTrue(all(r['publishedAt'] is None for r in rows))

    def test_filename_first_and_unknown(self):
        self.assertEqual(module.classify_arch('en_office_x86_x64.iso'),'x86 + x64')
        self.assertEqual(module.classify_arch('file.iso'),'Unknown')
        self.assertEqual(module.classify_language('mu_windows_language_pack.iso'),'Multilingual')
        self.assertEqual(module.classify_language('file.iso'),'Unknown')
        bad=[r for r in self.regressions['resources'] if r['productId']=='windows-7' and r['filename'] and 'enterprise' in r['filename'] and 'x64' in r['filename']]
        self.assertEqual(len(bad),1)
        self.assertIsNone(bad[0]['sha1'])
        self.assertEqual(bad[0]['architecture'],'x64')

    def test_server_2025_metadata_does_not_cross_locales(self):
        rows=[r for r in self.regressions['resources'] if r['productId']=='windows-server-2025']
        self.assertEqual(len(rows),3)
        self.assertEqual({r['language'] for r in rows},{'Simplified Chinese','Traditional Chinese','English'})
        for r in rows:
            self.assertIn({'English':'en-us','Traditional Chinese':'zh-tw','Simplified Chinese':'zh-cn'}[r['language']],r['filename'])
            self.assertEqual(r['architecture'],'x64')
            self.assertTrue(all(module.filename(d['url'])==r['filename'] for d in r['downloads']))

    def test_edge_case_language_architecture_and_malformed_urls(self):
        self.assertEqual(module.classify_language('zh-hans_windows_xp.iso'),'Simplified Chinese')
        self.assertEqual(module.classify_language('zh-hant_windows_xp.iso'),'Traditional Chinese')
        self.assertEqual(module.classify_arch('sql_x86_x64_ia64.iso'),'x86 + x64 + IA64')
        self.assertIsNone(module.filename('https://[invalid'))
        self.assertIsNone(module.filename('unknown:opaque'))

    def test_same_basename_different_language_query_stays_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=root/'docs/applications/test/data.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'title':'Office Test','versions':[{'attributes':[], 'downloads':[
                {'download_url':'https://example.com/setup.exe?language=zh-cn'},
                {'download_url':'https://example.com/setup.exe?language=en-us'}]}]}))
            resources=module.build(root,'https://example.com')[0]['resources']
            self.assertEqual(len(resources),2)
            self.assertEqual({r['language'] for r in resources},{'Simplified Chinese','English'})

    def test_windows_11_64arm_filenames_are_arm64(self):
        arm_rows=[r for r in self.regressions['resources'] if r['filename'] and '64arm' in r['filename'].lower()]
        self.assertGreaterEqual(len(arm_rows),2)
        self.assertTrue(any('21H2' in r['filename'] for r in arm_rows))
        self.assertTrue(any('22H2' in r['filename'] for r in arm_rows))
        for r in arm_rows:
            self.assertEqual(module.classify_arch(r['filename']),'ARM64')
            self.assertEqual(r['architecture'],'ARM64')

    def test_grouped_metadata_not_smeared_and_deterministic(self):
        a='ed2k://|file|cn_one_x86.iso|1|AAAA|/'
        b='ed2k://|file|en_two_x64.iso|2|BBBB|/'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=root/'docs/windows-11/test/data.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'title':'Windows 11 Test','url':'https://example.com', 'versions':[
                {'version_text':'Chinese 32-bit','attributes':['文件名：cn_one_x86.iso','SHA1：'+'a'*40,'发布时间：2024-1-2'],
                 'downloads':[{'download_url':a},{'download_url':a},{'download_url':b}]}]}))
            first=module.build(root,'https://example.com')
            self.assertEqual(first,module.build(root,'https://example.com'))
            self.assertIsNone(first[0]['meta']['sourceSnapshotDate'])
            dated=module.build(root,'https://example.com',source_snapshot_date='2025-10-09')
            self.assertEqual(dated[0]['meta']['sourceSnapshotDate'],'2025-10-09')
            result=first[0]['resources']
            self.assertEqual(len(result),2)
            second=next(r for r in result if r['filename']=='en_two_x64.iso')
            self.assertEqual(second['language'],'English')
            self.assertEqual(second['architecture'],'x64')
            self.assertIsNone(second['sha1'])
            self.assertIsNone(second['publishedAt'])
            self.assertEqual(next(r for r in result if r['filename']=='cn_one_x86.iso')['publishedAt'],'2024-01-02')

if __name__=='__main__': unittest.main()
