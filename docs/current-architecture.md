# Current architecture

This page describes the current command pack.
Git history preserves the retired designs and completed work records.

## Repository model

The repository owns one payload copy under `skills/`.
Nothing renders into this checkout.
The installer reads that payload and creates machine-level links.
`manifest.json` defines the shipped payload and command inventory.
This page summarizes that enforced model.

The executable entrypoints live under `bin/`.
Each installed command links back to the serving checkout.
The installation receipt records owned links and their digests.
Run `bin/sd_install.py --status` to inspect the current installation.

The installer does not edit shell configuration.
The selected installation directory must already be on `PATH`.

## Work model

Active plans live under `docs/work/<item>/`.
Each plan uses `prd.md` and optional `design.md` or `implement.md` files.
Database rows own live task status.
An existing task binds through `item: sd:<id>` in PRD frontmatter.

Completed plans can move into `docs/work/archive/YYYY-MM/`.
The repository removes obsolete archive payload in reviewed batches.
Commit `8ba8fa7a15fcd4783b42cbe580a04e89149be08d` preserves that snapshot.
The [archive index](work/archive/README.md) explains recovery.

## Documentation model

Governing documents state current rules once.
Other documents link to the governing statement.
Work records keep dated evidence and distinct decision changes.
Git history preserves removed discussions and completed plans.

Use STE-Concise for new and revised prose.
Keep sentences active, direct, and no longer than 20 words.
Preserve exact commands, paths, identifiers, and quoted evidence.

## Validation model

`make check` is the repository aggregate check.
It runs lint, audit, documentation lint, and tests.
Run it without `CHANGED` before publication.

The changed-files mode selects a smaller development test set.
It exits nonzero because it omits full coverage gates.
Read [CONTRIBUTING.md](../CONTRIBUTING.md) for exact commands and limitations.

## Delivery model

Use the pack's ship workflow for branch publication, review, and merge.
Use the review workflow for local review before publication.
The active branch-protection exception lives in `.github/sd-status.json`.
Run `bin/sd-status` to inspect the live repository state.

## Historical design

The artifacts-as-product design created the current machine-scope model.
Its documents remain in the current archive:

- [Design record](work/archive/2026-09/2026-08-29-artifacts-as-product/design.md)
- [Implementation record](work/archive/2026-09/2026-08-29-artifacts-as-product/implement.md)

Treat those files as historical evidence.
This page and current code define present behaviour.
