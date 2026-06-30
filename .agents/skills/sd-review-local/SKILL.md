---
name: sd-review-local
description: Use when the user asks to run local code review providers such as Prism, Gito, or a configured repo-local reviewer, choose which findings to fix, and repeat until no selected findings remain.
---

# SD Local Review Loop

Use this project-local skill for `sd-review-local` and `/sd:review-local` style
work. It runs local code review tools, asks the user which findings to fix, and
repeats until the user selects no more findings or the configured tools report
no actionable items.

By default this command is current-diff scoped. It reviews unstaged, staged,
and untracked local files first. If there are no local changed files, it reviews
the current branch diff from the configured base. Use `sd-review-local-all` when
the user asks to review the entire checked-out repository.

This is a local-review-only loop. It does not request remote reviewers, does not
require a pull request, and must not stage, commit, or push unless the user
separately asks for that.

## Tool Selection

The default tool stack is Prism plus Gito. Run it with:

```bash
bash scripts/sd-ai-command-pack-review-local.sh
```

If the user names a specific local review tool, run only that tool or tool set:

```bash
bash scripts/sd-ai-command-pack-review-local.sh prism
bash scripts/sd-ai-command-pack-review-local.sh gito
SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS="prism gito" bash scripts/sd-ai-command-pack-review-local.sh
```

For repo-specific or third-party tool stacks, use the same command loop with a
configured command:

```bash
SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS="semgrep" \
SD_AI_COMMAND_PACK_REVIEW_LOCAL_SEMGREP_COMMAND="semgrep scan --config auto" \
bash scripts/sd-ai-command-pack-review-local.sh
```

The script also accepts `all` or `default` as aliases for `prism gito`.
Per-tool command variables use the pattern
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_<TOOL>_COMMAND`, with the tool name uppercased
and non-alphanumeric characters replaced by underscores.

## Safety Rules

- Start with `git status -sb` and classify existing dirty files before making
  changes. Work with user changes; do not overwrite unrelated work.
- Run the configured local review tools first. Do not fix findings until the
  user selects which findings to address.
- Verify every selected finding against the actual code, specs, and tests
  before editing. Treat local reviewer findings as evidence, not authority.
- Ask before changing product behavior, architecture, dependency choices, or
  other tradeoffs that are larger than the finding itself.
- If a finding is invalid or already addressed, keep it out of the fix list and
  report the evidence. There is no remote review thread to resolve in this
  local-only command.
- Do not stage, commit, push, request remote review, or run PR housekeeping as
  part of this command unless the user separately asks.

## Step 1: Snapshot Local State

```bash
git status -sb
```

If the working tree is dirty before review starts, note which files are user
work and which files are likely part of the current task. Stop and ask before
touching ambiguous files.

## Step 2: Run Local Review Tools

Use the requested tool stack. By default, run Prism and Gito:

```bash
bash scripts/sd-ai-command-pack-review-local.sh
```

The runner applies the pack-managed standard review-scan exclusions to Prism
and Gito, skipping top-level AI/tooling/cache directories such as `.github/`,
`.claude/`, `.codex/`, `.gemini/`, `.opencode/`, `.agents/`, `.build/`,
`.git/`, `.pytest_cache/`, `.obsidian-kb/`, `.trellis/`, `.ruff_cache/`,
`.venv/`, `.sd-ai-command-pack/`, and `node_modules/`.

When Gito reports a provider rate limit such as `ClientError: 429` or `Slow
down`, the runner retries with bounded exponential backoff. Tune that with
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_MAX_ATTEMPTS`,
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_DELAY_SECONDS`, and
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_MAX_DELAY_SECONDS`.

If `scripts/sd-ai-command-pack-review-local.sh` is missing, stop and report
that the pack install is incomplete. Do not substitute `sd-full-check`; this
command's user-selected fix loop depends on the local-review runner.

If a specific custom tool was requested and no command is configured for it,
stop and tell the user which
`SD_AI_COMMAND_PACK_REVIEW_LOCAL_<TOOL>_COMMAND` variable is needed.

Capture the reviewer output, report missing credentials or missing tools, and
group findings by provider, severity when available, path, and theme.

## Step 3: Ask Which Findings To Fix

Present a concise selection list. Group duplicates and false positives before
asking. Ask the user which findings to fix now, for example:

> Local review found these actionable candidates. Which should I fix in this
> pass?

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

## Step 5: Repeat

Run the same local review tool stack again after fixes:

```bash
bash scripts/sd-ai-command-pack-review-local.sh
```

Compare the new output with the prior round. Continue only for findings the
user selects. Stop when the tools report no actionable items, or when the user
selects no remaining findings to fix.

## Final Report

Report:

- Tools requested and tools actually run.
- Findings fixed, skipped as invalid, or left for later.
- Tests and checks run after each fix round.
- Any provider setup problems, missing credentials, or skipped tools.
- Final local review status.
- Final working-tree state.
