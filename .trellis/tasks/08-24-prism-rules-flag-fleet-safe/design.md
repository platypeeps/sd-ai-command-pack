# Design — prism rules flag, made fleet-safe

## Shape of the change

One new pure function in `sd-ai-command-pack-review-local.py`, one extra
parameter threaded to `_expand_argv`, one extra key in two artifacts, and a
fleet edit across ten repositories that must land first.

## Ordering

**Revised 2026-08-24, at the start of implementation.** The original plan made
the fleet edit a standalone prerequisite that ran before any pack change. That
is not possible: `.prism/rules.schema.json` lists `severityOverrides` in
`required`, and the schema is `install: always`, so it reaches a consumer only
through a pack release. Stripping the key first would leave every repository
holding a file invalid against the schema sitting next to it — which is exactly
the state `sd-github-review` has been in, unobserved, since 2026-08-24.

So the pack moves first:

1. **Pack templates** (implement Phase 0): schema drops `severityOverrides`
   from `required`; the `templates/.prism/rules.json` block goes.
2. **Pack change and tests** (Phases 1–2): `--rules`, the guard, the receipt
   record.
3. **Release and rollout** (Phase 3): the new schema reaches consumers because
   it is `install: always`. Receipts read `rules.status == "refused"` here, and
   that is the expected value — every consumer still carries the block.
4. **Fleet** (Phase 4): strip the block from ten `rules.json` files and amend
   the `description` sentence that references it. Durable, because `rules.json`
   is `install: if-not-exists`.
5. **Verify live** (Phase 5).

The guard is what makes this order safe. Between steps 1 and 3 every consumer
still carries `severityOverrides`, so the pack refuses to pass `--rules` and
each repository keeps exactly today's behaviour until its own file is cleaned.
The window is not a regression window; it is a no-change window. That property
was the guard's original justification and it is now also the sequencing
argument.

The guard does not only enable the ordering, it survives it. If the fleet edit
misses a repository — or one is added later from a copied
template — the guard degrades that repository to today's behaviour rather than
to the broken one. Guard and fleet edit are belt and braces on purpose; the
fleet has already shown that these files propagate by copying: the `focus`
array is byte-identical across all eleven, and the files vary only in `required`
and, in two of them, `description`. That is what copy-then-edit looks like.

## Rules resolution

```
_prism_rules(repo: Path) -> RulesDecision
```

`RulesDecision` carries `argv_extension: list[str]` and `record: dict`. Four
outcomes, all of them recorded, none of them fatal:

| condition | argv extension | `record["status"]` |
| --- | --- | --- |
| file absent | `[]` | `absent` |
| unreadable / not JSON / not an object | `[]` | `unreadable` |
| object contains `severityOverrides` | `[]` | `refused` |
| otherwise | `["--rules", ".prism/rules.json"]` | `applied` |

The `refused` and `unreadable` records carry a `reason` naming the file and, for
`refused`, the key. A review that runs without rules is exactly today's
behaviour, so no outcome here fails the review — degrading to the status quo is
always available and always better than not reviewing.

The path stays **relative**. `_run_provider` sets `cwd=repo` on the
`subprocess.Popen` call (`sd-ai-command-pack-review-local.py:1736`), so prism resolves
`.prism/rules.json` against the repository under review. A relative path also
keeps the argv stable across machines, which matters because the argv is
persisted into `invocation.json` and compared for receipt reuse.

Size limit on the read: the file is consumer-controlled input parsed by the
pack, so it goes through the existing `_read_json(..., limit=…)` helper rather
than a bare `json.load`.

## Threading

`_expand_argv` already receives `repo`, but it must not do the file read itself:
it is called once per provider inside a dict comprehension
(`sd-ai-command-pack-review-local.py:2231`), and the decision has to reach
`_run_provider` too. So the decision is computed once at the call site and
passed in.

- `_expand_argv(provider, target, attempt_dir, context_path, repo, rules)` —
  appends `rules.argv_extension` to the three `adapter == "prism"` branches
  only. `gito` and `argv` are untouched; the `argv` adapter already has
  `{repo}` available and any consumer wanting rules there passes them itself,
  which is what `sd-github-review`'s `prism-chunked` provider does today.
- `_run_provider(..., rules=rules.record)` — merges the record into the attempt
  base dict as `"rules"`, so it lands in `attempt.json` beside `provider` and
  `diagnostic`.

Computed once per run, not once per provider: the decision depends only on
`repo`.

## Observability

Two artifacts, deliberately:

- `invocation.json` already persists the full `plan` argv, so `--rules` presence
  is visible there the moment it is passed. That covers "were rules applied".
- `attempt.json` gains `rules`, which covers "and if not, why". This is the half
  that was missing: nothing in a receipt today distinguishes *no rules file*
  from *rules file silently ignored*, and that indistinguishability is precisely
  why the defect survived unnoticed across eleven repositories.

No receipt schema exists to version, and no consumer reads `attempt.json`
positionally, so an added key is additive.

## Mirrors

`plugins/sd/bin/` and `plugins/sd/machine-payload/scripts/` are byte-identical.
Edit one, sync the other in the same commit, and let `pack.install-audit`
confirm it. This is mechanical and has bitten before; it is a checklist item in
`implement.md`, not a design question.

## The two pack-managed files, and why they differ

`manifest.json` gives `.prism/rules.json` `install: if-not-exists` and
`.prism/rules.schema.json` `install: always`. That asymmetry is correct and the
plan depends on it: the rules file is consumer policy and must survive updates,
the schema is pack contract and must not drift. It also means the two halves of
this change have to travel by different routes — the schema centrally, the rules
files one repository at a time — and neither route can carry the other.

`templates/.prism/rules.json` seeds new installs and still contains the
identical block. Fixing it is not optional cleanup: it is the difference between
this task closing and this task closing until the next repository is created.

## The fleet edit

Ten repositories, one key removed from one file each. Mechanically trivial, and
the risk is entirely in it being *incomplete* rather than in it being wrong. The
acceptance check therefore enumerates from the filesystem —
`~/repos/*/*/.prism/rules.json` — rather than from the table in `prd.md`. A
check built from the list I already have cannot find the repository I did not
know about.

Each edit is a commit in its own repository. Nine of the ten have their own
review gates, and this change makes those gates *less* likely to block, so the
sequencing is safe in either direction per-repository.

## Proving the rules actually loaded

`BuildRulesPromptSection` (`prism internal/review/rules.go:52`) renders `focus`
and `required` into the prompt, so the plumbing exists. Observing it from the
outside is the hard part, and the obvious check does not work.

**The category set proves nothing.** `prism internal/review/prompt.go:28`
hardcodes `bug, security, performance, correctness, style, maintainability,
testing, docs` into every prompt regardless of rules, and every consumer's
`focus` array is that exact list. "All findings' categories fall inside `focus`"
is therefore true of every prism run ever made, with or without a rules file.
The consumer-side write-up in `sd-github-review` originally offered this as
evidence and has been corrected.

**A/B against the same diff does not work either**, for two reasons: the
finding set is not deterministic across runs, and prism's response cache key
excludes the rules file, so a cached replay returns the no-rules answer while
looking like a rules run.

**What does work is a probe.** A scratch rules file carrying a `required` check
that demands a specific, otherwise-impossible finding — keyed to a marker string
planted in the diff under review — with the response cache disabled for the run.
The finding appears only if the required text reached the model. This tests the
one link unit tests cannot: file on disk to prompt to provider.

## Rejected alternatives

**Have the pack strip `severityOverrides` in-memory and pass a rewritten rules
file from a temp directory.** Removes the fleet edit and the ordering
constraint. Rejected: it makes the file on disk stop describing what actually
runs, which is a worse version of the bug being fixed — the consumer would read
their own rules file and be wrong about their gate. The whole defect is that
what the file says and what the review does have drifted apart.

**Refuse the review outright when `severityOverrides` is present.** Rejected: it
fails ten repositories' reviews for a condition the pack can safely ignore, and
turns a config nit into an outage. Degrading to today's behaviour is strictly
better.

**Ship chunking in the same change.** Rejected as scope. `--rules` is a
one-flag correctness fix against a defect that is measurable today; chunking is
a design decision about whether the pack owns a diff-splitting strategy, and
folding them together means neither gets reviewed on its own merits.
