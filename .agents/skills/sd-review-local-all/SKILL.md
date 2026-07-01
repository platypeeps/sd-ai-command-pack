---
name: sd-review-local-all
description: Use when the user asks to run local code review providers such as Prism, Gito, or a configured repo-local reviewer against the entire checked-out repository, choose which findings to fix, and repeat until no selected findings remain.
---

# SD Full-Codebase Local Review Loop

Use this project-local skill for `sd-review-local-all` and
`/sd:review-local-all` style work. It runs local code review tools against the
entire checked-out repository, asks the user which findings to fix, and repeats
until the user selects no more findings or the configured tools report no
actionable items.

This is a local-review-only loop. It does not request remote reviewers, does not
require a pull request, and must not stage, commit, or push unless the user
separately asks for that.

## Tool Selection

The default tool stack is Prism plus Gito in full-codebase mode. Run it with:

```bash
bash scripts/sd-ai-command-pack-review-local.sh --all
```

If the user names a specific local review tool, run only that tool or tool set:

```bash
bash scripts/sd-ai-command-pack-review-local.sh --all prism
bash scripts/sd-ai-command-pack-review-local.sh --all gito
SD_AI_COMMAND_PACK_REVIEW_LOCAL_SCOPE=all \
SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS="prism gito" \
bash scripts/sd-ai-command-pack-review-local.sh
```

For repo-specific or third-party tool stacks, use an all-scope command when the
tool needs different arguments for a full repository scan:

```bash
SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS="semgrep" \
SD_AI_COMMAND_PACK_REVIEW_LOCAL_ALL_SEMGREP_COMMAND="semgrep scan --config auto" \
bash scripts/sd-ai-command-pack-review-local.sh --all
```

The script also accepts `all` or `default` as tool aliases for `prism gito`.
Per-tool command variables use the pattern
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_ALL_<TOOL>_COMMAND`, with the tool name
uppercased and non-alphanumeric characters replaced by underscores. If the
all-scope command is not set, the runner falls back to
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_<TOOL>_COMMAND`.

## Safety Rules

- Start with `git status -sb` and classify existing dirty files before making
  changes. Work with user changes; do not overwrite unrelated work.
- Run the configured local review tools first. Do not fix findings until the
  user selects which findings to address.
- Treat full-codebase findings as candidates. Verify every selected finding
  against the actual code, specs, and tests before editing.
- Ask before changing product behavior, architecture, dependency choices, or
  other tradeoffs that are larger than the finding itself.
- If a finding is invalid, low-value churn, or already addressed, keep it out
  of the fix list and report the evidence.
- Do not stage, commit, push, request remote review, or run PR housekeeping as
  part of this command unless the user separately asks.

## Step 1: Snapshot Local State

```bash
git status -sb
```

If the working tree is dirty before review starts, note which files are user
work and which files are likely part of the current task. Stop and ask before
touching ambiguous files.

## Step 2: Run Full-Codebase Local Review Tools

Use the requested tool stack. By default, run Prism and Gito across the whole
checked-out repository:

```bash
bash scripts/sd-ai-command-pack-review-local.sh --all
```

Default provider behavior:

- Prism runs `prism review codebase`, which reviews all tracked files according
  to Prism's provider behavior, any configured Prism rules, and the
  pack-managed standard review-scan exclusions for top-level AI/tooling/cache
  directories such as `.github/`, `.claude/`, `.codex/`, `.gemini/`,
  `.opencode/`, `.agents/`, `.build/`, `.git/`, `.pytest_cache/`,
  `.obsidian-kb/`, `.trellis/`, `.ruff_cache/`, `.venv/`,
  `.sd-ai-command-pack/`, and `node_modules/`. If Prism reports an
  `empty chunk response` in full-codebase mode, the runner retries in tracked
  file batches and splits a failed batch down to individual paths when needed.
  Override the batch size with
  `SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_CODEBASE_BATCH_SIZE`, or set
  `SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_CODEBASE_FALLBACK=0` to disable the
  fallback.
- Gito runs `gito review --all --path <repo-root>` with an include filter after
  applying the same standard exclusions. The include filter is built from
  existing tracked files, so branch-diff deletions are not reviewed as deleted
  diff paths. Reports are written to `.build/review/gito-all` by default. The
  runner sets `UV_CACHE_DIR` and `UV_TOOL_DIR` to writable temp directories
  when they are unset so `uvx`-based Gito wrappers do not need to write under a
  restricted home directory. When Gito reports a provider rate limit through an
  explicit HTTP 429 status such as `ClientError: 429`, the runner retries with
  bounded exponential backoff. Tune that with
  `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_MAX_ATTEMPTS`,
  `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_DELAY_SECONDS`, and
  `SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_MAX_DELAY_SECONDS`.

If `scripts/sd-ai-command-pack-review-local.sh` is missing, stop and report
that the full-codebase local review runner is not installed. Do not substitute
the diff-scoped full-check command for this command.

If a specific custom tool was requested and no command is configured for it,
stop and tell the user which
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_ALL_<TOOL>_COMMAND` or
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_<TOOL>_COMMAND` variable is needed.

Capture the reviewer output, report missing credentials or missing tools, and
group findings by provider, severity when available, path, and theme.

## Step 3: Ask Which Findings To Fix

Present a concise selection list. Group duplicates and false positives before
asking. Ask the user which findings to fix now, for example:

> Full-codebase local review found these actionable candidates. Which should I
> fix in this pass?

If the user selects none, stop the loop. Do not make edits just because a tool
reported findings.

## Step 4: Fix Selected Findings

For each selected finding:

1. Read the relevant code, tests, docs, and specs.
2. Implement the smallest correct fix.
3. Add or update tests when behavior changes or the risk is nontrivial.
4. Run the narrowest relevant checks first, then broader checks warranted by the
   touched files.

If a selected finding turns out to be wrong, explain the evidence and ask
whether to skip it or address a different underlying issue.

If a check fails after a selected fix, stop the loop, report the command and
failure output, and leave the working tree available for inspection. Do not
continue stacking fixes until the failed check is understood.

## Step 5: Repeat

Run the same full-codebase local review tool stack again after fixes:

```bash
bash scripts/sd-ai-command-pack-review-local.sh --all
```

Compare the new output with the prior round. Continue only for findings the
user selects. Stop when the tools report no actionable items, or when the user
selects no remaining findings to fix.

## Final Report

Report:

- Tools requested and tools actually run.
- Full-codebase scope, including any provider that could not run repo-wide.
- Findings fixed, skipped as invalid, or left for later.
- Tests and checks run after each fix round.
- Any provider setup problems, missing credentials, or skipped tools.
- Final local review status.
- Final working-tree state.
