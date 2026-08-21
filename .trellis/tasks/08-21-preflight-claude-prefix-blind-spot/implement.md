# Implementation plan — stop ignoring `.claude/` path citations

Branch off `main` before step 1 (`fix/preflight-claude-prefix-blind-spot`).
Direct pushes to `main` are chore-scope only; this touches `scripts/`.

## Step 1 — baseline the failure set

```bash
node scripts/sd-ai-command-pack-review-preflight.mjs | tail -3
```

Expect `0 failure(s)`. This is the "before" side: every failure the rest of this
plan is about is invisible at this point, which is the defect.

## Step 2 — change the checker

In `templates/scripts/sd-ai-command-pack-review-preflight.mjs` — the source of
truth (`CONTRIBUTING.md:153`). Do not edit the `scripts/` mirror: `make sync`
reinstalls it from `templates/` and silently discards the edit.

1. Delete the `'.claude/',` line from `ignoredReferencePrefixes` (line 436).
   Leave the identical line at 378 — that one is `referencePrefixes` and is the
   list that should have been winning.
2. Add to `optionalReferencePaths`, in sorted position, with a comment:

   ```js
   // Per-checkout machine state, gitignored at .gitignore:66. Absent in a
   // clean clone, so a citation of it is not a dangling path.
   '.claude/settings.local.json',
   ```

Verify both lists afterwards — the entry must be gone from one and present in
neither by accident:

```bash
grep -n "'\.claude/'," templates/scripts/sd-ai-command-pack-review-preflight.mjs
```

Expect exactly one hit, at the `referencePrefixes` line.

## Step 3 — assert it

In the node harness inside `tests/test_review_preflight.py`, in the
`shouldCheckDocumentationPathReference` block (lines 810–824), add:

```js
assert.equal(shouldCheckDocumentationPathReference('.claude/skills/sd-work-backlog/SKILL.md'), true);
assert.equal(shouldCheckDocumentationPathReference('.claude/settings.json'), true);
assert.equal(shouldCheckDocumentationPathReference('.claude/settings.local.json'), false);
```

The second line is the pair the file's own convention (line 826) requires: the
third passes vacuously against the pre-change checker, and only the second
distinguishes "exempt because machine-local" from "whole tree ignored".

Confirm the first assertion is not vacuous against the pre-change checker.
Stash only the checker, so the new assertions stay in the tree:

```bash
git stash push scripts/sd-ai-command-pack-review-preflight.mjs \
  templates/scripts/sd-ai-command-pack-review-preflight.mjs
.venv/bin/python -m unittest \
  tests.test_review_preflight.ReviewPreflightTests.test_review_preflight_exports_reusable_helpers
git stash pop
```

The middle command must FAIL — that node harness is where the assertions live
(`tests/test_review_preflight.py:81`). There is no pytest in the venv; the
suite is unittest, driven by `make test`. A test that passes both before and
after has pinned nothing.

## Step 4 — repair the five newly-visible citations

Marker rule: `[absent: <reason>]` must follow the citation with only spaces or
tabs between. Punctuation moves after the closing bracket; it may not sit
between the backtick and the `[`.

| file:line | action |
| --- | --- |
| `.trellis/tasks/07-25-agent-artifacts/research/cross-platform-agent-support.md:48` | reword: `.claude/.codex/.gemini/.opencode/.github` is prose shorthand for five directories, not a path. Name the platforms instead. A marker cannot fix this — the token would still parse as a path. |
| `.trellis/tasks/08-07-plugin-review-provider-lanes/prd.md:312` | insert marker between the closing backtick and the comma; reason: provider lane never built |
| `.trellis/tasks/08-07-plugin-review-provider-lanes/prd.md:313` | same, on the `.claude/commands/sd/review-local.md` citation |
| `.trellis/tasks/08-08-upstream-handoff-register/research/07-27-upstream-claude-statusline-utf8-stdin-fix.md:11` | insert marker directly after the closing backtick; reason: upstream Claude Code path, not a repository file |
| `.trellis/tasks/08-09-deployment-thin-consumers/research/claude-code-plugin-capabilities.md:56` | no edit — step 2's config entry covers it |

Do not delete or repoint any of these citations. Each supports a claim about
what a path was or will be; rewriting the path falsifies the claim.

## Step 5 — repair this task's own `prd.md`

`prd.md` quotes all four shapes and fails under the new rule. `design.md` and
`implement.md` do not: the checker exempts task design/implement artifacts at
line 3236, because they are forward-looking and cite files the task proposes to
create. Research notes are not exempt.

Treatments are the same as step 4 — reword the `.claude/.codex/...` shorthand,
mark the `.claude/hooks/statusline.py` citation, leave the
`.claude/settings.local.json` citations alone. Rerun the checker rather than
working from a count; skipping this step means the task cannot pass its own
gate.

## Step 6 — whole-tree verification

```bash
node scripts/sd-ai-command-pack-review-preflight.mjs | tail -3
```

Expect `0 failure(s), 0 warning(s)`. Any remaining `.claude/` FAIL is either a
missed site from steps 4–5 or a real dangling path — read it, do not silence it.

## Step 7 — propagate

```bash
make sync && make generate
```

Sync first. `make sync` runs `install.py . --force`, installing `templates/`
into `scripts/` and the adapter trees; `make generate` then rebuilds `plugins/`
and runs surface closure, which fails `mirror.stale` if the mirrors have not
been installed yet. Then confirm all four checker copies carry the change:

```bash
for f in scripts templates/scripts plugins/sd/bin plugins/sd/machine-payload/scripts; do
  printf '%s ignore=%s optional=%s\n' "$f" \
    "$(grep -c "'\.claude/'," "$f/sd-ai-command-pack-review-preflight.mjs")" \
    "$(grep -c "settings\.local\.json" "$f/sd-ai-command-pack-review-preflight.mjs")"
done
```

Expect `ignore=1 optional=1` on all four lines — one `.claude/` entry left
(the `referencePrefixes` one) and the new exemption present. `ignore=2`
anywhere means that copy did not receive the change.

## Step 8 — version and changelog

Bump the patch version in `manifest.json` and add a matching `CHANGELOG.md`
entry under `### Fixed`, naming both halves: the contradiction removed, and the
one exemption added with its reason.

## Step 9 — full check

```bash
make check
```

The candidate ledger may go stale because surfaces moved; if the pre-push hook
reports `mirror.stale` or a stale ledger, regenerate with
`.venv/bin/python scripts/sd-ai-command-pack-fleet-candidate-check.py` (~60s).

## Step 10 — ship

Open the PR, let CI and the Copilot round settle, merge. Consumers pick the
rule up on their next refresh; refreshing them is out of scope.

## Step 11 — se-ai-command-pack

One citation there becomes visible under the new rule. Fix it in that
repository, with the same treatment rules as step 4, so its next refresh does
not red on this change. This is a separate PR and does not block step 10.

## Rollback points

- After step 2, before step 7: revert the two config edits; nothing else has moved.
- After merge: re-add the one `ignoredReferencePrefixes` line. The step-4 and
  step-5 repairs are correct independently and need not be reverted.
