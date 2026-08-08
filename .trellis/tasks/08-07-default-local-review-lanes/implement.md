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

AC7 requires proving that a machine without Codex selects and runs the same
providers as today. Capture that reference **now**, from the unmodified tree,
with `codex` hidden from `PATH`. Strip only the directory holding `codex` rather
than hardcoding `PATH=/usr/bin:/bin`, which would also hide `git` and any
Homebrew Python the suite depends on:

```bash
mkdir -p .build/ac7
CODEX_DIR="$(dirname "$(command -v codex)")"
NOCODEX_PATH="$(printf '%s' "$PATH" | tr ':' '\n' | grep -vFx "$CODEX_DIR" | paste -sd: -)"
env PATH="$NOCODEX_PATH" sh -c 'command -v codex' && echo "STILL VISIBLE — fix PATH" && exit 1
env PATH="$NOCODEX_PATH" python3 -m pytest tests/test_review_stage.py -q \
  > .build/ac7/baseline.txt 2>&1; tail -3 .build/ac7/baseline.txt
```

Also capture a plan-level baseline, since the test summary alone will not show
which providers were selected. Use `--plan-only` (`:2246`, consumed at `:2310`):
it emits `status: "planned"` with the full `target` and `plan` and executes no
provider, so the baseline is deterministic, free, and offline.

`--attempt-id` is **required** (`:2240`). `--scope` takes
`changes|branch|codebase|pr` (`SCOPES`, `:51`) — not the internal target scopes:

```bash
env PATH="$NOCODEX_PATH" python3 templates/scripts/sd-ai-command-pack-review-local.py \
  --repo . --scope changes --base main --attempt-id ac7-before --plan-only --json \
  > .build/ac7/plan-before.json
```

Repeat for `--scope branch` and `--scope codebase`; low-risk and
substantive-risk paths select differently and a single scope proves only one of
them. `tests/test_review_stage.py:204-229` shows the same invocation shape.

**Two scope vocabularies exist and must not be conflated.** The CLI takes
`changes|branch|codebase|pr` (`:51`). The provider `scopes` field and
`target["scope"]` — what `:1211-1215` filters on and what `_expand_argv` branches
on — take `worktree|branch_delta|codebase` (see any provider entry in
`review.py:220`). The design's scope-prompt table is written against the
*internal* vocabulary, which is correct for the adapter; using the CLI
vocabulary there would silently match nothing.

Then observe the exit codes the adapter must map — the design deliberately
refuses to assume them.

Run the probes from a scratch directory that is **not** a git repository, and
tell `codex` so explicitly. `codex exec` refuses to run outside a git repo
unless `--skip-git-repo-check` is given, and `-C` is how the adapter itself
binds its working root — a probe run by `cd`-ing somewhere and omitting both
measures a different code path from the one being mapped, and on a machine where
`/tmp` happens to sit inside a repository it measures nothing at all.

```bash
probe="$(mktemp -d)"
codex exec -s read-only --ephemeral -C "$probe" --skip-git-repo-check \
  -o "$probe/out.json" "reply with {}"; echo "exit=$?"
codex exec -s read-only --ephemeral -C "$probe" --skip-git-repo-check \
  -o "$probe/out.json" --output-schema "$probe/missing.json" "x"; echo "exit=$?"
codex exec -s read-only --ephemeral -C "$probe/does-not-exist" \
  --skip-git-repo-check -o "$probe/out.json" "x"; echo "exit=$?"
```

Write the observed codes into `design.md`'s exit-code section before writing the
mapping. Map only codes actually observed — `outcomeByExitCode` is capped at 32
entries (`review-local.py:450-452`), and anything unmapped falls through to
**`failed`**, which is the hardcoded default at `:1716` and is not
configurable. Do not attempt to make the fallback `unavailable`; `failed`
already satisfies the requirement that no unmapped code become `clean` or
`findings`.

## Step 1 — the eligibility gate (do this first)

This is the change that prevents a regression, so it lands before the provider
that depends on it.

- [ ] Add a module-level **adapter → required executable** map, e.g.
  `ADAPTER_EXECUTABLES = {"codex": "codex"}`. `prism`, `gito`, and `argv` are
  absent and therefore unconstrained.
- [ ] `templates/scripts/sd-ai-command-pack-review-local.py:1211-1215` — extend
  the `eligible` comprehension: a provider whose adapter appears in that map is
  eligible only when `shutil.which(ADAPTER_EXECUTABLES[provider.adapter])` is
  not `None`.

Do **not** try to derive the executable from `argv[0]` the way `_run_provider`
does at `:1677`. At `:1211` planning has not run `_expand_argv`, and a builtin
provider's configured `argv` is `[]` (`:402`). `build_tool_environment` is also
not called until `:2077`, after selection, so no provider environment exists at
gate time either.

- [ ] Add a test asserting the gate and the runtime resolve the same
  executable — `shutil.which("codex")` and
  `shutil.which("codex", path=build_tool_environment(repo=repo)[0]["PATH"])`
  must agree. They do today because `build_tool_environment`
  (`sd_ai_command_pack_lib.py:402`) copies `os.environ` and overrides only
  `CACHE_ENV_KEYS` and `GIT_TERMINAL_PROMPT`, never `PATH`. The test is what
  keeps that true; without it, a future `PATH` sanitization reintroduces the
  regression silently — gate passes, runtime reports `unavailable`.

Validation:

```bash
env PATH="$NOCODEX_PATH" python3 -m pytest tests/test_review_stage.py -q 2>&1 | tail -3
```

Must match `.build/ac7/baseline.txt`. At this point no codex provider exists
yet, so this step must be a no-op — including the digests, since
`_default_config()` is unchanged. This is the one step where byte equality *is*
the right assertion; from Step 3 onward it is not.

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

- [ ] Factor the validation body of `_parse_argv_payload` (`:1515-1522`) into a
  helper that takes an **already-parsed object** and returns `dict | None`.
  `_parse_argv_payload` keeps its `(stdout: bytes)` signature (`:1515`) and
  calls the helper after decoding.
- [ ] `_parse_provider_payload` (`:1612-1616`) — add the `codex` branch reading
  `attempt_dir/codex-review.json` via `_read_json(..., limit=MAX_OUTPUT_BYTES,
  ...)`, then pass that result to the new helper.

Do **not** call `_parse_argv_payload` on the `_read_json` result. `_read_json`
is `(path, *, limit, label) -> object` (`:358`) and `_parse_argv_payload` is
`(stdout: bytes) -> dict | None` (`:1515`) — codex writes a file, not stdout, so
the two do not compose. Copying the validation instead of extracting it gives
two rules that drift.

- [ ] Return `None` on malformed or missing output. Never synthesize
  `status: "clean"`.

Validation:

```bash
python3 -m pytest tests/test_review_local.py -q -k "argv" 2>&1 | tail -3
```

The existing `argv` payload tests must still pass unchanged — they are the proof
that extracting the helper did not alter the shared rule.

## Step 6 — the bounded ensemble

`policy` is validated against a closed key set, so this is four edits, not one.
Doing only the last makes every configuration carrying the key a hard input
error.

- [ ] `review-local.py:149` — add `"ensembleProviders"` to `POLICY_KEYS`.
  Without this, `set(policy) - POLICY_KEYS` at `:507` raises
  `"review policy must use only supported fields"`.
- [ ] `review-local.py:519-530` — parse it with `_string_list`, reject members
  that are not configured provider ids the way `requiredProviders` does, and
  emit it into `normalized_policy` **defaulting to
  `["codex", "gito", "prism"]` when absent**. The default belongs here, not in
  `_default_config()`: a repository with its own `.sd-ai-command-pack/review.json`
  never sees `_default_config()`, and a missing default would give it an empty
  ensemble and a silently skipped substantive review.
- [ ] `review-local.py:_default_config()` — include the key explicitly so the
  shipped default is readable rather than implicit.
- [ ] `review-local.py:1257-1263` — remove the `{"prism", "gito"}` literal and
  filter `eligible` by membership in `policy["ensembleProviders"]`.

A member naming an undefined provider is an input error; a member naming a
defined-but-ineligible provider is simply filtered out — that is what makes the
`codex` entry harmless without the CLI.

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

Then prove the back-compat path:

```bash
python3 -m pytest tests/test_review_local.py tests/test_review_stage.py -q 2>&1 | tail -3
```

Add a case feeding a config whose `policy` omits `ensembleProviders` and assert
the normalized policy comes back with all three ids — an empty ensemble is the
failure mode this step exists to prevent, and it fails silently.

## Step 7 — the shell entrypoint

The shell has per-tool state and dispatch, not a generic loop. An unrecognized
token reaches the `*)` branch, warns
`"No command configured for local review tool '<name>'"`, and sets
`OVERALL_STATUS=2` — so changing the default list alone would make the default
set fail immediately.

Seven sites, plus the runner. Enumerate; do not work from `--help`:

- [ ] `list_tools()` — the hardcoded `printf` block behind `--list-tools`. It is
  a separate function from `usage()`, so "update `--help`" misses it.
- [ ] `:196-197` — the `usage()` heredoc tool table and the `all`/`default`
  alias descriptions.
- [ ] `:643` — `raw_tools="${SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS:-prism gito}"`.
- [ ] `:702-703` — add `NEED_CODEX=0` beside `NEED_PRISM` / `NEED_GITO`.
- [ ] `:717-718` — the `all|default` alias branch sets `NEED_CODEX=1`.
- [ ] `:732`, `:735` — add a `codex)` arm to the per-tool `case`.
- [ ] `:753`, `:757` — add the `if [ "$NEED_CODEX" -eq 1 ]` execution guard.
- [ ] Add `run_codex_review` alongside `run_prism_reviews` / `run_gito_review`.

**Do not move the custom-command lookup.** `configured_command_for_tool` is
consulted at `:723-728`, *before* the builtin `case`. A consumer already running
Codex via `SD_AI_COMMAND_PACK_REVIEW_LOCAL_CODEX_COMMAND` keeps that override
only because the custom branch still wins. Reordering silently breaks them.

Validation — invoke it with a stub. The **shell** entrypoint has no
`--plan-only`; its parser accepts only `--all`, `--codebase`, `--full`,
`--full-codebase`, `--help`/`-h`, `--list-tools`, `--diff`/`--changed`,
`--scope[=]`, and `--`. (`--plan-only` does exist, but on the *Python* stage
script at `review-local.py:2246` — that is the flag Step 0 uses. Do not carry it
across to the shell.)

```bash
stub="$(mktemp -d)"
printf '#!/bin/sh\necho STUB-CODEX-RAN >&2\nexit 0\n' > "$stub/codex"
chmod +x "$stub/codex"
env PATH="$stub:$PATH" bash templates/scripts/sd-ai-command-pack-review-local.sh codex \
  2>&1 | tee "$stub/log"; echo "exit=$?"
grep -q 'STUB-CODEX-RAN' "$stub/log" || echo 'FAIL: codex was never invoked'
grep -q "No command configured for local review tool 'codex'" "$stub/log" \
  && echo 'FAIL: still hitting the unconfigured-tool branch'
bash templates/scripts/sd-ai-command-pack-review-local.sh --list-tools | grep -qx codex \
  || echo 'FAIL: --list-tools omits codex'
```

The `--list-tools` check is necessary but not sufficient on its own: that
function is a hardcoded `printf` independent of dispatch and can be right while
dispatch is missing. The stub invocation is the load-bearing check.

## Step 8 — tests

- [ ] AC5: stub `codex` on `PATH`, low-risk worktree review → `codex` runs,
  `prism` and `gito` do not. Follow the stub-binary pattern at
  `tests/test_review_local.py:167-193`.
- [ ] AC6: stub `codex`, substantive-risk review → `codex` **and** the metered
  providers run.
- [ ] AC7: no `codex` on `PATH` → rerun the Step 0 commands with the same
  `NOCODEX_PATH` and compare against `.build/ac7/`.

  Compare **behavior**, and exclude the three identity fields that necessarily
  change (`configurationDigest`, `policyDigest`, `receiptId`) — a raw diff fails
  on them for the wrong reason and invites loosening the assertion until it
  passes:

  ```bash
  jq -S 'del(.configurationDigest,.policyDigest,.receiptId)
         | {providers: .providers, policyId: .policyId, outcome: .outcome}' \
    .build/ac7/receipt-before.json > .build/ac7/before.norm
  jq -S 'del(.configurationDigest,.policyDigest,.receiptId)
         | {providers: .providers, policyId: .policyId, outcome: .outcome}' \
    .build/ac7/receipt-after.json > .build/ac7/after.norm
  diff .build/ac7/before.norm .build/ac7/after.norm && echo "AC7 behavior identical"
  ```

  Then assert the identity change is real and well-formed, so it is proven
  intentional rather than assumed absent:

  ```bash
  jq -r .configurationDigest .build/ac7/receipt-before.json > .build/ac7/d1
  jq -r .configurationDigest .build/ac7/receipt-after.json  > .build/ac7/d2
  ! diff -q .build/ac7/d1 .build/ac7/d2 && grep -Eqx '[0-9a-f]{64}' .build/ac7/d2 \
    && echo "configurationDigest changed once, still 64-hex"
  ```

  Adjust the `jq` paths to the receipt's actual shape. The rule, not the
  expression, is the requirement: provider list, policy id, and outcome
  identical; digests different.
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
- [ ] `templates/docs/SD_AI_COMMAND_PACK.md:862-878` — the current-diff native
  peer-lane paragraphs, and `:1821-1826` under the `### Local Review` heading at
  `:1819`. Note `:1819` is the heading itself, not prose to edit.
- [ ] `templates/.agents/skills/sd-review/SKILL.md` — does not currently mention
  Codex, so this is an addition: the provider lane, and the Claude-native
  pre-push lane. State explicitly that native-lane results do **not** reach the
  router; the coordinator builds router evidence only from its own local receipt
  (`review.py:1839`, `:1941`).
- [ ] State that a repository with its own `.sd-ai-command-pack/review.json`
  does not inherit the new default and must add the provider itself.

Out of scope — do not edit. The `grep -rln` returns 16 files; twelve are noise
and are listed here so an implementer does not have to re-derive the
classification and does not mistake silence for oversight:

Planning-adversarial-review lane (a different feature):

- `templates/docs/SD_AI_COMMAND_PACK.md:32-35` and the whole
  `### Planning Artifact Review` section at `:1798-1817`.
- `templates/.claude/rules/sd-planning-adversarial-review.md`
- `templates/.claude/sd-ai-command-pack/planning-adversarial-review.md`

Unrelated — `codex/<slug>` branch names or `.codex/` platform-directory paths:

- `templates/.agents/skills/sd-create-pr/SKILL.md:63-64`, `:144`
- `templates/.agents/skills/sd-full-check/SKILL.md`
- `templates/.github/copilot-instructions.sd-ai-command-pack.md`
- `templates/.gito/config.toml:12`
- `templates/scripts/sd-ai-command-pack-review-scope.sh:103`
- `templates/scripts/sd-ai-command-pack-shell-lib.sh:15`
- `templates/scripts/sd-ai-command-pack-review-preflight.mjs:274`, `:4255`,
  `:4306`
- `templates/scripts/sd-ai-command-pack-install-audit.py:239`
- `templates/scripts/sd-ai-command-pack-audit-route.py:152`
- `templates/scripts/sd-ai-command-pack-update-spec-kb.py:90`, `:913`, `:916`
- `templates/docs/SD_AI_COMMAND_PACK.md:1951`, `:1955`, `:2134-2137`, `:2162`,
  `:2240`

Re-run the enumeration rather than trusting this list — it is a snapshot, and
the point of AC9 is that the list is derived, not remembered.

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
  It requires an actual diff against the `.build/ac7/` baseline captured in
  Step 0. If Step 0's baseline was never captured, AC7 cannot be claimed. It is
  also the one most likely to be *mis*-reported: the pass condition is behavioral
  equality with a deliberate digest change, not byte equality. A report claiming
  "no change at all" is wrong on its face.
- AC4 (no surviving literal) and AC8 (shell actually dispatches) both require
  running a command, not reading a file. For AC8 specifically, `--list-tools`
  output is not evidence of dispatch.
- Step 0's observed exit codes must appear in the committed mapping. If they
  were never observed, say so rather than shipping assumed values. Unmapped
  codes become `failed` (`:1716`), which is intended.
- Step 6 must be checked for the empty-ensemble failure: a config omitting
  `policy.ensembleProviders` must normalize to all three ids. That failure is
  silent — substantive review simply runs nothing.
