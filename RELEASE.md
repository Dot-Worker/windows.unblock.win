# Releasing immutable browser assets

Authored files remain `app.js`, `styles.css`, `lib/catalog.mjs`, and `data/catalog.json`.

Before every publication:

```sh
npm run build
npm run build:check
npm test
npm run test:data
```

The Python-standard-library build script computes SHA-256 content fingerprints and emits four files under `assets/`: stylesheet, catalog module, catalog JSON, and the application entry. The generated application imports its fingerprinted module and fetches fingerprinted JSON relative to `import.meta.url`, preserving GitHub Pages repository-subpath support. `index.html` references the fingerprinted CSS and application. The app fingerprint includes rewritten dependency filenames, so changing catalog data or logic also changes the app URL.

Commit and publish `index.html` **and the generated assets together**. `build:check` fails if expected files are missing, bytes differ from authored sources, or HTML points to stale fingerprints. CI must run this check. Do not edit generated files; rebuild instead. No timestamps, network calls, third-party packages, query-string cache settings, or server configuration are required.

The build intentionally retains prior fingerprinted files. This lets already-cached old HTML load its original coherent release instead of receiving new content under old URLs. Do not overwrite or remove published fingerprinted assets casually. New HTML uses genuinely new filenames, including when a CDN ignores query strings. An already open tab or cached HTML still needs navigation/reload before it discovers a new release; verify the served HTML and its referenced filenames after deployment.

The generated catalog preserves all source data except `meta.provenanceFile`, relocated from `provenance.json` to `../data/provenance.json` so the audit pointer resolves from `assets/`. The canonical authored catalog remains unchanged. A regression test verifies both the resolved file and full semantic equality after restoring that one pointer.
