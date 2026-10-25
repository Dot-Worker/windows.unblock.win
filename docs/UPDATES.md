# Live catalog updates (GitHub Actions)

## What is fetched

`Update live catalog and deploy` runs daily at **22:06 UTC / 06:06 UTC+8**, and on **Actions → Update live catalog and deploy → Run workflow** on `main`. Maintainer pushes to `main` also run the same verified update/deploy pipeline; the bot’s own scoped commit does not recursively trigger it.

The updater reads `https://www.imsdn.cn/robots.txt`, the home page, all six product categories, and **every discovered product page on each check**. Product discovery is not a frozen list: new product links in the supported categories are included automatically. The public source must allow the requests. Only HTML and robots are fetched; ISO/executable/torrent files and download targets are never fetched. The independent Python-standard-library parser does not run upstream scraper code or use old GitHub JSON as a fallback. The original GitHub repository is retained as historical reference, not misrepresented as the live source.

The source itself may still list old versions. A successful fresh check means “we fetched and parsed the source now,” not “Microsoft published new media now,” nor a guarantee that third-party links work or files are authentic.

## Data, provenance and freshness

- `data/catalog.json`: normalized browser catalog. A first migration sets `meta.sourceMode: live-html`, `meta.sourceSite`, null `sourceRevision`, null `sourceSnapshotDate`, and a deterministic `sourceContentDigest`.
- `data/provenance.json`: parsed source rows and the same catalog metadata.
- `data/update-status.json`: truthful check status, independent of resource release dates:
  - `attemptedAt`: latest actual attempt.
  - `checkedAt`: last complete successful live check; unchanged on failure.
  - `updatedAt`: last catalog replacement, including initial migration; unchanged on a genuine no-change check.
  - `status`: `not-run`, `updated`, `unchanged`, or `failed`.
  - `catalogDigest`: SHA-256 of canonical products/resources, excluding timestamps.
  - `contentChanged` and `sourceMigration`: distinguish actual semantic changes from first migration.
  - `counts`, `workflowRunUrl`, and sanitized `error` when failed.

On identical source data, **catalog and provenance bytes stay identical**. The status check time still changes and is deployed. Because the UI consumes a fingerprinted status asset, its app/status hash may change even when the catalog hash stays the same. The builder retains only the current and previous complete asset graphs (`assets/releases.json`); git history retains earlier data and source revisions for recovery.

## Fail closed

Any fetch/robots failure, challenge page, malformed or ambiguous section, missing known product, duplicate ID, orphan/empty resource, or reduction in an existing product's normalized resource or download-link count rejects the update. Unlabelled source download sections are retained as link-only records without borrowing neighboring metadata. Grouped links are normalized independently by the existing importer.

The complete scrape and validation finish before either published document is touched. Promotion errors restore both original documents. Failure status retains last-success timestamps/counts/digest. Tests run before committing; if they fail, nothing is committed or deployed.

On a **source collection failure**, the workflow publishes only the honest failed-check status against the last-good catalog and then fails its final verdict job. The workflow therefore stays red rather than disguising a blocked source as a successful update. A failed deployment is also red. No automatic deletion approval or lower safety threshold is exposed by workflow inputs; legitimate source removals require a reviewed code/data change.

## Deployment and permissions

One workflow owns fetch → normalize → validate → fingerprint → scoped commit → artifact upload → Pages deployment. It does **not** rely on the bot's push triggering another workflow. GitHub documents that `GITHUB_TOKEN` pushes do not trigger ordinary push workflows:

- [Trigger a workflow](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)
- [Custom GitHub Pages workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)

Repository Pages publishing must be **GitHub Actions**. The refresh job has only `contents: write`; the deploy job has only `pages: write` and `id-token: write`; the verdict job has no permissions. No PAT, deploy key, custom secret, or repository-wide token permission increase is required. If branch/environment protection rejects a write/deployment, investigate that explicit failure; do not bypass protection.

The commit is restricted to catalog/provenance/status, generated assets/retention manifest, and `index.html`. Push is non-forced; concurrent main-branch edits make the run fail rather than overwrite them. Workflow concurrency prevents overlapping updater deployments. The Pages artifact includes static site files only, not workflow/scripts/tests.

## Verify end-to-end

1. Run the workflow manually on `main`. Check `refresh`, `deploy`, **and `verdict`**, not just an individual green step.
2. Confirm its scoped commit exists on `main`, the Pages deployment succeeds, and the public site’s hashed status/catalog match the run.
3. Run it again while source content is unchanged: expect `status: unchanged`, identical `catalogDigest` and catalog bytes, newer `checkedAt`, and unchanged `updatedAt`.
4. Offline tests cover new products, grouped links, unsupported links, ambiguous pages, missing products, resource loss, redirects, network failures, transactional write failures, changed/no-change behavior, and generated browser hash propagation.

Local checks (no third-party Python dependencies):

```sh
python -m unittest discover -s tests -p '*test.py' -v
python scripts/build_assets.py --prune
npm test
python scripts/build_assets.py --check
```

A live local preflight must use a copy of `data/` and `--output-dir /path/to/copy` when preserving deployment data for an actual Actions test.

Schedules are best-effort, can be delayed, and GitHub can disable scheduled workflows in inactive public repositories. Check the latest run and UI freshness rather than assuming the cron entry guarantees operation. If disabled, re-enable the existing workflow in Actions and run it manually. Do not add a secret or external scheduler merely to hide that state.
