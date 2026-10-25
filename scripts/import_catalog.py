#!/usr/bin/env python3
"""Offline, deterministic import of an explicitly supplied upstream JSON snapshot.
No requests, scraper execution, binary downloads, or authenticity validation.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit, parse_qs


def clean(value):
    return ' '.join(str(value or '').split())


def attrs(row):
    result = {}
    for value in row.get('attributes', []):
        parts = re.split(r'[：:]', value, maxsplit=1)
        if len(parts) == 2:
            result[clean(parts[0])] = clean(parts[1])
    return result


def split_url(url):
    try:
        return urlsplit(url)
    except ValueError:
        return urlsplit('')


def filename(url):
    if url.lower().startswith('ed2k://|file|'):
        return unquote(url.split('|')[2])
    if url.lower().startswith('magnet:'):
        return parse_qs(split_url(url).query).get('dn', [None])[0]
    leaf = unquote(split_url(url).path.rsplit('/', 1)[-1])
    match = re.match(r'(.+?\.(?:iso|img|exe|zip|msi|cab))(?:_[a-f0-9-]+)?$', leaf, re.I)
    return match.group(1) if match else None


def classify_language(text):
    text = text.lower()
    if re.search(r'(?:^|[/_?=&.-])(?:zh-cn|zh-hans|cn|chs)(?:[/_.&-]|$)|chnsimp|简体', text):
        return 'Simplified Chinese'
    if re.search(r'(?:^|[/_?=&.-])(?:zh-tw|zh-hant|tw|ct|cht)(?:[/_.&-]|$)|chntrad|繁体', text):
        return 'Traditional Chinese'
    if re.search(r'(?:^|[/_?=&.-])(?:en-us|en|enu)(?:[/_.&-]|$)|english|英文', text):
        return 'English'
    if re.search(r'(?:^|_)mu_|multilanguage|multi.language', text):
        return 'Multilingual'
    return 'Unknown'


def classify_arch(text):
    text = text.lower()
    if re.search(r'arm64|64arm|64位arm', text):
        return 'ARM64'
    x64 = bool(re.search(r'x64|amd64|64bit|64位', text))
    x86 = bool(re.search(r'x86|(?:^|_)w32(?:_|$)|32bit|32位|32/64', text))
    if 'ia64' in text:
        return 'x86 + x64 + IA64' if x64 and x86 else 'IA64' if not x64 and not x86 else 'Unknown'
    if x64 and x86:
        return 'x86 + x64'
    return 'x64' if x64 else 'x86' if x86 else 'Unknown'


def family(path):
    section = path.parts[-3]
    return {'windows-11':'Windows 11', 'windows-10':'Windows 10', 'windows-server':'Windows Server',
            'applications':'Office','servers':'SQL Server'}.get(section, 'Windows')


def normalized_date(value):
    if not value:
        return None
    from datetime import date
    try:
        return date(*map(int, value.split('-'))).isoformat()
    except (ValueError, TypeError):
        return None


def build(source, repository, revision=None, imported_at='2026-10-25T00:00:00Z', source_snapshot_date=None):
    products, resources, source_rows = [], [], []
    raw_links = 0
    for path in sorted(source.glob('docs/**/data.json')):
        document = json.loads(path.read_text(encoding='utf-8'))
        product_id = path.parent.name
        product = {'id':product_id,'title':clean(document['title']), 'family':family(path),
                   'intro':document.get('intro_text',''), 'sourceUrl':document.get('url'),
                   'sourcePath':str(path.relative_to(source))}
        products.append(product)
        rows = document.get('versions', [])
        # Exact URL evidence is preferred over broad grouped headings.
        by_url = {}
        for index, row in enumerate(rows):
            a = attrs(row)
            declared = a.get('文件名', a.get('文件'))
            links = row.get('downloads', [])
            names = {filename(d['download_url']).casefold() for d in links if filename(d['download_url'])}
            grouped = len(names) > 1
            row_id = product_id + ':' + str(index)
            source_rows.append({'id':row_id,'path':product['sourcePath'],'index':index,
                               'versionText':row.get('version_text',''),'attributes':row.get('attributes',[]),
                               'downloads':links})
            for link in links:
                raw_links += 1
                url = link['download_url'].strip()
                name = filename(url)
                matches = bool(declared and name and declared.casefold() == name.casefold())
                # An opaque link is assignable only in an unambiguous row.
                assign = matches or (bool(declared) and not name and not grouped)
                evidence = {'rowId':row_id,'row':row,'attrs':a,'declared':declared,
                            'metadataApplied':assign, 'grouped':grouped,'label':link.get('download_type','')}
                by_url.setdefault(url, []).append(evidence)
        groups = {}
        for url, evidence in sorted(by_url.items()):
            safe = [e for e in evidence if e['metadataApplied']]
            safe.sort(key=lambda e: (e['grouped'], len(e['row'].get('downloads',[])),e['rowId']))
            best = safe[0] if safe else None
            name = filename(url) or (best['declared'] if best else None)
            # URLs with the same basename but distinct HTTP language/architecture are not interchangeable.
            key = ('file:' + name.casefold()) if name and (best or url.startswith(('ed2k:', 'magnet:'))) else 'url:' + url
            group = groups.setdefault(key, {'name':name,'links':[], 'evidence':[], 'safe':[]})
            group['links'].append({'url':url,'type': ('http' if url.startswith(('http:','https:')) else split_url(url).scheme or 'other'),
                                   'label':clean((best or evidence[0])['label'])})
            group['evidence'].extend(evidence)
            group['safe'].extend(safe)
        for key, group in sorted(groups.items()):
            safe = sorted(group['safe'],key=lambda e:(e['grouped'],len(e['row'].get('downloads',[])),e['rowId']))
            best = safe[0] if safe else None
            a = best['attrs'] if best else {}
            name = group['name']
            # Do not borrow a grouped row's language or version for a different file.
            title = clean(best['row'].get('version_text')) if best else (name or product['title'] + ' — source link')
            language = classify_language(name or '')
            arch = classify_arch(name or '')
            hint = ' '.join(d['url'] for d in group['links'])
            if language == 'Unknown': language = classify_language(hint)
            if arch == 'Unknown': arch = classify_arch(hint)
            if best and not best['grouped']:
                if language == 'Unknown': language = classify_language(title)
                if arch == 'Unknown': arch = classify_arch(title)
            sha1 = a.get('SHA1',a.get('SHA-1'))
            sha1 = sha1 if sha1 and re.fullmatch('[0-9a-fA-F]{40}',sha1) else None
            provenance = []
            for e in group['evidence']:
                item = {'rowId':e['rowId'],'metadataApplied':e['metadataApplied']}
                if item not in provenance: provenance.append(item)
            resources.append({'id':product_id+'-'+hashlib.sha256(key.encode()).hexdigest()[:16],
                'productId':product_id,'family':product['family'],'product':product['title'],
                'version':title,'title':title,'filename':name,'language':language,'architecture':arch,
                'size':a.get('文件大小',a.get('大小')), 'publishedAt':normalized_date(a.get('发布时间')),
                'sha1':sha1,'sourceUrl':product['sourceUrl'],'attributes':best['row'].get('attributes',[]) if best else [],
                'downloads':group['links'],'provenance':provenance,
                'metadataStatus':'source-reported' if best else 'link-only',
                'hashStatus':'unverified' if sha1 else 'not-provided'})
    # Keep source rows in a companion file: fully auditable without burdening browser parsing.
    meta = {'schemaVersion':1,'sourceRepository':repository,'sourceRevision':revision,
            'importedAt':imported_at,'sourceSnapshotDate':source_snapshot_date,'productCount':len(products),'resourceCount':len(resources),
            'sourceRowCount':len(source_rows),'sourceDownloadOccurrences':raw_links,
            'downloadCount':sum(len(r['downloads']) for r in resources),
            'notice':'Third-party source snapshot. Links, dates, sizes and hashes are source-reported, not independently verified. Availability and authenticity are not guaranteed.',
            'provenanceFile':'provenance.json'}
    return {'meta':meta,'products':products,'resources':resources}, {'meta':meta,'rows':source_rows}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir',required=True,type=Path)
    parser.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parents[1]/'data')
    parser.add_argument('--source-repository',required=True)
    parser.add_argument('--source-revision')
    parser.add_argument('--source-snapshot-date', help='Known source commit date (YYYY-MM-DD); omitted means unknown')
    parser.add_argument('--imported-at',default='2026-10-25T00:00:00Z',help='Explicit snapshot import timestamp; fixed default keeps repeated imports byte-identical')
    args=parser.parse_args()
    catalog,provenance=build(args.source_dir,args.source_repository,args.source_revision,args.imported_at,args.source_snapshot_date)
    if not catalog['products']: parser.error('No docs/**/data.json found')
    args.output_dir.mkdir(parents=True,exist_ok=True)
    for name,data in [('catalog.json',catalog),('provenance.json',provenance)]:
        (args.output_dir/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(catalog['meta'],indent=2))

if __name__=='__main__': main()
