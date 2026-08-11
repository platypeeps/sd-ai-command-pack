# Design — repoint surviving pack surfaces off removed paths

## The shape the PRD did not have yet

An earlier revision of the PRD named `templates/.github/prompts/**` as a
canonical source. It is not, and the PRD's Evidence section now records
the correction. All four prompts are **generated**:
`.github/command-sources/sd-<name>.md` holds one neutral body, and
`.github/scripts/generate-command-surfaces.py` reads it at `:429` and
fans it out to every platform adapter at `:652`. Editing the prompt
template directly is overwritten by `make generate`. The canonical source
is the command-source file.

(`check-command-surface-drift.py` is *not* the guard here: it enumerates
required paths and checks existence at `:624`, not content drift. An
earlier revision of this design cited it as a content check.)

That reframes the whole task. There is no per-prompt repointing to do —
there is one neutral sentence per command, and a question about which
adapters get which resolution arms.

## What already works, and why exactly one arm is broken

Three delivery locations exist. Each adapter reaches exactly one, and two
of the three are already correct because a payload builder rewrites them
(`installer/references.py`):

| Adapter | Cites | Rewritten by |
|---|---|---|
| Claude Code plugin (`plugins/sd/commands/`) | `sd-ai-command-pack-housekeeping.sh` (bare, on the Bash tool PATH) | `PLUGIN_PROFILE`, `script_template="{name}"` |
| machine payload (`plugins/sd/machine-payload/.opencode/`) | `~/.agents/bin/sd-ai-command-pack-housekeeping.sh` | `MACHINE_PROFILE` |
| repo-native (`.github/prompts/`, `.claude/commands/`, `.opencode/`) | `scripts/sd-ai-command-pack-housekeeping.sh` | nobody — installed verbatim |

Verified by grepping one shared sentence across all three trees. The
third row is the defect, and it is the defect *because* it is the only
row no rewrite touches: `repo-native` files stay in the consumer
repository, so nothing ever relocates their references, and a thin
conversion then deletes what they name.

## D1 — Arms are generated per platform, not authored once

The obvious fix — write all three arms into the neutral body — is wrong,
and quietly so. `SCRIPT_REFERENCE_RE` rewrites any `scripts/<name>`
occurrence inside the machine payload, so a hand-authored sentence
listing both `~/.agents/bin/<name>` and `scripts/<name>` becomes a
machine-payload sentence naming `~/.agents/bin/<name>` twice.
`check_text_residue` passes — there is no residue — and the text is
nonsense. A gate that is satisfied by broken output is the failure mode
this repo keeps finding, so the design does not create another one.

## D1 superseded — measured 2026-08-11, at implementation start

Everything below in this section described adding resolution *arms* to
the repo-native text. Measurement against `cites_removed_path` refutes
the premise: **the scanner classifies tokens, not reachability.** A
sentence that offers `~/.agents/bin/<name>` and `scripts/<name>` still
contains the `scripts/<name>` token, so the surface still reports a
`packDefect`. Arms satisfy requirement 1 and fail acceptance criterion 3.

Measured vocabulary (synthetic removed-set, real rule shapes):

| Form | Verdict |
|---|---|
| `~/.agents/bin/<script>`, `~/.agents/bin` | ok |
| `~/.agents/docs`, `~/.agents/skills`, `~/.agents/skills/sd-*/SKILL.md` | ok |
| `scripts/<name>`, bare `<name>` | HIT |
| `docs/SD_AI_COMMAND_PACK.md`, bare `SD_AI_COMMAND_PACK.md` | HIT |
| `~/.agents/docs/SD_AI_COMMAND_PACK.md` | HIT |
| `.agents/skills/sd-*/SKILL.md`, `**/skills/sd-*/**`, `scripts/sd-ai-command-pack-*` | HIT |

The last two rows matter most. `thin-resweep.py:1225` matches **path
suffixes** — `any("/".join(parts[index:]) in removed ...)` — so
`~/.agents/docs/SD_AI_COMMAND_PACK.md` ends with the removed
`docs/SD_AI_COMMAND_PACK.md` and is flagged. The machine payload's own
`AGENTS_DOC_REFERENCE` has exactly that shape; it is latent there only
because payload files are not scanned. A thin variant cannot reuse it.

**Chosen (user, 2026-08-11): a third `RewriteProfile`, applied to
surviving repo-native text at conversion time.** Same machinery that
already serves the plugin and machine payloads, so the authored source
stays canonical and the fat tree is untouched — zero churn for the eight
consumers that exist today.

```python
THIN_PROFILE = RewriteProfile(
    name="thin",
    script_template=f"{AGENTS_BIN_REFERENCE}/{{name}}",
    doc_template="the pack reference manual under `~/.agents/docs`",
    ...
)
```

`doc_template` deliberately diverges from `MACHINE_PROFILE`'s: it must
not end in `docs/<file>`, per the suffix rule above.

Two limits this profile does not cover, handled separately:

- The three Copilot **globs** are not matched by `SCRIPT_REFERENCE_RE`
  (`_PACK_SCRIPT_NAME` requires a real `.py`/`.sh`/`.mjs` extension, and
  `scripts/sd-ai-command-pack-*` has none). They keep the mode-aware
  managed-block treatment decided in D2.
- The PR template is force-preserved, so conversion-time rewriting
  reaches only fresh installs — unchanged from D4.

The superseded reasoning is kept below because it is still the correct
account of *why the arms idea was tempting*, and the payload-input
collision it documents remains true and still constrains the profile.

---

A first draft of this design said "generator emits the clause per
platform, plugin and machine untouched." That is wrong, and the reason is
worth writing down because it is not visible from the generator alone:
**the repo-native templates are the input to both payload builders.**
`generate-plugin.py:440` does `body = rewrite_markdown(text)` and
`machinestage.py:169` does
`body = rewrite_text(text, profile=MACHINE_PROFILE, key=target)`, each
reading a `templates/` command file. So a two-arm clause authored into a
repo-native template does not stay there: the machine payload rewrites
its `scripts/` arm and ends up naming `~/.agents/bin/<name>` twice, and
the plugin — which strips to a bare command — inherits a `~/.agents/bin`
arm naming a location the plugin does not install. Widening the
repo-native text silently widens both payloads.

**Chosen:** the resolution clause is a **profile-parameterized atomic
replacement**, not prose that a regex later edits. Add the clause text to
`RewriteProfile` in `installer/references.py` and replace the whole
authored clause per profile, rather than substituting the path token
inside it:

| Profile | Clause |
|---|---|
| plugin | bare command on `PATH` |
| machine | `~/.agents/bin/<name>` |
| repo-native (no rewrite) | `PATH`, then `~/.agents/bin/<name>`, then `scripts/<name>` |

The authored template carries the repo-native form, because that is the
form that must survive unrewritten. Each payload builder swaps the whole
clause for its own, so no payload ever contains an arm assembled from
another profile's text. Arm order for repo-native is PATH, then
`~/.agents/bin`, then `scripts/`: a thin consumer hits a real location on
arm two, a fat consumer on arm three, and neither is asked which mode it
is in.

The replacement must be anchored on a unique sentence and fail loudly
when the anchor is missing or ambiguous — the same discipline
`CLAUDE_COMMAND_BODY_INSERTIONS` already enforces with its
`body.count(anchor) != 1` check. A silent no-op here reintroduces exactly
the bug this section exists to prevent.

**But that assertion has to be target-scoped, and one caller cannot scope
it yet.** `rewrite_text()` runs over every text file in a payload
(`machinestage.py:140`, `generate-plugin.py:419`), not just these four
commands, so an unconditional "anchor must appear exactly once" rejects
every unrelated file. The clause map is therefore keyed by target, and
exactly-one is enforced only for targets in that map. The machine caller
already threads a key (`machinestage.py:169`,
`rewrite_text(..., key=target)`); the plugin caller does not —
`rewrite_markdown(text)` at `generate-plugin.py:307` takes text alone.
Threading the target key through the plugin path is part of this task,
not an assumption it can make.

**Rejected — mode detection on the pin receipt.** Requirement 2 does not
forbid it — it only requires the verify-then-run shape to survive — so
this is a design judgement rather than a PRD constraint. It adds a file
read to every prompt before the verify step, and a prompt that detects a
mode can detect it wrong. An ordered
resolution list cannot: every arm names a location that really exists in
some real deployment, and the first hit wins.

## D2 — The two globs fail a different rule and need a different fix

`sd-ai-command-pack-thin-resweep.py:1176`: *"A glob is only broken when
nothing it selects survives."* Both Copilot globs
(`.agents/skills/sd-*/SKILL.md`, `**/skills/sd-*/**`) select the
`.agents` skills population. Today's conversions delete that population
entirely — `retainVendoredFor` retains `codex`/`pi` rows only for a
consumer declaring those platforms, and no registered consumer does — so
nothing survives and both are genuine defects.

The consequence the PRD already flagged: a glob is not fixed by aiming it
at another absent directory. What clears it is a survivor. So the managed
block has to say where pack skills actually live in a thin checkout.

**Decided (user, 2026-08-11): a mode-aware managed block, chosen at
install time.** The installer emits a thin variant and a fat variant and
picks between them; it already rewrites this block on every refresh, and
it already knows which mode it is installing. This is the PRD's explicit
"or it detects the mode and branches explicitly" arm, with the detection
done by the installer rather than by an agent guessing at runtime.

The thin variant states that the repository vendors no pack files, and
that pack skills run from the Claude Code plugin and `~/.agents/skills`,
neither of which is in the repository — so no diff path is pack-owned.
The fat variant is unchanged and keeps all three globs.

Two options were rejected. Pointing the globs at
`~/.agents/skills/sd-*/SKILL.md` clears the resweep, but the block
classifies paths appearing in *this repository's* diffs, so naming a path
outside the repository makes the check pass without making the statement
true. Dropping the globs entirely is the simplest text change, but all
eight consumers run fat today, where the globs are accurate and useful —
that trades correct classification for every consumer that exists against
a mode none of them are in yet.

This widens the task beyond a text change: it needs an installer branch
and a test per variant. That is the cost of the only option under which
both a thin and a fat consumer read something true.

All edits stay between `SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:START` and
`:END`. Outside those markers is consumer content.

## D3 — `.gitignore`: change the provenance comment, not the allowlist

The hit is emitted at
`templates/scripts/sd-ai-command-pack-update-spec-kb.py:442`, the header
comment of the `obsidian-kb` block. The replacement names the **pack**,
carrying no script path and no script basename:

```
# Generated by sd-ai-command-pack. DO NOT EDIT MANUALLY.
```

It does clear the resweep, but **not** for the reason a first draft of
this design gave. That draft claimed the line yields no path token at
all; it does — `TOKEN` (`thin-resweep.py:469`) extracts
`sd-ai-command-pack.` and `MANUALLY.`. What matters is that both
classify `False` against every registered consumer: neither is a removed
path, and neither is an unambiguous basename of one, so the rule at
`:1231` does not fire.

The distinction is worth keeping because the two explanations fail
differently. "No token" would stay true no matter what the delete set
becomes; "token that classifies False" is a fact about today's delete
set, and a future conversion that removed something named
`sd-ai-command-pack` would break it. The literal is safe; the reason it
is safe is narrower than it looks.

`BIN_LITERAL_ALLOWLIST["sd-ai-command-pack-update-spec-kb.py"]` stays
exactly as it is. Line 1116 still writes the repository path into the
`.obsidian-kb/` file banner, so the allowlisted literal is still present
and still justified — and `.obsidian-kb/` is gitignored, so the resweep
never reads it. Two emissions, one literal, only one of them tracked.

**Verified, and the first proposal fails.** `thin-resweep.py:1231` ends
token classification with
`return "/" not in token and token in unambiguous`: a bare, unambiguous
basename of a removed file is classified removed exactly like the full
path. Dropping the `scripts/` prefix therefore changes nothing, and pack
ownership makes it a `packDefect` regardless of command position
(`thin-resweep.py:1592`).

So the comment names the block's **owner**, not its generator — the pack,
by name, with no script reference at all. Provenance survives; the path
claim and the basename claim both go.

The route to zero is the one the PRD already establishes: this block is
rewritten only when the KB script *runs*, so shipping the fix is not
enough and the conversion PRs carry an explicit KB-refresh step.

## D4 — PR template: ship it, and bound the claim

Per PRD 2c, unchanged. Recording the mechanism so the bound is checkable:
`install_file()` returns `PRESERVED` for a force-preserved target whenever
existing bytes differ from the shipped bytes, and does so even under
`force=True` (`installer/fileops.py:366`). The moment the shipped
template changes, all existing copies differ and are preserved
permanently. The fix reaches fresh installs only; the eight repositories
that exist today are consumer-side work in children 3–5.

## D5 — Mirror and release flow

Edit templates and command sources first, then `make sync` and
`make generate`. `scripts/`, `plugins/sd/bin/`, and
`plugins/sd/machine-payload/scripts/` are byte-verified mirrors and are
never hand-edited. This is a shipped-payload change, so it needs a
`manifest.json` bump and a matching top `CHANGELOG.md` heading or the
release gate fails.

## D6 — The rewrite is the payload's content, not an edit after the write

**Measured 2026-08-11, during implementation. Supersedes D2's install-time
managed-block branch and D4's template edit, and completes D1's
`THIN_PROFILE`.** Both earlier decisions were about *which text to ship*.
The measurement moved the question to *where the text is decided*.

`THIN_PROFILE` was first applied as a post-write pass at the end of the
conversion (`thin.repoint_kept_references`). Built as a fixture and run:

| step | before D6 | after D6 |
|---|---|---|
| conversion | rc 0 | rc 0 |
| `install.py --check` | **`state: invalid`** | `state: current` |
| — reason | "vouched target content drifted" ×4 | — |
| refresh | **rc 2** (conflicts) | rc 0 |
| repoint survives refresh | n/a — refresh refused | yes |

Two independent causes, both structural rather than incidental:

1. `.github/copilot-instructions.md` and 550 other rows are `repo-native`
   (`docs/fleet/surface-partition.json`), so they are inside the residual
   slice a thin refresh reinstalls (`install.py:792`). Anything written
   after the install is overwritten by the next one.
2. Provenance records `result.source_digest`, which is the digest of the
   bytes the installer decided to write (`provenance.py:183`). Editing the
   file afterwards desynchronizes the receipt from the disk, and the
   inspection reports exactly that.

So the seam is `payload_source_bytes()` in `installer/fileops.py`: the one
point where a target's content is decided. `source_digest` hashes its
return value, provenance records that hash, and the bytes on disk are it —
three facts from one value instead of three that must be kept in step. The
same flag reaches `normalize_managed_block_template()`, which is why the
Copilot block needs no second authored variant: `is_thin` false is the
untouched path, so the fat emission is byte-identical by construction
rather than by review.

The conversion keeps its repoint, for the window the installer does not
cover: a conversion does not reinstall, so without it a converted consumer
carries the fat text until someone refreshes. It now writes only what
`planned_repoints()` decided *before* the receipts, and the receipt takes
those digests through `repointed_provenance_files()` — most repo-native
targets fall outside the residual payload, so their provenance entries are
carried forward from the fat receipt rather than recomputed, and the
overlay is what stops a freshly converted consumer reporting every
repointed file as drifted.

D4 needs no template edit at all: both PR-template lines are ordinary path
citations, so the profile rewrites them like any other. The line that does
still need authoring is D3's, because that block is written by *running*
the KB script rather than by installing a template — the profile never
sees it. Its cost, measured: changing the banner rewrites the generated
`.gitignore` block on every consumer's next KB refresh, which dirties the
tree once. `.gitignore` is a real defect row (1 hit per consumer in the
baseline), so the change is required, not optional.

## Verification strategy

The acceptance signal is a measurement, not a diff reading. Baseline,
re-measured 2026-08-11 with the current detector: **17 hits in 8 files**
for the five consumers carrying the pack's PR template, **15 in 7** for
the three that own theirs. The eighth file is the `codex` row owned by
`08-11-thin-undeclared-codex-marker`; this task's ceiling is therefore
one remaining defect, not zero, until that task lands.

**Measured 2026-08-11, per surface, against the shipped classifier**
(`cites_removed_path` from `scripts/sd-ai-command-pack-thin-resweep.py`,
with `removed`/`survivors` taken from a real converted fixture rather than
a hand-written list):

| surface | fat | thin |
|---|---|---|
| `.github/copilot-instructions.md` | 7 | 0 |
| `.github/PULL_REQUEST_TEMPLATE.md` | 2 | 0 |
| `.github/prompts/sd-housekeeping.prompt.md` | 3 | 0 |
| `.github/prompts/sd-review-learnings.prompt.md` | 2 | 0 |
| `.github/prompts/sd-review.prompt.md` | 2 | 0 |
| `.github/prompts/sd-status.prompt.md` | 1 | 0 |
| `.gitignore` | 0 | 0 |
| **total** | **17** | **0** |

Fat keeps citing the vendored paths, which is correct there — they exist
in a fat checkout, and breaking fat to fix thin trades one outage for
another. `.gitignore` reads 0 in both columns because D3's banner change
fixes it in both layouts rather than only after conversion.

The negative case is load-bearing and gets its own run — refreshed but
*not* KB-refreshed still reports the `obsidian-kb` hit, or the extra
conversion step is ceremonial and the PRD's central claim is wrong. That
one is consumer-side and belongs to children 3–5; nothing in this
repository can measure it.
