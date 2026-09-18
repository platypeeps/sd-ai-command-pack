# Archived work history

This directory accepts newly completed work under `YYYY-MM/`.

The repository removed the earlier archive payload on 2026-09-17.
That payload contained 491 historical work items across several statuses.
Commit `8ba8fa7a15fcd4783b42cbe580a04e89149be08d` preserves every removed file.

Browse the [historical archive snapshot](https://github.com/platypeeps/sd-ai-command-pack/tree/8ba8fa7a15fcd4783b42cbe580a04e89149be08d/docs/work/archive).
Verify and inspect a snapshot path with Git.

```bash
git cat-file -e 8ba8fa7a15fcd4783b42cbe580a04e89149be08d:<path>
git show 8ba8fa7a15fcd4783b42cbe580a04e89149be08d:<path>
```

Restore a file only when its content remains current.

```bash
git restore --source=8ba8fa7a15fcd4783b42cbe580a04e89149be08d -- <path>
```

Do not copy old plans back into the current tree only to preserve history.
Extract any still-current rule into a governing document and link its historical source.
