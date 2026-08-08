# Implement — default to local subscription review lanes

Branch: `task/08-07-default-local-review-lanes`
Worktree: session scratchpad `pack-wt`, isolated from the checkout another
session is using on `task/08-07-review-check-stale-cache`.

**Every code edit targets `templates/scripts/...`.** Root `scripts/*` are
byte-verified mirrors (`AGENTS.md:29-33`) refreshed by `make sync`. The
behavioral tests import the template copies directly
(`tests/test_review_stage.py:27`). Editing the root copy first gets overwritten
and leaves the tests reading unchanged code.

Run every command from the worktree root.

## Step 0 — baseline, and capture the reference behavior

```bash
make test 2>&1 | tail -5
codex --version
```

Record the passing count.

AC7 requires proving that a machine without Codex behaves exactly as it does
today. Capture that reference **now**, from the unmodified tree, with `codex`
hidden from `PATH`:

```bash
mkdir -p .build/ac7 && env PATH=/usr/bin:/bin \
  python3 -m pytest tests/test_review_stage.py -q > .build/ac7/baseline.txt 2>&1; tail -3 .build/ac7/baseline.txt
```

Then observe the exit codes the adapter must map — the design deliberately
refuses to assume them:

```bash
cd /tmp && codex exec -s read-only --ephemeral -o /tmp/codex-out.json "reply with {}"; echo "exit=$?"
codex exec -s read-only --ephemeral -o /tmp/codex-out.json --output-schema /nonexistent.json "x"; echo "exit=$?"
```

Write the observed codes into `design.md`'s exit-code section before writing the
mapping. Anything unmapped falls through to `unavailable`.

## Step 1 — the eligibility gate (do this first)

This is the change that prevents a regression, so it lands before the provider
that depends on it.

- [ ] `templates/scripts/sd-ai-command-pack-review-local.py:1211-1215` — extend
  the `eligible` comprehension with an availability predicate: a provider whose
  adapter names a required executable is eligible only when
  `shutil.which(<executable>)` is not `None`.

Validation:

```bash
env PATH=/usr/bin:/bin python3 -m pytest tests/test_review_stage.py -q 2>&1 | tail -3
```

Must match `.build/ac7/baseline.txt`. At this point no codex provider exists
yet, so this step must be a no-op — if it is not, the predicate is wrong.

## Step 2 — the findings schema

Do **not** create a file under `config/`; it is consumer-owned and not
installed by the pack.

- [ ] Add the JSON Schema as a module-level literal in
  `templates/scripts/...review-local.py`. Fields: `status` enum
  `clean|findings`; `findings` array of
  `{path, line, severity, summary, family}`.

`summary` and `family` are mandatory and are **not** `title`/`details`.
`_bounded_provider_findings` (`:1640-1642`) reads exactly `summary` and
`family`, defaulting them to `"provider finding"` and `"other"` — a schema using
other names validates and then discards every finding's content.

- [ ] Write it to `attempt_dir/codex-schema.json` where `attempt_dir` is created
  (`:1657-1658`), for the codex adapter only.

Validation:

```bash
grep -rn "config/codex" templates/ scripts/ tests/
grep -n '"title"\|"details"' templates/scripts/sd-ai-command-pack-review-local.py
```

The first must return nothing. The second must show no `title`/`details` in the
new schema literal (existing `_gito_payload` hits at `:1600-1604` are expected —
gito maps *from* those names).

## Step 3 — provider vocabulary and defaults

- [ ] `review-local.py:398` — add `codex` to the adapter allow-list.
- [ ] `review-local.py:_default_config()` — add the `codex` provider:
  `adapter: "codex"`, `costTier: "none"`,
  `dataHandling: "public-network"`, `qualityTier: "standard"`, scopes as the
  shared block, `outcomeByExitCode` from Step 0, `timeoutSeconds` at least
  gito's 600 since an agent loop is slower than one API call. `argv` may be
  omitted — it defaults to `[]` (`:402`).
- [ ] `templates/scripts/sd-ai-command-pack-review.py:220` — add the matching
  entry.

Validation:

```bash
python3 -c "
import importlib.util
def load(p,n):
    s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
a=load('templates/scripts/sd-ai-command-pack-review-local.py','a')
print([(p['id'],p['costTier']) for p in a._default_config()['providers']])
"
```

Expect `codex`/`none` present and first by cost tier.

## Step 4 — command construction

- [ ] `_expand_argv` (`review-local.py:1376`; prism at `:1386`, gito at `:1412`)
  — add the `codex` branch:
  `codex exec -s read-only -C <repo> --ephemeral --output-schema
  <attempt_dir>/codex-schema.json -o <attempt_dir>/codex-review.json
  <scope prompt>`.

The function is `_expand_argv`, not `_provider_command`. The output filename must
not be `provider-output`; that name is a *directory* for gito.

- [ ] Scope prompts for `worktree`, `branch_delta`, `codebase` per `design.md`.

`-s read-only` is a correctness requirement: non-PR scopes are worktree-only and
a reviewer must not be able to mutate the tree.

## Step 5 — payload parsing

- [ ] `_parse_provider_payload` (`:1612-1616`) — add the `codex` branch reading
  `attempt_dir/codex-review.json` via `_read_json(..., limit=MAX_OUTPUT_BYTES,
  ...)`, then the validation `_parse_argv_payload` (`:1515-1522`) applies.
- [ ] Return `None` on malformed or missing output. Never synthesize
  `status: "clean"`.

## Step 6 — the bounded ensemble

- [ ] `review-local.py:1257-1263` — remove the `{"prism", "gito"}` literal.
  Filter `eligible` by `policy.ensembleProviders`, a new policy key defaulting
  to `["codex", "gito", "prism"]`.

Do **not** use `list(eligible)`. It sweeps in repository-defined `argv`
providers, silently promoting `auto` substantive review to `all`, and it is
observable: membership feeds the policy digest and receipt identity (`:1295`,
`:1973`) and the router evidence's `providers`, `latencyMs`, and maximum
`costTier` (`review.py:951`).

Validation — the enumerating check:

```bash
grep -rn '"prism", "gito"' templates/scripts/ scripts/
```

Must return nothing anywhere, not just in the file you edited.

## Step 7 — the shell entrypoint

The shell has per-tool state and dispatch, not a generic loop (`:702`, `:730`).
An unrecognized token hits the unknown-tool branch and exits 2, so changing the
default list alone would make the default set fail immediately.

- [ ] Add codex dispatch and its state alongside prism and gito.
- [ ] `review-local.sh:643` — default tool set includes `codex`.
- [ ] `review-local.sh:196-197` — `all` and `default` aliases updated.
- [ ] `--help` lists `codex`.

Validation — invoke it, do not read the help text:

```bash
bash templates/scripts/sd-ai-command-pack-review-local.sh codex --plan-only; echo "exit=$?"
```

Exit 2 with an unknown-tool diagnostic means dispatch is still missing.

## Step 8 — tests

- [ ] AC5: stub `codex` on `PATH`, low-risk worktree review → `codex` runs,
  `prism` and `gito` do not. Follow the stub-binary pattern at
  `tests/test_review_local.py:167-193`.
- [ ] AC6: stub `codex`, substantive-risk review → `codex` **and** the metered
  providers run.
- [ ] AC7: no `codex` on `PATH` → rerun the Step 0 command and diff against
  `.build/ac7/baseline.txt`. Identical output is the pass condition. An
  assertion written by hand is not.
- [ ] AC2: assert the two default configs agree on provider ids and cost tiers.
- [ ] `tests/test_review_stage.py:1115-1118` — the exact-set assertion
  `["gito", "prism"]` for `substantive-ensemble` becomes
  `["codex", "gito", "prism"]` with a codex stub present, and stays
  `["gito", "prism"]` without one.
- [ ] Update the provider-set enumerations in `tests/test_review_local.py`
  (`:98`, and the `for name in ("prism", "gito")` loops at `:215`, `:268`,
  `:319`) to the new expected set. Do **not** loosen an assertion to make it
  pass; a set assertion that stops naming providers stops testing selection.

Validation:

```bash
python3 -m pytest tests/test_review_local.py tests/test_review_stage.py tests/test_review_controller.py -q 2>&1 | tail -5
```

Zero failures. Then prove AC5 is real: temporarily set the codex provider's
`costTier` to `"high"` and rerun — the AC5 test must fail. Restore `"none"`.

## Step 9 — documentation

Enumerate first; do not work from a remembered list:

```bash
grep -rln -i codex templates/
```

Classify every hit into one of three buckets — **local-review lane** (in scope),
**planning-adversarial-review lane** (out of scope, a different feature), or
**unrelated `.codex/` directory listing** (leave alone). As of this plan:

In scope:

- [ ] `templates/.agents/skills/sd-review-local/SKILL.md:155` — the
  `Claude Code Native Codex Lane` section. Codex is now *also* a configured
  provider. Name the two lanes distinctly per `design.md`.
- [ ] `templates/.claude/commands/sd/review-local.md:40-44` — defers to that
  section and repeats `command -v codex` gating. Update to match.
- [ ] `templates/.agents/skills/sd-help/references/command-catalog.md:40` —
  description text.
- [ ] `templates/docs/SD_AI_COMMAND_PACK.md:861` and `:1819` — the local-review
  sections.
- [ ] `templates/.agents/skills/sd-review/SKILL.md` — does not currently mention
  Codex, so this is an addition: the provider lane, and the Claude-native
  pre-push lane. State explicitly that native-lane results do **not** reach the
  router; the coordinator builds router evidence only from its own local receipt
  (`review.py:1839`, `:1941`).
- [ ] State that a repository with its own `.sd-ai-command-pack/review.json`
  does not inherit the new default and must add the provider itself.

Out of scope — do not edit:

- `templates/docs/SD_AI_COMMAND_PACK.md:32` — the planning-adversarial-review
  "Codex CLI peer lane". Different feature.
- `templates/.agents/skills/sd-full-check/SKILL.md:72` and
  `templates/.github/copilot-instructions.sd-ai-command-pack.md:18` —
  `.codex/` directory listings.

Validation:

```bash
grep -rn -i "peer lane\|additive" templates/ | grep -i codex
```

Every surviving hit must be a planning-review reference, not a local-review one.

## Step 10 — release payload requirements

`CONTRIBUTING.md:136-142` — CI-enforced, not advisory. A `Release payload gate`
job blocks merge without these.

- [ ] Bump `manifest.json` version.
- [ ] `manifest.json:6` — description no longer promises "Prism/Gito defaults".
- [ ] Add a matching top `CHANGELOG.md` heading.
- [ ] `make release-prep` to produce or reuse an all-pass
  `docs/fleet/candidate-validation.json` matching the exact payload and fleet
  manifest. Run it **after** all payload edits; earlier generation or sync
  changes invalidate its evidence.

## Step 11 — sync and full gate

```bash
make sync
make surface-check
make check
```

`make sync` propagates `templates/` into the root mirrors; `surface-check` must
report no drift. `make check` runs `test`, `lint`, `audit`, `full-check` — zero
failures across all four.

Then confirm scope:

```bash
git diff --stat origin/main
```

No change to routed-review protocol files or to the `localReview` evidence
schema.

## Step 12 — ship

```bash
git add -A
git commit
git push -u origin task/08-07-default-local-review-lanes
```

PR body must state: substantive-risk reviews now run an additional free
provider; consumers without the Codex CLI see no behavior change; consumers with
a custom `review.json` do not inherit the change.

## Rollback points

- After Step 1: the eligibility gate alone is a no-op and safe to keep or drop.
- After Step 6: changes are confined to the two Python modules; reverting them
  restores previous selection exactly.
- After Step 11: `git revert` of the single commit.

## Review gates

- Before Step 12, walk every `prd.md` acceptance criterion and cite the specific
  command output or file line that satisfies it.
- AC7 is the one most likely to be reported as passing without having been run.
  It requires an actual diff against `.build/ac7/baseline.txt` captured in
  Step 0. If Step 0's baseline was never captured, AC7 cannot be claimed.
- AC4 (no surviving literal) and AC8 (shell actually dispatches) both require
  running a command, not reading a file.
- Step 0's observed exit codes must appear in the committed mapping. If they
  were never observed, say so rather than shipping assumed values.
