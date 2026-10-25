# Resource snapshot and normalization

## Attribution and scope

Data imported from [wangzhenjjcn/Microsoft_Resources](https://github.com/wangzhenjjcn/Microsoft_Resources), revision `f69e23f8bf478004d45abd56757674155b1ece0a`. The upstream snapshot contains 46 `docs/**/data.json` files and identifies individual page sources on `imsdn.cn`. This is an archival third-party listing, not an official Microsoft catalog. The revision's commit date is 2025-10-09; the explicit import timestamp is 2026-10-25T18:54:00Z. Import time is not resource freshness or last verification time.

The upstream README claims MIT, but no LICENSE file was present in the supplied snapshot. That licensing statement has not been independently established; attribution does not imply an ownership grant. No upstream application code is included here. The importer and replacement UI are independently written. Software binaries and third-party links retain their respective rights and terms.

No binaries were downloaded, no upstream scraper executed, and no links or checksums were independently verified. A source-reported SHA-1 is not evidence of authenticity. Links may expire or require third-party software/accounts. The snapshot contains older, potentially unsupported products.

## Schema (version 1)

`catalog.json` contains:

- `meta`: source repository/revision, nullable source commit date (`sourceSnapshotDate`), explicit import timestamp, counts, caveat, provenance filename.
- `products`: `id`, `title`, `family`, `intro`, `sourceUrl`, `sourcePath`.
- `resources`: stable `id`, `productId`, `family`, `product`, `version`, `title`, nullable `filename`, `language`, `architecture`, nullable `size`, nullable `publishedAt`, nullable `sha1`, `sourceUrl`, `attributes`, `downloads`, `provenance`, `metadataStatus`, `hashStatus`.
- Downloads are `{url, type, label}`; `type` is `http`, `ed2k`, or `magnet` in this snapshot. HTTP means HTTP(S), not a trust rating.
- `language`: `Simplified Chinese`, `Traditional Chinese`, `English`, `Multilingual`, or `Unknown`.
- `architecture`: `x64`, `x86`, `ARM64`, `x86 + x64`, `IA64`, `x86 + x64 + IA64`, or `Unknown`.
- `size` preserves a source display string, not a computed byte value. `publishedAt` is a valid normalized ISO date only when supplied for a matching resource; otherwise null.
- `metadataStatus` is `source-reported` or `link-only`. `hashStatus` is `unverified` or `not-provided`.
- Each provenance item points to a raw source row ID and says whether its metadata was safely applicable.

`provenance.json` preserves original version headings, attribute arrays, link labels and URLs, source paths and row indexes. It is companion audit data, not needed for ordinary browsing. It intentionally preserves upstream errors without promoting them to normalized facts.

## Normalization policy

The upstream first row often aggregates links for multiple editions/architectures. Links are split by identity before metadata is assigned. A filename-bearing link receives a row's file metadata only when its filename matches that row's declared filename. Opaque links may inherit a filename only from a row with no conflicting filename-bearing links. Unassignable opaque links remain separate and unknown. File links are joined across protocols by filename within a product, retaining distinct URLs; generic Office image filenames without matching declared metadata remain URL-specific, preventing locale merging. Repeated identical URLs within a product are collapsed. IDs are product slug plus the first 16 hex characters of SHA-256 of the stable identity key; this is an identifier, not a file checksum.

Language and architecture are inferred first from filenames, then explicit URL tokens. An unambiguous matching source heading is a final fallback. Missing metadata is not fabricated, and grouped headings are not used as fallback. Invalid SHA-1 text stays in raw attributes rather than being promoted to `sha1`. No release dates are inferred from names, ordering, product intros, or import time.

## Offline reproduction

From the application directory, with the exact upstream snapshot available separately:

```sh
python scripts/import_catalog.py \
  --source-dir /path/to/Microsoft_Resources \
  --source-repository https://github.com/wangzhenjjcn/Microsoft_Resources \
  --source-revision f69e23f8bf478004d45abd56757674155b1ece0a \
  --source-snapshot-date 2025-10-09 \
  --imported-at 2026-10-25T18:54:00Z
python -m unittest discover -s tests -p 'data*.py'
```

Only Python's standard library is required. The importer does not access the network and produces deterministic bytes for identical inputs and arguments. The current output has 46 products, 209 resources, and 255 download links from 244 source rows containing 514 link occurrences.
