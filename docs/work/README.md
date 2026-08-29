# Work items

One directory per item: `<YYYY-MM-DD>-<slug>/prd.md` (+ `design.md`, `implement.md` when
warranted). Frontmatter `status:` is `planning | ready | in_progress | done`; `in_progress`
requires `branch:`. Merged and aged items move to `archive/YYYY-MM/`. Pull requests reference
an item with a `Work:` line. This directory is the entire tracked footprint of the
sd-ai-command-pack workflow; nothing else in the repo is framework bookkeeping.
