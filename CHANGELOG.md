# Changelog

## 0.71.57 - 2026-08-26

### Fixed

- A `--successor bookkeeping` re-entry on a pull request can now complete in a
  repository with no routed-review descriptor. `--successor bookkeeping`
  deliberately selects zero local providers, which makes the local outcome
  `skipped`, and the absent-router branch for PR scope accepted only `clean` --
  so the successor's own documented route could not reach `ready`. The
  workaround was `--remote none`, which is legitimate only where routed review
  is optional, and it was discovered rather than documented.
- The branch now accepts a `skipped` outcome when the plan selected zero
  providers, and reports a third limitation, `local-skipped:<policyId>`, naming
  the policy that chose to ask nothing. The policy is reported verbatim rather
  than through the coarser `skipReason` vocabulary, which knows only two
  policies and would relabel the rest as `not-requested`.
- The deciding fact is the plan's `providers` list, not the outcome word.
  `outcome: "skipped"` is reached two ways -- nobody was asked, and every asked
  provider reported `skipped` in its own payload -- and `remoteGate` cannot
  tell them apart either, since neither has outstanding findings or a terminal
  failure. `skipped` was deliberately not split into a new outcome; the
  unconflated fact was already in the receipt.

### Changed

- A non-PR review whose providers were all asked and all reported `skipped` no
  longer reaches `ready`. It previously did, because the non-PR branch accepted
  every `skipped`. Both branches now share one predicate, so they cannot drift
  apart again -- that divergence is what made the bookkeeping successor
  unreachable on a pull request. This is a behaviour change, not a bug fix, and
  it is reachable only through an argv-adapter provider that reports
  `status: "skipped"`; the bundled `prism` and `gito` adapters emit only
  `clean` and `findings`.
## 0.71.56 - 2026-08-26

### Fixed

- A remote review in which one provider found something and another died no
  longer reports a plain `eligible` gate. `_aggregate_outcome` ranks `findings`
  ahead of `failed` on purpose -- a run that found real problems should report
  them as findings, not as a failure -- but the remote gate was reading that
  single word as its whole verdict, so the terminal-failure branch never ran and
  the gate contradicted the receipt printed beside it, which already named the
  dead lane under `confidence.limitations`. The gate now takes a separate
  `degraded` signal drawn from that same limitations list, so a partial run is
  gated as limited whatever the providers found. `_aggregate_outcome` is
  unchanged; reordering it would have traded this bug for its mirror image.
- Re-gating a stored receipt after a disposition reads the persisted
  `confidence.limitations` rather than recomputing it, so dispositioning a
  finding cannot silently clear a provider limitation it did not address.
## 0.71.55 - 2026-08-26

### Fixed

- Review scope: a pack-version adoption PR no longer requires a hand-written
  `Tooling/generated scope:` section. `check_pr_body_scope` failed on any
  non-zero count of scoped files, which cannot distinguish a diff of *only*
  pack-installed files from authored work carried alongside them — so the
  consumer-side adoption commit the pack itself produces was refused by the
  pack's own gate. When every changed path is pack-owned, the body requirement
  is waived; the scope report still prints, and no advisory marker is emitted.

### Security

- The adoption exemption reads file ownership from the **base** copy of
  `.sd-ai-command-pack/installed-targets.txt` rather than the working tree, so
  a diff cannot exempt itself by appending its own authored path to the
  receipt. Untracked files are counted for the same reason. An unreadable or
  empty base receipt, or one authored file alongside the pack files, denies the
  exemption.

## 0.71.54 - 2026-08-25

### Fixed

- Every `--bookkeeping-evidence` rejection in the local review stage now names
  the contract it wanted. The flag takes a five-key descriptor --
  `"schemaVersion": 1`, `"classification": "bookkeeping-successor"`, and
  `base`/`head`/`contentDigest` equal to the reviewed target -- and that shape
  was discoverable only by reading the validator. A caller who reverse-engineers
  a schema from source is one step from hand-authoring a payload to satisfy the
  check, which is manufacturing the evidence the classification exists to
  require, so the honest route is now the documented one.
- The nonexistent-path case is attributed to the flag. It was resolved in
  `main()` under a blanket `except (OSError, ReviewInputError)` that stringified
  the error verbatim, so the operator saw `[Errno 2] No such file or
  directory: '<path>'` and was told neither which argument was at fault nor
  that a JSON file was wanted. The resolution moved into an attributed helper
  rather than widening that `except`.
- The unsupported-or-missing-fields rejection names the fields. It compared
  `set(value)` against the allowed set and reported neither side, so a missing
  key and an extra one read identically. The common case -- passing
  `final-bundle --mode completion` output, whose `kind` is
  `trellis-bookkeeping-validation` and which collides on the word bookkeeping --
  now says exactly that, and each message disambiguates the two artifacts.
- The target-mismatch rejection names which of `base`, `head`, or
  `contentDigest` disagreed and echoes only the bounded caller-supplied value.
  It deliberately does not print the target's own values: handing over the
  expected answer is the same shortcut in a friendlier costume, since a pasted
  value proves nothing about the tree it claims to describe.
- The `sd-review` skill now documents the descriptor and the one way to obtain
  it. `base` is the resolved merge-base OID rather than the pull request's base
  branch and `contentDigest` is computed over the canonicalized delta, so
  neither is derivable by hand; both are read from the `target` object of a
  `--plan-only --json` run of the same attempt. A required input reachable only
  by reading source was a contract that could not be satisfied from the docs.

Diagnostics only: no outcome classification, exit code, or receipt schema
changes. Exit code 2 and the `schemaVersion`/`command`/`status`/`outcome`
report envelope are asserted unchanged on every rejection branch.

## 0.71.53 - 2026-08-25

### Fixed

- The status collector's machine-scope row no longer reports `unavailable` on
  a machine install. `machine_scope_api()` looked for the engine in exactly
  one place -- `installer/machinescope.py` beside the directory holding the
  running script -- and on a machine install that arithmetic yields
  `~/.agents`, which ships no `installer/` at all. Since the `sd-status` skill
  routes thin consumers to precisely that copy, the row was permanently
  `unavailable` for the documented path, which hid a live 0.71.26-against-
  0.71.22 version skew: the one thing the row exists to show. The loader now
  walks an ordered ladder -- the script-adjacent root first, unchanged and
  still winning wherever it resolves today, then the parent of each
  `path_pack_bins()` entry in `PATH` order, which reaches the versioned plugin
  cache root that does carry `installer/`.

  The second rung imports executable Python from a directory `PATH` names, so
  it is gated: the candidate must hold a real `installer/` package (both
  `__init__.py` and `machinescope.py`), must carry a pack identity marker, and
  must have none of the root, the package, or the module world-writable. The
  identity check accepts `manifest.json` naming `sd-ai-command-pack` **or**
  `.claude-plugin/plugin.json` naming `sd`; the plugin cache root -- the one
  arrangement this fix exists to reach -- carries no `manifest.json`, so a
  gate keyed on that alone would have rejected the target root and shipped a
  fix that fixed nothing. The script-adjacent rung is deliberately not gated:
  it is the tree already executing.

  A refused candidate is reported rather than silently skipped, since skipping
  would degrade back to the same bare `unavailable` while also hiding a
  directory that had no business being on `PATH`. When no rung answers, the
  error names every candidate tried and why each was refused. The report gains
  `engineRung`, `engineRoot`, and a bounded `engineRefusals`, rendered into
  the human row only when the engine did *not* come from beside the script --
  so the common arrangement's line is byte-identical, and the unusual one
  discloses that a version-qualified engine root may be describing an install
  of a different release.

## 0.71.52 - 2026-08-25

### Fixed

- The local stage's `gito` adapter transmitted only the base of the review
  range. gito supplies its own head from the working tree, so a delta review
  was `base..<whatever is checked out>` rather than `base..head`. In ordinary
  use the tree *is* the head and the bug is invisible; it bites when the head
  is supplied explicitly and differs — replaying a historical range, or any
  caller reviewing a ref it has not checked out. The failure was silent and
  severity-free: exit zero, a plausible finding count, and a receipt recording
  the base and head that were *asked for*. Observed on a real replay where
  fourteen of fifteen findings cited files outside the requested diff. The
  delta invocation now passes `--what <head>` alongside `--vs <base>`;
  `worktree` keeps no head (the tree is the subject) and `codebase` is
  unchanged.

### Added

- `requiresTreeAtHead`, a provider property for a tool that reads file
  *content* from the working tree rather than from the refs it is given. Such a
  provider cannot honour a head the tree does not hold, so the stage now
  refuses a `branch_delta` review in that situation, naming both oids, instead
  of dispatching and recording a head the output does not support. Passing
  `--what` alone is not sufficient: gito resolves the diff from refs but reads
  content from the tree, which produces either a crash or a fabricated
  "inconsistency between diff and final file content" finding.
  It defaults to true for the built-in `gito` adapter and false otherwise, and
  only an `argv` provider may declare it — a wrapper such as `prism-chunked`
  can opt in. `prism` was tested and does **not** need it: it reads content
  from refs, returning findings about code the tree does not contain.

## 0.71.51 - 2026-08-25

### Added

- A third `--local-disposition` ground, `accepted`, for a finding that is
  accurate and that the repository has deliberately decided not to act on.
  The vocabulary previously had a ground for "this finding is wrong"
  (`rebutted`) and one for "this finding is pointed at the wrong place"
  (`miscited`), and none for "this finding is right, and the answer is still
  no." An accurate finding the repository had accepted therefore had no honest
  disposition: calling it `rebutted` filed a false classification, and leaving
  it undispositioned blocked the merge with no exit but a human
  round-extension. Grammar is `<stable-id>=accepted@<reason>`; the reason is
  required, bounded at 500 characters, and stored on the finding as
  `dispositionReason`.
- The bound on that ground is attributability, not prevention, and the choice
  is deliberate. `accepted` grants no power an operator lacked: the pack never
  reads the checkout to verify a disposition, so both existing grounds were
  already assertions taken on trust, and anyone wanting to wave a real defect
  through could already write `rebutted`. What changes is the incentive — the
  honest answer now has a name, so a decision that would have been recorded as
  a fabricated rebuttal is recorded as a signed statement instead. No cap was
  added; a cap would block honest batches while doing nothing about one
  dishonest waiver.
- Waivers are counted apart from rebuttals. The receipt's `disposition` block
  gains an `accepted` integer, kept separate from `dispositioned` so a reader
  can tell a receipt that refuted its findings from one that waived them, and
  `accepted` takes the first rung of the `remoteGate` eligible ladder,
  reporting `local-findings-accepted` ahead of `local-findings-dispositioned`.
  Ranked any lower, a waiver in a receipt that also rebutted something would
  have been invisible to a reader consulting `remoteGate.reason` alone — which
  is the silent acceptance the ground exists to avoid.
- `accepted` is a local disposition only and deliberately absent from
  `FINDING_DISPOSITIONS`, whose sole consumer validates `--family-evidence`
  payloads. A waiver has no defined meaning on that path, and an accepted
  family finding carrying `actionable: true` would have validated and reached
  the family gate with nothing deciding what it meant. A test pins the
  rejection, because the two sets look like they ought to agree and the obvious
  tidying edit is to add the member to both.

- The ground is admitted by the coordinator as well as the stage. The
  controller keeps its own copy of `LOCAL_DISPOSITION_VALUES` and gates on it,
  so a ground added to the stage alone is refused before it reaches the stage
  and is unreachable through the documented entry point. Its router also
  buckets every receipt disposition and raises on one it does not know, which
  would have rejected an accepted receipt outright rather than miscounting it
  -- a trap the surrounding comment already described for `miscited`. Both are
  now covered by a controller-level test asserting the pair is forwarded
  verbatim, since a stage-only suite passes either way.

### Changed

- The `--local-disposition` grammar error for an `@` payload on a ground that
  takes none now reads "only miscited and accepted accept an @ payload". The
  previous wording named `miscited` alone and became false.

## 0.71.50 - 2026-08-25

### Fixed

- Restored the authored formatting of `templates/.prism/rules.schema.json`.
  Removing `severityOverrides` in 0.71.49 was done by round-tripping the file
  through `json.dumps`, which expanded two inline arrays that had been written
  compact. Semantically identical, but it would have landed as gratuitous churn
  in every consumer diff of the 0.71.49 rollout, on top of the six lines that
  are the actual change. Caught by installing into one consumer before rolling
  to nine.

## 0.71.49 - 2026-08-25

### Fixed

- The shipped prism rules schema no longer admits `severityOverrides`. Release
  0.71.48 retired the key from the runner, which now refuses a `.prism/rules.json`
  carrying it, but left the property standing in
  `templates/.prism/rules.schema.json`. An author who hand-wrote one got a file
  that validated against every check available to them and was then refused at
  review time, with nothing in between to catch it. The root object already
  carried `"additionalProperties": false`, so deleting the property is what
  forbids it. Raised independently by Copilot on four consumer PRs during the
  0.71.48 rollout, which is the signal the contradiction was legible from
  outside.
- The refusal list and the schema are now bound by test rather than by
  convention. `REFUSED_RULES_KEYS` is a module-level mapping of refused key to
  the reason published in the receipt, and
  `test_the_shipped_schema_admits_no_key_the_runner_refuses` asserts the
  intersection of the schema's admitted keys with that mapping is empty. Editing
  either side alone now fails, which is precisely how the two drifted apart.
  Falsified by restoring the property: `- set() + {'severityOverrides'}`.
- A refused key's receipt reason comes from that mapping rather than from a
  literal at the refusal site, so a second refused key cannot inherit the first
  one's explanation. `test_every_refused_key_carries_its_own_receipt_reason`
  asserts each reason names its own key and carries no path separator, since
  receipts are published artifacts.

## 0.71.48 - 2026-08-24

### Fixed

- Pack-driven prism reviews now pass `--rules`. Since the prism adapter shipped,
  the argv builder emitted `prism review range|codebase … --format json` and
  nothing else, so a repository's `.prism/rules.json` — its `focus` categories
  and its `required` checks — was ignored by every review the pack ran. Every
  repository with a pack install ships one of these files. Consumers should
  expect **new findings** after adopting this release: the required checks are
  being evaluated for the first time, and that is the fix working rather than a
  regression.

  The flag is only passed when the file exists, so a consumer without one sees a
  byte-identical command line.

### Changed

- `.prism/rules.json` no longer requires — or ships with — a `severityOverrides`
  block, and `.prism/rules.schema.json` no longer lists it under `required`. The
  key is still a permitted property, so an existing file stays valid.

  prism applies `severityOverrides` client-side *after* the model answers,
  rewriting each finding's severity from its category
  (`ApplySeverityOverrides`, `internal/review/rules.go:82`). That replaces the
  per-finding judgement the local advisory gate discriminates on with a lookup
  table: with the block the pack shipped, every `correctness` finding is `high`
  and therefore blocking, however small. Measured on a real 23-file branch, the
  `high` set was exactly `correctness 14 + security 3 + bug 2` and the advisory
  set exactly `docs 4 + maintainability 7 + testing 4 + style 3` — both sides
  exact, no finding anywhere off its category's mapped severity.

- The review stage **refuses to pass a rules file that still carries
  `severityOverrides`**, and records why. It does not fail the review: it falls
  back to the no-rules behaviour that shipped before this release, so a consumer
  who has not yet removed the key sees no change at all. Remove the key to have
  `focus` and `required` applied.

  This is deliberate sequencing rather than a migration warning. A consumer that
  keeps the block gets today's behaviour; one that removes it gets its rules
  honoured. Neither gets a gate whose blocking decisions are made by category.

### Added

- Review receipts record what happened to the rules file. Every attempt in
  `receipt.attempts[]` now carries a `rules` object with a `status` of
  `applied`, `absent`, `unreadable`, `refused`, or `not-applicable` for adapters
  that do not consult one, plus a `reason` for the two failure cases.

  Nothing previously recorded this. `invocation.json` carries the provider
  *plan*, not the command line, so a rules file being silently ignored was
  indistinguishable from no rules file at all — which is how the missing
  `--rules` flag survived unnoticed across every consumer.

  `absent` means the path is genuinely missing. A dangling symlink or a
  directory at `.prism/rules.json` records `unreadable`: `Path.is_file()`
  follows symlinks and so reads a broken link exactly like a missing file, and
  a receipt calling that `absent` would report a broken checkout as a
  repository that ships no rules.

### Upgrade notes

- Roll out **without** `install.py --force`. `.prism/rules.json` is
  `if-not-exists` precisely so local `required` checks survive an update, and
  `--force` overrides that. Consumers still holding a byte-exact previously
  shipped default are corrected automatically by the installer's provider-config
  history and report `refreshed`; consumers with local edits report `preserved`
  and need the `severityOverrides` key removed by hand.

## 0.71.47 - 2026-08-24

### Added

- The local review gate can release advisory findings by severity. A repository
  may set `"policy": {"localAdvisorySeverityCeiling": "low" | "medium"}` in
  `.sd-ai-command-pack/review.json`; an outstanding local finding at or below
  that severity no longer blocks `remoteGate`, which reports
  `local-advisory-released`. **Omitting the key is strict and is the default**,
  so adoption is opt-in per repository and every existing consumer keeps
  byte-identical behaviour until it opts in. Rollback is deleting the key — no
  pack downgrade, no reinstall.

  `high` and `unspecified` are refused at parse time even though both are
  members of the severity vocabulary: accepting `high` would let a policy
  author lower the blocking floor to nothing, and `unspecified` (rank 0) means
  the provider classified nothing, which is the last thing a ceiling should
  release. A severity outside the vocabulary also ranks 0 and stays blocking,
  so a provider cannot label its way out by inventing one.

  This exists because per-finding rebuttal alone does not converge. Across nine
  measured rounds on two consumers, successive provider invocations returned
  almost entirely disjoint observation sets — rounds 1 and 2 of one PR shared no
  finding at all — so rebutting a round's findings only produces a different
  round. The loop is unbounded in rounds, not in findings per round.

- `--local-disposition '<stable-id>=miscited@<path>:<line>'` dispositions a
  finding that does not describe the code at the location it names. Distinct
  from `rebutted`, which asserts the finding is false, and from a finding that
  is real but low severity. The citation is required and is the caller's own
  evidence; both it and the provider's cited location are kept in the receipt,
  so the assertion is auditable. The pack does not read the checkout to confirm
  it — a receipt has to be replayable from its own contents — which is the same
  trust posture `rebutted` already has. A citation path may not contain `=`.

### Changed

- `remoteGate` now distinguishes why it opened: `local-stage-terminal` (nothing
  was found), `local-findings-dispositioned` (rebutted or miscited), and
  `local-advisory-released` (ceiling). The strongest claim the receipt supports
  wins, so a reader is never told "clean" about a receipt that was released.
  The receipt's `disposition` block carries `advisory` and `dispositioned`
  counters alongside `outstanding`.
- `sd-review`'s local-completion rule now reads `remoteGate.state`, not the
  outcome. A released receipt is still `outcome: "findings"` and still carries
  zero confidence — deliberately, since the release is a policy decision made
  in advance rather than a claim that nothing was found — so a rule keyed on
  "clean" would have refused exactly the case the ceiling exists to allow.

## 0.71.46 - 2026-08-22

### Changed

- The fleet integration-only review profile now runs on `sd-review` instead of
  `sd-review-pr`. `sd-fleet-refresh` invokes `sd-review` for its `review`
  action with the same trusted context (`caller: sd-fleet-refresh`,
  `return-after: review-result`, `defer-finish-work: true`), and `sd-review`
  gained the trusted-caller contract: exact-head identity between
  `classified-head`, the live local head, and the PR head; fail-closed
  fallback to the normal remote profile on any non-eligible, unavailable,
  malformed, or head-mismatched recheck; and `0` recorded remote rounds when
  the profile is granted. The trusted context is not an argument — the
  `key=value` enum stays closed, so a `caller=` argv token remains an unknown
  key.
- `sd-review` defers finish-work rather than cancelling it. Where
  `sd-review-pr` cancels the deferral and runs finish-work itself when the PR
  turns out to be already merged, `sd-review` returns a typed deferral
  disposition (`deferral: cancelled`, `deferral-reason: pr-already-merged`)
  and leaves the call to `sd-fleet-refresh`. This keeps "Do not merge, archive
  Trellis work, or run housekeeping from this skill." absolute rather than
  narrowing it for one trusted caller. The disposition is added to the review
  result, not substituted for it.
- The `Fleet Integration-Only Recheck` procedure moved from `sd-review-pr`
  into `sd-fleet-refresh`, which owns the profile end to end. It was moved
  rather than copied, so there is no second live copy to drift.
  `sd-review-pr` keeps a pointer and still runs its own path.
- `PLUGIN_CLOSURE_ALLOWLIST` and `MACHINE_CLOSURE_ALLOWLIST` are both empty.
  Their only entries exempted `sd-review-pr`'s inlined reference to the
  source-only `sd-ai-command-pack-fleet-review-classify.py`; the relocation
  removed the reference, so the exemptions retired with it. The two dicts key
  the same authored file differently (`skills/...` versus
  `.agents/skills/...`), so both had to be cleared.

## 0.71.45 - 2026-08-21

### Fixed

- `.gemini/settings.local.json` now carries the same `optionalReferencePaths`
  exemption 0.71.43 gave its Claude twin. Both are per-checkout machine state,
  gitignored the same way (`.gitignore:66` and `:104`), and both prefixes are
  checked; only one was exempt. These two are the whole set — no other checked
  prefix has a machine-local settings file — so the asymmetry is now closed
  rather than narrowed.
- An `optionalReferencePaths` entry cited as a location kept its line suffix
  through the exemption lookup, so it was not recognised as the same file:
  `.claude/settings.local.json:5` resolved, found the machine-local file
  missing, and failed. The lookup now also tries the citation with its line
  suffix stripped. This affected every optional entry, not only the settings
  files, and was pre-existing — the new Gemini exemption merely landed on it.

### Changed

- Pinned the thin conversion's rewrite scope with a test, and corrected how
  0.71.44 described it. That entry said directory-shaped `.agents/` tokens are
  "not in the rewrite map", implying a file-versus-directory distinction. The
  actual rule cuts elsewhere: the conversion repoints `scripts/<name>` to
  `~/.agents/bin/<name>`, and a concrete path already written under `.agents/`
  passes through untouched — bin, skills, or docs, file or directory alike,
  since such a citation is already true of the canonical layout and repointing
  it would move a reference that resolves. Glob text is the deliberate
  exception: `literal_rewrites` replaces the exact `.agents/skills/sd-*/SKILL.md`
  and `**/skills/sd-*/**` strings, because a thin checkout has no pack tree for
  those globs to select and the resweep calls a glob broken when nothing it
  selects survives. No behaviour changes; the rule was simply never stated or
  asserted, which is how the `.claude/` ignore survived a year.

## 0.71.44 - 2026-08-21

### Fixed

- `sd-audit-repo` told the agent the charter directory resolves "either inside
  the installed skill payload or at `.agents/skills/sd-audit-repo/charters/`
  relative to the repository root". The second half holds only in a vendored
  install. Every consumer in the fleet is thin, none carries a repo-relative
  charter directory, and the thin conversion does not rewrite this path —
  directory-shaped `.agents/` tokens are not in the rewrite map. The arm is
  kept, because in a vendored checkout it is the arm that works (the Claude
  adapter copy of the skill carries no `charters/` of its own), but the root is
  now named as the payload's root rather than the repository's, and the text
  says outright that a missing repo-root path is not a blocker in a thin
  install. Same family as 0.71.42, and fixed the same way: drop the false
  qualifier rather than add a conversion-time substitution.

## 0.71.43 - 2026-08-21

### Fixed

- The review preflight never checked a `.claude/` path citation. The prefix was
  listed both in `referencePrefixes`, which declares a tree checkable, and in
  `ignoredReferencePrefixes`, which skips one; the ignore won, so every
  `.claude/` citation in every consumer was passed unread. Its three neighbours
  in that list are generated or never-committed trees; `.claude/` is an
  authored adapter tree the installer writes into, and the class the gate could
  not see — a dangling `.claude/skills/sd-*/SKILL.md` — had to be found by hand
  in review. The ignore entry is removed and the behaviour is now pinned by a
  test in both directions. Measured fleet-wide impact before shipping: six
  newly-visible citations across seven repositories, none of them a dangling
  path in shipped surface.
- `.claude/settings.local.json` is exempted by name in `optionalReferencePaths`,
  with the reason in the source: it is per-checkout machine state, gitignored at
  `.gitignore:66`, so its absence in a clean clone is normal rather than a
  dangling citation. This is the narrow half of the old blanket ignore, and the
  only part of it that was right.

## 0.71.42 - 2026-08-21

### Fixed

- The `sd-housekeeping` and `sd-review-learnings` adapters told the agent a
  script was reachable "at that path relative to the repository root". The thin
  conversion rewrites that path to `~/.agents/bin/<name>` and leaves the prose
  alone, so a converted consumer carried a sentence calling an absolute `$HOME`
  path repository-relative, in the same clause that printed it. Twelve sites
  across six thin consumers. The clause is now dropped rather than rewritten
  during conversion: "at that path" is true in both install shapes, and a
  conversion-time substitution would be a byte-matched second copy of the
  sentence that stops matching the moment the source is rewrapped. Same family
  as the 0.71.41 `sd-review` fix -- prose that survives conversion describing
  something that does not -- and invisible for the same reason, since a thin
  consumer's resweep has nothing left to remove and reports clear.
- The same two adapters offered `PATH` as an alternative way to resolve that
  script, which `sd-review` explicitly forbids in the same repository: "a
  `PATH` entry can name a different install than the one the running skill text
  came from." Two commands were instructing the resolution the pack's own
  policy rules out, and the backticked token was a path rather than a bare
  command name, so the `PATH` arm could not have resolved it as written. Both
  now resolve at the given path only, and carry the same warning `sd-review`
  does.

## 0.71.41 - 2026-08-21

### Fixed

- The `sd-review` adapter prose named `sd-ai-command-pack-review.py` as a bare
  filename while telling the agent to reach it only through the toolchain
  bootstrap. The adapter surfaces that carry that sentence survive a thin
  conversion; the machine-scope script it names does not, so every thin
  consumer was left citing a file its own conversion had deleted --
  hoa-manager, loadsmith and anomaly-metric-creator all carry it today. It went
  unnoticed because a resweep only sees names it is about to remove, and by the
  time a consumer is thin there is nothing left to match. It surfaced when
  people-profiles became the first fat consumer swept since the sentence
  landed. The prose now names the typed review coordinator instead; the script
  name stays in `sd-review/SKILL.md`, the authority the adapter defers to.

## 0.71.40 - 2026-08-20

### Fixed

- A fleet refresh archived its Trellis task with every acceptance criterion
  still unticked. Nothing in the publish path ever ticked them and nothing
  asked the operator to, so a merged archive reported verified work as
  unverified — two consumers carry that in history from the 0.71.38 rollout.
  `sd-ai-command-pack-fleet-publish.py` now ticks the criteria it can prove,
  immediately before `task.py archive` so the rewrite lands in the archive
  commit and the completion bundle keeps its shape. Criteria carry a
  `<!-- verify: ... -->` tag naming the evidence that would settle them; the
  verifier keys off the tag and never off the prose, so a rewording cannot
  silently change what gets asserted. `install-audit`, `tracked-mode`, and
  `bundle-shape` are proved from the consumer tree, and the asserted release
  and platform set ride on the tag because the helper takes no release
  argument. Everything else is supplied through the new repeatable
  `--criterion-evidence <id>=verified|unverified[:<note>]`, whose malformed
  values are rejected outright rather than read as "unverified". An untagged
  criterion, an unknown tag id, and a missing lane result all stay visibly
  unticked and are named in a generated disposition block and in the helper's
  `uncheckedCriteria` result; an already-ticked box is never unticked. See
  `.trellis/spec/tooling/fleet-publish-acceptance-criteria.md`.

## 0.71.39 - 2026-08-20

### Fixed

- `make audit` reported success on a machine with no scanner installed:
  both the bandit and the zizmor blocks fell through to a warning and an
  `if` that exits 0, so a security gate that audited nothing was
  indistinguishable from one that found nothing. `STRICT=1` now makes a
  missing scanner fatal, matching the node and shellcheck lanes that
  already had that branch.
- The `sd-finish-work` fallback guidance told the caller to fill
  `(Add details)`, `(Add test results)`, and `(see git log)` placeholders
  that the current recorder never writes -- `add_session.py` now omits any
  section it was given no content for, so an agent following the old text
  searched for strings that never appear and could read the absence as a
  recorder failure. The skill now tells the fallback caller to supply
  `--summary`, `--change`, and `--test` content up front and treats a
  missing section as a missing flag. (#484)
- An evidence-backed successor-head re-entry (`--successor bookkeeping`
  with matching `--bookkeeping-evidence`) now carries its own fixed budget
  of two rounds past `remoteIntegration roundLimit`, so the Stage 2b
  re-entry that every completed `sd-ship` chain performs no longer forces a
  `review.round-extension` decision that carries no information. The
  evidence is validated against the exact target in the local stage before
  any provider is selected, a falsely claimed re-entry still fails before
  any spend, and every other over-limit attempt -- including a bookkeeping
  claim without evidence and any attempt beyond the fixed grant -- is still
  refused until the structured decision is recorded. (#485)

## 0.71.38 - 2026-08-20

### Fixed

- Reinstalling now repairs an installed file whose executable bit has drifted
  from what the pack ships. Byte-identical content short-circuited straight to
  `unchanged`, so a destination that had lost its exec bit was stuck that way
  permanently: no reinstall, at any version, would fix it, because the content
  it would have rewritten was already correct. That is how 0.71.36's exec-bit
  fix failed to reach the fleet -- every consumer would have pulled the
  corrected pack and kept the broken mode. Content equality is not file
  equality; the mode is part of what the pack ships, so a disagreement is drift
  and now reports as `updated`.

  Repair runs in both directions and preserves the installed file's read
  permissions: an exec bit is granted exactly where read is already granted, so
  a deliberately restricted mode (`0600`) becomes `0700`, not `0755`. A dry run
  names the drift without touching the file. The chmod is verified rather than
  assumed, so a filesystem that cannot represent the bit reports `unchanged`
  instead of claiming an update on every run forever.

## 0.71.37 - 2026-08-20

### Added

- The documentation path-reference gate now checks a bare filename when it is
  cited as a *location* -- a name carrying a line or line-range suffix such as
  `review.py:555`. 667 bare references were skipped outright, so a document
  could name a file that does not exist and nothing objected. The naive
  widening (any bare filename must name a tracked file) produces 160 failures
  across 43 documents; restricting it to locator form yields 107 newly-checked
  references and exposed exactly 4 genuine dangling citations, now annotated.
  A filename with no line suffix stays unchecked, because prose uses a
  filename as a noun far more often than as a path.

  Resolution matches by basename against `git ls-files`, retrying the
  `sd-ai-command-pack-` and `sd_ai_command_pack_` prefixes the pack uses for
  its own scripts, and treats a name matching several tracked files as
  resolved rather than failed -- the mirror between `templates/scripts/` and
  `scripts/` would otherwise fail every helper the pack documents.
  `bareReferenceExtensions` widens the extensions a bare filename may carry,
  and a malformed value leaves the built-in set in force.

  The basename index is consulted at resolution, never at eligibility:
  `shouldCheckDocumentationPathReference` stays a pure test of shape, because
  an eligibility gate that knew whether a file was tracked could never fail,
  and the rule's whole value is its failing half.

## 0.71.36 - 2026-08-20

### Fixed

- Shipped pack helpers are tracked executable, so
  `sd-ai-command-pack-toolchain.sh run -- <helper>` works in the pack's own
  checkout. `run` ends in `exec "$RUN_COMMAND"`, and 21 of the 25 shipped
  non-library helpers were tracked `100644`, so the documented way to reach
  them died with `Permission denied` on a fresh clone. The mode had two
  independent derivations: `installer/machinepayload.py` and
  `.github/scripts/generate-plugin.py` derive it from the destination family
  and the `sd_ai_command_pack_` library prefix -- which is why every installed
  copy is already `755` -- while `installer/fileops.py` carries the template's
  own mode forward, making this repository the single tree where the wrong bit
  was authoritative and the single tree `run --` resolves against. Nothing
  caught it because the resolver tests chmod their own fixtures and the
  source-drift gate compares bytes, which is blind to modes by construction.
  This change moves 50 tracked modes across `templates/scripts/`, `scripts/`,
  and `.sd-ai-command-pack/bin/`; no shipped script's content changes. The four
  `sd_ai_command_pack_*` modules stay `100644`, matching the rule the
  generators already implement.

### Added

- `.github/scripts/check-shipped-script-modes.py` fails when a shipped script
  is tracked with the wrong mode, in both directions: a shebang-carrying file
  that is not `100755`, or an importable `sd_ai_command_pack_*` module that is.
  It enumerates from `git ls-files -s` and classifies by the blob's first two
  bytes, so a helper added later is covered without editing the gate, and it
  reads the index rather than the filesystem because a checkout with
  `core.fileMode` disabled lets the two disagree. A mode is invisible in diff
  review, which is why this is a gate and not a matter of care.

### Changed

- A **fresh** install now writes
  `.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py` executable
  where it previously wrote it `644`. That target sits outside every payload
  family, so it is installed from the template's own mode; it is committed in
  consumer repositories and the usage guide tells readers to call it directly
  from their own guards, so shipping it non-executable was the same defect one
  tree over. **Existing installs are untouched** -- the installer returns
  `UNCHANGED` before any `chmod` when the bytes already match, so a consumer
  keeps its current mode until something rewrites the file.

## 0.71.35 - 2026-08-20

### Fixed

- A commit subject containing a backslash no longer reaches the session journal
  unescaped. The record-session wrapper resolved every subject itself and then
  overwrote each commit-table row with `subject.replace("|", "\|")`, which
  escapes pipes but leaves backslashes raw, preserves whitespace runs that can
  break the row, and skips the 500-character truncation. `add_session.py`
  resolves the same subjects from the same object database and renders them
  with `escape_markdown_cell`, which handles all four cases, so the wrapper now
  passes the OIDs and asserts the rows were written rather than re-rendering
  them. The overwrite dated from a Trellis version that seeded a
  `(see git log)` placeholder; no such placeholder exists any more.

- The fleet refresh lane no longer creates a task whose `base_branch` is the
  refresh branch. Two surfaces forbade `task.py create --base-branch` on the
  grounds that the vendored `task_store.py` rejects it as an unrecognized
  argument -- true when written, false now, and the prohibition had begun to
  cost the correctness it was meant to protect: without the flag, `create`
  falls back to the checked-out branch, which on that lane is exactly the wrong
  answer. The two-step create-then-repair sequence is replaced by passing the
  flag, and `set-base-branch` returns to being the repair for an existing task.

### Changed

- The vendored Trellis compatibility contract now states a supported floor --
  the build `0.6.16-sd.7`, which this repository and all eight fleet consumers
  run as of 2026-08-20 -- and the wrappers that straddled `0.6.7` and `0.6.14`
  drop the branches that only served the older runtime. The status collector's
  three-way `current --json` fallback becomes the single documented call: a
  non-zero exit or unparseable stdout now means "no active task" instead of
  falling back to parsing prose.

  The floor is recorded as an identity, not a range. `0.6.16-sd.7` carries a
  prerelease segment, so under semver it sorts *below* `0.6.16`; the natural
  `>=0.6.16` spelling would reject every repository in the fleet.

  Not everything that looked like version machinery was one. The wrapper's
  Testing and Next Steps patching survives, because `add_session.py` applies
  its bullet prefix unconditionally and would render an already-marked line as
  `- [OK] [WARN] flaky lane`; so does its retry handling, which covers an
  uncommitted half-written entry rather than the already-committed record
  `--idempotency-key` addresses. Both are now documented as deliberate
  exceptions rather than left to read as leftovers.

- The human `sd-status fleet` report prints each repository's Trellis version
  beside its pack pin. The JSON payload always carried it, so an operator
  reading only the human report saw a fleet consistent on a version it had
  never been shown. `current --json`'s `stale` flag is surfaced the same way.
  The runtime calls a pointer stale when its directory is gone, so the ordinary
  stale case resolves to no task record at all; rather than suffix "none
  active" with a contradiction or drop the signal, the report names the
  pointer -- `none active [stale pointer to .trellis/tasks/<slug>]` -- which is
  the only thing left to act on.

## 0.71.34 - 2026-08-19

### Added

- A documentation reference can now be marked as deliberately unresolvable
  where it is written, with `[absent: <reason>]` immediately after it on the
  same line. `checkDocumentationPathReferences` resolves every eligible
  reference against the filesystem, and the only escape hatch was
  `optionalReferencePaths` -- a repository-wide array with no file or line
  scope, so silencing one path for one sentence silenced it everywhere,
  including in a future document that names it because it genuinely rotted.
  A PRD describing current state routinely needs to name a path that is
  currently absent, and saying so is the point of the sentence.

  The reason is required: the marker's whole purpose is to record why, so
  `[absent:]` and `[absent: ]` leave the reference checked, as do a missing
  colon, an unclosed bracket, anything non-blank between the reference and the
  marker, and a marker on the next line or before the reference. Reasons may
  not span a line terminator, `\r` and U+2028/U+2029 included. The exemption
  covers only the one reference it follows: a second reference to the same
  path, in the same file or elsewhere, still fails. `optionalReferencePaths`
  is unchanged and remains correct for paths that are optional everywhere,
  such as generated artifacts.

  The two references on `main` that had been stripped of their code spans on
  2026-08-08 to unblock CI are restored and marked, which is the degradation
  this replaces.

## 0.71.33 - 2026-08-18

### Fixed

- The review preflight's default working-tree run now enforces the
  planning-phase branch invariant it already reported as checked.
  `task.py start` is what records a branch, so a `status: planning` record
  already carrying one means the task was started without its lifecycle
  advancing with it. The bundle-scoped `planning_lifecycle_mutation` rule
  encodes the same invariant, but only the bookkeeping and finalization paths
  reach it, so an ordinary run printed a Trellis task metadata PASS covering
  identity, lifecycle, and branch integrity while that one combination went
  unchecked.

  `validateTrellisBookkeepingMetadata` now rejects it directly, conditioned on
  the record's own status rather than on bundle context, so `in_progress`,
  `review`, and archived `completed` records keep their branches untouched.
  Measured across this repository before the change: 77 active and 333
  archived task records, none newly rejected.

## 0.71.32 - 2026-08-18

### Fixed

- The pull-request eligibility probe no longer blames branch protection for a
  merge state GitHub has not finished recomputing.
  `classify_non_clean_merge_state` diagnosed a non-CLEAN `mergeStateStatus`
  from one snapshot, and every cause it named is stable except the one it did
  not name: the read right after a push or a draft-to-ready transition can
  report a `BLOCKED` that clears itself within about a minute. That case fell
  through to `merge_blocked_review` -- "a required approval or branch-protection
  rule is unsatisfied" -- sending an operator to inspect branch protection with
  nothing wrong with it.

  A genuine protection block and a stale snapshot are the same bytes in one
  read, so that one branch now spends a bounded re-read to separate them:
  `MERGE_STATE_RECHECK_ATTEMPTS` (2) extra reads, each preceded by
  `MERGE_STATE_RECHECK_DELAY_SECONDS` (3.0), stopping early on the first value
  that differs. A caller that never polls therefore pays at most 6 seconds and
  2 extra `gh` calls, and only on that branch. A `BLOCKED` stable across every
  read keeps the branch-protection diagnosis, now worded `on every read`; a
  value that moved reports the new retryable-indeterminate
  `merge_state_unsettled` instead, which is strictly weaker than the block it
  replaces. An unavailable re-read degrades to the existing generic
  `merge_state_not_clean` rather than earning a verdict on absent evidence.

  The re-read lives inside the probe rather than in a settle-watch because
  `sd-ai-command-pack-housekeeping.sh` calls the probe once and acts on that
  single result; a caller that cannot poll must still receive an accurate
  diagnostic. No path through the change can report `eligible` for a `BLOCKED`
  state, and the sd-ship watch coordinator's classification order is updated to
  keep polling on `merge_state_unsettled` rather than settle it as blocked.

## 0.71.31 - 2026-08-18

### Fixed

- The generated structural map guard in `review-preflight` no longer passes
  when the map it was pointed at has no `# Directory Structure` section.
  `parseGeneratedStructuralMapEntries` returned `parsed: true` for that case
  and the caller only inspected `parsed`, so a map with no readable section
  reached the success path and printed
  `checked 0 generated structural map .trellis/ path(s); all resolve`. That is
  the guard's own failure mode one level up: if repomix renamed the heading,
  every consumer's gate would validate nothing while still reporting PASS, and
  nothing distinguished "this repository has no map" from "this map's format is
  no longer one we can read".

  An existing map with no section is now unreadable rather than empty. It warns
  -- naming the file and the reason -- and does not emit a pass line, matching
  how the unparseable-indentation case is already treated: a generator format
  change is a pack-side defect, and failing every consumer's gate on it would
  convert one upstream mistake into a fleet-wide outage. The success message
  also splits in two, so a parsed map that simply lists no `.trellis/` path
  reports `generated structural map(s) list no .trellis/ path; none needed
  checking` instead of a `checked 0` line that reads as a validation that ran.

- The same parser now skips a fence line carrying a language or info string
  (` ```text `) and a tilde fence, not only a bare backtick fence. Repomix
  currently opens the listing with a bare four-backtick fence, so no map is
  misparsed today; had that changed, an indented fence line would have been
  taken as a tree entry and reported as a `.trellis/` path that does not
  resolve -- drift no regeneration could fix.

## 0.71.30 - 2026-08-17

### Changed

- Every shipped skill now reaches a pack helper through one resolution rule,
  defined once in the new
  `.agents/skills/sd-help/references/pack-helper-resolution.md`. Skills used to
  write `bash scripts/sd-ai-command-pack-toolchain.sh`, which is
  working-directory relative and resolved by nothing: a thin consumer has no
  `scripts/` directory, so the invocation failed before the toolchain's own
  resolver -- the part that guarantees a run cannot mix two installs -- was ever
  reached. Each executable block now carries a bootstrap that tries
  `SD_AI_COMMAND_PACK_TOOLCHAIN`, the checkout's own `scripts/` copy, then the
  machine install under `$HOME/.agents/bin`, and reports all three when none
  answers. `PATH` is deliberately absent from that order, because `PATH` is
  where the version split comes from: a host that prepends a stale plugin cache
  leaves the oldest surviving entry answering first, with no relation to which
  pack the running skill text came from.

  84 authored sites changed across `templates/.agents/skills/**`,
  `templates/docs/SD_AI_COMMAND_PACK.md`, and `.github/command-sources/**`. Two
  were live defects rather than style: `sd-create-pr` guarded an invocation with
  a `command -v` probe that accepted a different set of locations than the
  invocation used, so it could pass while the invocation threw, and `sd-check`
  required vendored `scripts/` siblings that a thin consumer never has.

### Added

- `.github/scripts/check-helper-resolution.py`, wired into `make check` and CI,
  fails on a `scripts/`-prefixed helper in an executable block, on `node`,
  `bash`, or `python3` invoking a helper directly, on a helper named as the
  second operand of `run --` (which `run` never resolves), and on a block that
  uses `$SD_PACK_TOOLCHAIN` without a byte-identical copy of the bootstrap --
  each fenced block runs in its own shell. It enumerates the authored trees from
  the filesystem and reads the canonical bootstrap out of the reference file, so
  a skill added later is covered without editing the gate and the rule cannot
  drift from its definition.
- `sd-status` reports a helper-resolution row beside the machine-scope line, and
  deliberately not folded into it: which release is installed and which release
  a helper invocation runs are different questions. The row names the resolved
  toolchain, which candidate answered, its install root, every `PATH` entry
  holding a pack toolchain in `PATH` order, and a verdict of `bound`,
  `shadowed`, or `unresolved`. A `PATH` entry is recognized by holding the
  toolchain file rather than by matching a name pattern. `machineScope` moves to
  schema 2.

### Fixed

- The plugin build no longer mangles the bootstrap. Its rewrite turns a
  repository-root helper path into a bare PATH-resolved name, which would have
  silently converted the bootstrap's second candidate -- a probe asking whether
  the working directory is a pack source checkout -- into exactly the PATH
  resolution the rule exists to remove. `installer/references.py` now preserves
  that one quoted literal through both the rewrite and the residue gate; every
  prose and invocation form stays rewritable.
- The plugin and machine payloads no longer rewrite the resolution reference's
  own counter-examples. Both files document a rule by contrasting the wrong
  form with the right one, and the rewrite was right about the wrong half
  everywhere else: stripping `node ` from the `run --` trap, and the `scripts/`
  prefix from the operand rule, left each "Wrong" line byte-identical to the
  "Right" line beneath it. `RewriteProfile` gains `verbatim_spans`, which frees
  one exact span in one payload file rather than a name file-wide, and the
  plugin generator now passes the destination path so per-file declarations are
  consulted at all -- it previously rewrote every Markdown file with an empty
  key, so no exemption of any kind could apply to it. All five copies of
  `pack-helper-resolution.md` are byte-identical again, and a test asserts it
  from the filesystem rather than from a list.
- `sd-update-spec` and the `sd-audit-repo` tooling charter invoked
  `$SD_PACK_TOOLCHAIN` without saying where it comes from. Both now point at
  the bootstrap reference, like every other skill that uses the variable.

## 0.71.29 - 2026-08-16

### Changed

- `work-loop.py start` no longer replaces an existing ledger implicitly. A
  `stopped` or `completed` run used to fall out of the resume branch and reach
  `new_state()`, overwriting the ledger in place with no warning, no backup,
  and no reason code -- and the `--run-id` mismatch guard sat inside that same
  resume branch, so `start --run-id <the run I meant to resume>` was exactly
  the invocation that minted a fresh ledger carrying the run ID it destroyed.
  One consumer lost 8 completed / 8 merged PRs / 29 review rounds that way, and
  the loss is recorded only because an operator hand-wrote it into the run's
  own stop reason. `start` now refuses such a ledger with a nonzero exit naming
  the status and both flags: `--resume` reactivates the run in place, keeping
  its run ID, iteration, counters, and stop reason, and `--reset` archives the
  outgoing ledger to a `replaced.json` sibling before minting a new run. The
  flags are mutually exclusive, `--resume` without an existing ledger is an
  error rather than a silent new run, and `--reset --run-id <the discarded run
  ID>` is refused. `active` and `paused` resume semantics are unchanged.
- The `--run-id` mismatch guard now covers every existing ledger rather than
  only the resumable ones, and `status` reports whether a replaced-ledger
  sibling is present along with the replaced run ID and timestamp. An
  unreadable sibling reports present-but-unreadable; read-only status never
  raises on it.

## 0.71.28 - 2026-08-16

### Changed

- Housekeeping no longer returns `blocked` because local branches the run never
  touched still exist. That check fired on every successful merge in any
  repository that keeps branches around -- 3 branches and 14 branches produced
  the same verdict -- so it could not distinguish tidy-up from the one case that
  mattered, an unmerged branch with no pull request holding work present nowhere
  else. It also could not clear at all for anyone running concurrent worktrees,
  since a branch checked out elsewhere cannot be deleted by any correct cleanup.

  In its place the status collector classifies every local branch other than the
  default one, in both its advisory and strict modes, and publishes the result as
  `localBranchClassification`: `merged`, `unmerged-with-pull-request`,
  `unmerged-without-pull-request`, or `unknown`, each carrying the worktree
  holding it when one does. `unmerged-without-pull-request` is asserted only from
  pull request evidence that was available, untruncated, and current; anything
  else reports `unknown` with the reason rather than a false claim that no pull
  request exists. Merged branches no worktree holds surface as a follow-up
  action; the rest are reported without blocking.

  What that check incidentally covered -- the run's own source branch surviving
  deletion -- is now an explicit blocking postcondition, `local_source_branch_retained`.

- Status anomalies carry a severity. `anomalyDetails` runs parallel to
  `anomalies` (same order, same messages) and adds a stable code plus
  `blocking` or `advisory`. `--expect-clean` exits nonzero for blocking entries
  only, and the human report marks advisory ones `[advisory]` under the same
  `Anomalies` heading. Every previously blocking condition still blocks: a dirty
  tree, a diverged or missing default branch, a retained remote source branch.

- A default branch held by another live worktree is diagnosed instead of being
  reported as an opaque failure. Housekeeping emits `default_branch_held_elsewhere`
  naming the holding worktree, and `branch_retained_default_held` for the branch
  deletion it therefore skipped; both are advisory, so a merge whose every action
  succeeded returns `clean`. A switch that fails for any other reason keeps
  `default_branch_switch_failed` and now carries git's own first line of stderr.
  This closes the case where 14 pull requests merged in one session (#358-#379)
  each reported the same two opaque anomalies and a `blocked` verdict.

- A blocked housekeeping verdict names its cause where the reader is looking.
  The opaque `status_anomalies` reason code is replaced by the collector's own
  codes, prefixed -- `status_working_tree_dirty` rather than a pointer to the
  embedded document. An embedded status result without `anomalyDetails` keeps
  today's whole-list blocking behavior under the old code, so a mixed pair fails
  closed.

- `--prior-anomaly` on the status collector now takes a code and a message
  rather than a message alone, so a replayed caller anomaly keeps its severity.
  It is an internal flag with one caller, `sd-ai-command-pack-housekeeping.sh`.

## 0.71.27 - 2026-08-16

### Fixed

- Both machine-scope entry points now reconcile duplicate
  `claude plugin list --json` entries instead of refusing them. One plugin
  registered at user scope and again for each project that enables it is the
  ordinary shape of that listing -- three agreeing entries were measured on a
  developer machine -- and every entry describes the same install. Refusing
  them cost three things at once: `sd-status fleet` reported
  `pluginVersion: unavailable` and `comparison: unknown` for every consumer,
  which also suppressed the plugin-versus-receipt skew alarm rather than
  merely hiding a version; and `sd-ai-command-pack-pack-update.sh` exited `12`
  before running either half, stranding the only refresh path a thin machine
  has now that the consumer-side sync automation is retired. The failure text
  ("resolve the duplicate install before updating") named an action that does
  not exist -- there is no duplicate install to resolve, and following it would
  mean disabling the plugin in a consumer that legitimately declares it.

  Each site reconciles on the one field it consumes and refuses only a genuine
  disagreement: the status collector on `version`, the updater on
  `installPath`. Exit `12` is kept and narrowed to that path conflict, and its
  message now names the conflicting paths. Nothing consumes these exit codes
  programmatically, so the narrowing is not a contract change.

  **Bootstrap:** the first refresh after this release must be run from the pack
  source checkout --
  `bash scripts/sd-ai-command-pack-pack-update.sh` -- because the installed
  updater is still the previous one and will still exit `12` on a duplicated
  listing. Subsequent refreshes work normally from either copy.

## 0.71.26 - 2026-08-16

### Fixed

- `sd-check` now locates its five shipped-helper built-ins by installation
  mode instead of reading `scripts/` unconditionally, so a consumer converted
  to a thin install can pass again. Conversion moves the payload to the machine
  install and `pack.install-audit` fails any attempt to vendor it back, so
  every converted consumer reported `unavailable` for `pack.review-preflight`,
  `pack.install-audit`, `knowledge.obsidian-kb`, `pack.review-scope`, and
  `pack.pr-body-scope` while all five were installed and working. Because
  `unavailable` outranks `passed` in the aggregate, `sd-check` could never
  reach `passed` there and `sd-review` failed closed with
  `deterministic-check-not-passed` ahead of dispatch -- taking the whole
  `sd-ship` chain with it. Measured on `sd-github-review` at 0.71.24.

  Resolution goes through the pack-owned layout resolver and is gated on the
  consumer's own thin pin rather than on the resolver's machine rung, which
  fires for any directory on a machine that has the pack installed: a
  repository with no pack receipt still reads `scripts/`, unchanged. This
  decides where to look and not what counts as present -- a helper absent from
  both the repository and the machine install stays `unavailable` with its
  existing diagnostic. `.sd-ai-command-pack/check.json` was never a workaround
  for this: built-in rows are appended before configuration is read and
  duplicate row IDs are rejected, so a configured entry can neither replace nor
  suppress an `unavailable` built-in.

## 0.71.25 - 2026-08-16

### Added

- The surface generator now emits `generated/registry-snapshot.json`, the same
  `schemaVersion` 1 registry snapshot the SE pack already ships. `skill_review.py`
  from `se-review-skills` prefers a snapshot and falls back to AST-parsing
  `installer/registry.py` only when there is none; this pack shipped no snapshot,
  so in an SD checkout the "fallback" was the only path on every run. The
  snapshot is produced from the **imported** registry objects -- `COMMAND_FAMILIES`,
  `COMMAND_REGISTRY`, `PLATFORM_REGISTRY`, `SHARED_SKILL_REFERENCES` -- and not by
  re-parsing `installer/registry.py`, which would make the producer agree with the
  parser by construction while both drift from the real objects.

  `familyOrder` and `sharedReferences` carry the real values even though the AST
  parser derives neither for this pack: it reads the SE names `FAMILY_LABELS` and
  `SHARED_REFERENCES` and cannot see `COMMAND_FAMILIES` / `SHARED_SKILL_REFERENCES`.
  Emitting the parser's empties would have encoded a blind spot into the file that
  becomes the only registry source once the fallback is removed. The three fields
  the parser *can* derive -- `families`, `skill_order`, `platforms` -- were verified
  equal between both derivations on the same checkout (20 skills, 18 platforms).

  A malformed snapshot fails closed in the consumer while an absent one falls
  back, so the file is registered as a single output of the existing
  `generate_surfaces()` dict: `--check` drift detection and byte-determinism come
  from the machinery already in place rather than from a second code path.
  `generated/registry-snapshot.json` is added to `PAYLOAD_SINGLETONS` -- a
  singleton rather than a `generated/` prefix, so a future file under `generated/`
  is enrolled in the release gate by whoever adds it, not silently.

## 0.71.24 - 2026-08-16

### Fixed

- A routed `copilot` review no longer claims remote confidence for a review it
  did not cause. The Action already distinguishes the two cases -- it probes for
  the reviewer before requesting and records `dispatch.status` as `requested` or
  `already-present` -- and the coordinator validated that enum and then threw it
  away, harvesting reviews by author and head commit alone with no causal guard
  while conversation comments carried `created_at >= dispatch.startedAt`. A
  repository ruleset that requests Copilot when the pull request opens therefore
  had its review counted as the routed lane's own evidence. Every terminal report
  produced after remote observation now carries
  `remote-evidence-not-dispatch-caused` when the receipt says `already-present`.
  The findings are reported unchanged and no exit code moves -- what the
  limitation withdraws is the causal claim, not the evidence. A symmetric
  `submitted_at` guard was rejected because a ruleset requests early and the
  reviewer submits late, so a timestamp admits the foreign review anyway;
  rejecting `already-present` evidence outright was rejected because it would
  zero out remote confidence permanently wherever the piggyback is deliberate.

## 0.71.23 - 2026-08-16

### Fixed

- `sd-ai-command-pack-pr-body-scope.py --prepare-tooling-body` now declares the
  tooling subset of a mixed diff instead of refusing it. Previously it appended
  the scope section only when *every* changed path was generated or repository
  bookkeeping, and exited `3` writing nothing otherwise -- which left the PR
  body without a heading in exactly the case that needs one. `sd-ship` Stage 2b
  commits the workspace journal and index after the body has been authored and
  judged complete; those files are a `pack.review-scope` category, so the gate
  began requiring a heading at the finalization head, on a body that was
  correct when written and was no longer being edited. Seen on PRs #156, #163,
  #172, #203 and #208.

  The old refusal was a truthfulness guard, not an oversight: the canned
  section claims the change is *limited to* generated surfaces, false when
  authored files are present. A mixed diff now gets a section naming only the
  paths proven to be generated, worded as a non-exhaustive "include:" list --
  the branch acquires further generated files after the body is written, so an
  exhaustive claim would be false by the time the gate reads it. Paths are
  sorted, escaped with `json.dumps` so a newline in a filename cannot inject
  Markdown into a published body, and capped at 20 with an explicit remainder
  count rather than silently truncated.

  `pack.review-scope` itself is unchanged. Exit `3` survives with a narrower,
  honest meaning -- nothing to declare -- so a diff carrying no generated path
  still writes nothing and an unexplained generated change still reaches the
  gate undeclared and still fails.

## 0.71.22 - 2026-08-16

### Fixed

- `install.py TARGET --revert-thin` now undoes the conversion's repoint of the
  files it keeps. A conversion does not delete a kept surface -- it rewrites
  the pack references inside it in place -- and the payload restore has no
  inverse for that: `.github/PULL_REQUEST_TEMPLATE.md` is in
  `FORCE_PRESERVED_TARGETS`, so `install_file` returns `PRESERVED` for it and
  the revert exited zero with the consumer's own template still pointing at
  `~/.agents/docs`, which a fat checkout cannot follow. The undo is the thin
  rewrite read backwards, applied to the current text so post-conversion
  consumer edits survive, and each restoration is rewritten forward again and
  must reproduce the file byte for byte or the whole revert refuses and names
  it. Found by widening the round-trip test to a tree that installs the
  `github` platform; on `.claude` alone the conversion is almost entirely
  deletion and nothing exercised the kept-surface path.
- The thin `~/.agents/docs` reference is restored when a sentence ends on it.
  The forward rule has a leading boundary and no trailing one, so it rewrites
  `docs/SD_AI_COMMAND_PACK.md.`; an inverse that mirrored the forward boundary
  on the trailing side read the period as a path character and left the
  reference relocated -- through a full revert, exit zero.
- `install.py TARGET --thin` and `--revert-thin` no longer misreport a
  writable registry root as unwritable when two conversions probe it at once.
  The probe was a fixed `probe.touch()`/`probe.unlink()` pair: the first
  unlink wins and the second raises `FileNotFoundError`, and a leftover probe
  from a killed run made `touch()` answer about write permission to that file
  rather than to the directory. It is now `tempfile.mkstemp`, which creates
  under `O_EXCL` with a unique name and so fails exactly when the directory
  cannot take a new entry.
- `sd-status fleet` finds the fleet manifest when it is run from inside a pack
  source checkout by a machine install. `scripts/../` was the only rung, and a
  machine install puts the script at `~/.agents/bin/`, where that arithmetic
  yields `~/.agents` -- not a pack checkout, so the last resolver rung refused
  and the command reported missing configuration from inside the very checkout
  holding the manifest. The runtime root now asks the working directory too,
  through a new public `find_pack_source` in the shared fleet library.

## 0.71.21 - 2026-08-16

### Fixed

- A thin conversion no longer fails a consumer's narrow-globs gate on the
  Copilot payload-families list. The rewrite drops
  `scripts/sd-ai-command-pack-*` from that bullet, which promotes the legacy
  `scripts/trellis-*.sh` beside it to the line's first glob -- a Trellis family
  most consumers never had, so it matches nothing. Trellis'
  `check-narrow-globs.py` builds its paragraphs from the diff's added lines
  alone, so the bullet was invisible to the gate until the conversion touched
  it, and a `<!-- narrow-globs: skip -->` marker already sitting in the
  template would be context rather than an addition and never reach the
  paragraph. The marker now arrives as part of the rewritten bullet. Measured
  on `mezmo_benchmark`: the conversion PR's `preflight` job failed gate 6 with
  `glob \`scripts/trellis-*.sh\` matches 0 files in the working tree`, and
  every consumer running that gate without those legacy scripts would have hit
  the same wall.

## 0.71.20 - 2026-08-16

### Fixed

- A thin conversion no longer drops the consumer's ignore rules. The managed
  `.gitignore` block was deleted outright, and its rules are about the
  consumer's own tree -- `.env`, `.build/`, `.trellis/` runtime state,
  `.claude/settings.local.json` -- not about the payload being removed. The
  first `git add -A` after a conversion therefore committed local state the
  repository had been ignoring for as long as the pack was installed; measured
  across four converted consumers, one of which published 317 review-receipt
  files to its default branch that way. The conversion now *adopts* the block:
  the rules stay, the markers and the generated notice go, and a plain comment
  pair records that the repository owns them now. `--revert-thin` removes the
  adopted section before the payload restore re-inserts the managed block, so
  the two never stack.

## 0.71.19 - 2026-08-15

### Fixed

- The review preflight no longer reviews the wrong tree under a thin install.
  It derived its root as `resolve(scriptDir, '..')`, which is the consumer
  checkout when the file is vendored and the agents directory when a thin
  install moves it to the machine. There it found no repository content and
  reported `PASS` -- `package.json is not present`, six `could not inspect
  current diff` warnings, and a clean result over a tree nobody asked about.
  The root now follows the same ladder the shipped shell guards use: the
  `SD_AI_COMMAND_PACK_REPO_ROOT` override, then the caller's working tree via
  `git rev-parse --show-toplevel`, then this file's parent last, so a vendored
  install resolves exactly what it always did.

## 0.71.18 - 2026-08-15

### Fixed

- A relative `SD_AI_COMMAND_PACK_REPO_ROOT` no longer silently disables the
  review-scope guard. The override is the only root rung that can answer
  relative -- `git rev-parse --show-toplevel` and `cd ... && pwd` cannot -- and
  every path derived from it, the installed-targets receipt first, is built
  before the guard enters the repository. Once it did, the relative receipt path
  re-resolved against the new working directory, matched nothing, and the guard
  reported no tooling/generated scope at all while still exiting `0`. Both
  shipped shell guards now normalize the override with `cd ... && pwd -P` and
  export the absolute form back, since the shared shell library reads the raw
  variable rather than the script's local copy.

## 0.71.17 - 2026-08-15

### Fixed

- The two shipped shell guards no longer assume they live inside the
  repository they are checking. Both derived their root as
  `$SCRIPT_DIR/..`, which is the consumer checkout under a fat install and the
  agents directory under a thin one -- so a converted consumer's full check
  ended at `fatal: not a git repository` before the first check ran, with the
  layout resolver having correctly located and started the script. Measured on
  `rwbp-coordinator` converted at 0.71.16.

  `sd-ai-command-pack-full-check.sh` and `sd-ai-command-pack-review-scope.sh`
  now resolve the root through the same ladder the shared shell library
  already uses for its cache root, rather than a second convention:
  `SD_AI_COMMAND_PACK_REPO_ROOT`, then `git rev-parse --show-toplevel` from the
  caller's working tree, then the hosting checkout. Under a fat install
  invoked from inside the repository the second rung returns exactly what the
  third one used to, so every existing caller keeps its current root.

## 0.71.16 - 2026-08-15

### Fixed

- The layout resolver no longer reports a converted consumer as `fat`. It
  decided the install mode from whether `.sd-ai-command-pack/installed-targets.txt`
  exists, and conversion does not delete that file -- it rewrites it down to the
  residual slice the repository still holds. So every converted consumer
  classified as fat and the resolver then refused to locate any pack script,
  because the names it looked for had just been removed from the very file it
  was reading. Measured on `rwbp-coordinator` at 0.71.14, which resolved
  `mode: fat` while both of its own receipts recorded `thin`:
  `error: sd-ai-command-pack-full-check.sh is not listed in
  .sd-ai-command-pack/installed-targets.txt`. Every consumer guard shells out to
  `--resolve` and executes the result, so this made the conversion the rollout
  is for unusable.

  Mode now comes from the recorded thin pin, read the same way
  `installer/conversion.py:thin_pin_state` reads it: `manifest.json` first, then
  `provenance.json`, with thin-only pin keys under a non-thin mode reported as a
  receipt that contradicts itself rather than silently read as fat. The
  environment override still outranks everything, and a fat consumer resolves
  exactly as before. A thin consumer keeps the residual receipt for path
  classification, because those surviving rows are pack payload the repository
  genuinely still carries; only script resolution branches on mode.

## 0.71.15 - 2026-08-15

### Fixed

- `sd-review` can now observe a routed review finishing. The durable lane
  writes its receipt Check Run twice -- once with `dispatch.phase: "started"`
  as the route step begins, then a few seconds later with the terminal phase
  and a `completedAt`. The coordinator polled inside that window and kept what
  it found: the receipt was queried only when none was stored, the poll loop
  broke on the first non-`None` result whether or not it was terminal, and the
  terminal check then turned that cached `started` phase into
  `remote-reconciliation-required`. Since the only branch that re-queries an
  existing receipt is the dispatch-*failure* path, the rerun of the unchanged
  attempt that `sd-review/SKILL.md` prescribes replayed the cache forever --
  a wedged attempt rather than a pending one.

  Measured on `platypeeps/sd-github-review` PR #86, the first pull request to
  run against a fully installed durable lane: `21:51:30.633Z` to
  `21:51:34.172Z`, then `22:03:16.347Z` to `22:03:19.403Z` at a second head.

  A stored receipt whose dispatch is still in flight is now treated like a
  missing one and re-queried, so a receipt that settles within the existing
  poll budget is observed in the same invocation and a later rerun of the
  unchanged attempt gets a fresh read rather than the cache. Only
  `phase: "started"` counts as in flight: `not-started` is what a skipped
  `route: none` dispatch carries and still flows straight to observation, and
  a `failed` status stays terminal for the operator to reconcile. The
  fail-closed diagnostic is unchanged -- a receipt still non-terminal when the
  budget is exhausted continues to report `remote-reconciliation-required` --
  and a re-query never dispatches, never widens receipt matching, and never
  discards a stored receipt when the query transiently returns nothing.

## 0.71.14 - 2026-08-15

### Fixed

- The thin resweep no longer blocks on the migration it prescribes.
  `docs/FLEET_ROLLOUT.md:630` tells a consumer to replace its
  `scripts/sd-ai-command-pack-*` literals with `--resolve NAME` against the
  kept layout resolver. `NAME` is the bare basename of a removed path, so both
  bare-name rules in `cites_removed_path` fired on it: rule 5 directly, and
  rule 3 by resolving it against the citing file's own directory whenever the
  guard lives in `scripts/`. A consumer that followed the recipe exactly traded
  many blockers for a few and stayed `blocked`, with no documented next step.
  Measured on `rwbp-coordinator`: the rewrite cleared 44 blockers and its own
  three resolver keys replaced them.

  A file that names the kept resolver has adopted the resolver contract, so its
  slash-free pack basenames are keys rather than paths. The exemption is
  file-scoped, because the key is normally a constant declared away from the
  call site, and it reaches only the two bare-name rules: a path-shaped pack
  citation in the same file still blocks, which keeps the half-migrated trap
  named at `docs/FLEET_ROLLOUT.md:639` -- adopting `--resolve` while still
  naming the resolver under `scripts/` -- failing exactly as before.

## 0.71.13 - 2026-08-15

### Fixed

- `sd-ai-command-pack-review-layout.py` no longer names two machine-scope
  scripts in its prose. It is a `consumer-config` target, so thin conversion
  keeps it -- and `repoint_kept_references` rewrites only the forms
  `THIN_PROFILE` recognises, none of which is a bare basename in a docstring.
  A comment reading "already existed in ``sd-ai-command-pack-review-scope.sh``"
  was therefore a permanent `packDefect` in every consumer that installed the
  file, unfixable by the conversion and blocking it outright. Measured: the
  first refresh carrying 0.71.12 put two fresh defects into all three canaries
  at once, after the cohort had already measured zero.
- A test now enumerates every `consumer-config` target from the surface
  partition and fails if its shipped source names a removed path, borrowing
  `unambiguous_basenames` from the resweep rather than restating it so the
  guard cannot drift stricter than the check that produces the verdict. This
  class of defect is invisible until a consumer installs the file, which is
  the wrong place to find it.

## 0.71.12 - 2026-08-15

### Fixed

- The thin resweep now judges the bytes a conversion would write, not the ones
  it reads. `repoint_kept_references` rewrites kept files' path citations as
  part of every conversion, but the resweep scanned the pre-conversion text, so
  a correct citation of a path the consumer currently has was reported as a
  `packDefect`. `decide` blocks on any `packDefect` and `--thin` refuses any
  verdict but `clear`, so no fat consumer in the fleet could convert: the pack
  shipped the rewrite and the gate that rejected it. The scan now runs
  `planned_repoints` and reads the rewritten text for any kept file the
  conversion would repoint. Ownership is deliberately not consulted --
  membership in the repoint set is the whole test, and `plan.keep` comes from
  the receipt, so consumer-authored files are never in it. Measured across the
  canary cohort: 15 pack defects each before, 0 after, with consumer-owned
  blockers unmoved except one line in a pack-installed file the consumer had
  taken over, which the conversion does repoint.
- `THIN_PROFILE` rewrites the skills glob to `~/.agents/skills` rather than
  `~/.agents/skills/sd-*/SKILL.md`. `cites_removed_path` matches path suffixes,
  so the fuller form still ends with the removed `.agents/skills/sd-*/SKILL.md`
  and reads as a citation of the path the rewrite just repointed away from --
  the same trap `AGENTS_DOC_DIRECTORY` documents one screen above the rule that
  fell into it. It was the single surviving defect once the repoint simulation
  cleared the other fourteen.

## 0.71.11 - 2026-08-14

### Added

- The layout resolver now also installs to
  `.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py`, which the
  surface partition classifies `consumer-config` and thin conversion keeps.
  A repository's guards should call that path. Everything under `scripts/` is
  machine-scope, so a converted consumer that names the resolver there cannot
  ask where the pack is without naming a path the conversion just deleted --
  and the resweep fails closed on a single such reference. Measured across the
  fleet before this shipped: 288 references to `scripts/sd-ai-command-pack-*`
  spread over 68 files, so adopting `--resolve` alone would have traded many
  blockers for one per calling file rather than for none.

### Changed

- `sd-ai-command-pack-review-layout.py` no longer imports
  `sd_ai_command_pack_lib`. It was a bare sibling import that worked only
  because both files travelled together; the `consumer-config` copy has no
  such sibling, and the library is machine-scope. `resolve_state_root` and
  `CommandError` are carried in the script, with a test walking every rung of
  the ladder against the library's copy.
- `docs/FLEET_ROLLOUT.md` records the conversion ordering cohorts depend on:
  ship, refresh, rewrite guards, resweep, convert.

## 0.71.10 - 2026-08-14

### Added

- `sd-ai-command-pack-review-layout.py`: a pack-owned resolver for the
  installed layout, with two queries -- classify changed paths as pack payload
  or authored source, and resolve where a pack script actually lives. Five
  consumers had each reimplemented the first question against a hardcoded fat
  layout; the second exists because a thin install moves every
  `scripts/sd-ai-command-pack-*` out of the consumer, so a literal path
  reference breaks. Node and shell bindings delegate to the one implementation
  rather than restating it.

## 0.71.9 - 2026-08-14

### Added

- `sd-status fleet` reports the newest published release beside the checkout
  target. The fleet target was the operator's own checkout manifest, so *stale*
  meant "behind my checkout", not "behind what is published": an operator on an
  old checkout saw a healthy fleet, and an operator on an unreleased working
  copy saw every consumer flagged against a version nobody can install. The new
  `releaseTarget` field carries `status`, `version`, and `tag`, and one
  fleet-level step appears when the checkout differs from the release.

  The source is `git ls-remote --tags`, not `gh release view`: this project
  publishes annotated tags and has no GitHub Releases, so a `gh` lookup would
  have reported `unavailable` forever. Selection orders on the parsed
  `(major, minor, patch)` triple, because tag strings sort lexicographically
  and `v0.9.2` outranks `v0.71.8`.

  Consumer comparisons are unchanged and stay checkout-based. A lookup that
  produces no version is always labeled -- `disabled` under `--no-network`,
  `not-configured` without a remote, `unavailable` on failure -- never omitted
  and never silently substituted. Status remains read-only, and the release
  target is reported without counting toward the attention total.

## 0.71.8 - 2026-08-14

### Fixed

- The merge-eligibility probe blocked on check runs belonging to a workflow run
  GitHub had already superseded, contradicting GitHub's own `mergeStateStatus`
  (issue #414). A repository whose CI cancels superseded in-progress runs on the
  same ref leaves both the cancelled run and its replacement attached to the
  head, and `parse_checks` classified every rollup row independently, so the
  cancelled copy decided the verdict. Observed on `anomaly-metric-creator`
  PR #360: `gh pr view` reported `CLEAN`/`MERGEABLE` while the probe reported
  `blocked ['checks_blocking']`, and the only escape was re-running the
  superseded workflow. `sd-ship` Stage 3, `sd-housekeeping` eligibility, and
  `sd-fleet-refresh` `merge-eligibility` all inherited the false block.

  A row is now discounted when it is `CANCELLED` **and** a later-started row
  shares its `(workflowName, name)` identity. Both halves matter: restricting to
  `CANCELLED` keeps a genuine `FAILURE` from an older run blocking, and
  requiring a later sibling keeps an operator's cancellation of the only run
  blocking. Ties do not supersede, nameless rows never share an identity, and a
  discounted row is never counted successful — so a head whose every row is
  superseded is still refused, by `checks_no_success`. The receipt marks each
  discounted row with `superseded` and a `supersededBy` citation of the row that
  replaced it. Ordering comes from `startedAt`, which the existing single query
  already returns, so the probe still makes one GitHub call.

## 0.71.7 - 2026-08-14

### Fixed

- `sd-housekeeping` could block the merge it was cleaning up after (issue
  #432). It refreshes the Obsidian KB before its merge and branch-cleanup
  gates, and `sd-ai-command-pack-update-spec-kb.py` rewrote the managed
  `.gitignore` block whenever the rebuilt text differed byte for byte. A
  reworded comment line in a new pack release therefore dirtied a tracked file
  in every consumer at once, and three failed-closed cleanliness gates
  (dependency-PR merge, merged-branch cleanup, and the separate
  `pr-eligibility.py` probe) all read that as `working_tree_dirty`. The writer
  is now semantically idempotent: it rewrites the block only when the block is
  functionally deficient — markers absent, no active entry ignoring the KB
  directory, or an unmanaged KB entry outside the span — and leaves a
  functional block byte-identical, reporting `gitignore: present`. The pack
  owns the bytes between the `obsidian-kb start` and `obsidian-kb end`
  markers; a provenance mismatch confined to that span is reconciled by
  rehashing the ignore file, never by reverting it. `--rewrite-ignore-block`
  forces the old byte-exact rebuild for a caller that intends to commit the
  result, and combines with `--dry-run` and `--check`. Behaviour change:
  `--check` no longer reports `ignore entry is not current` for cosmetic block
  drift, so that drift no longer surfaces as a `knowledge.obsidian-kb` finding
  in `sd-check`.
- A `working_tree_dirty` anomaly from `sd-housekeeping` now names up to ten
  dirty paths (then `and N more`), and says so explicitly when this run's own
  Obsidian KB refresh wrote the ignore file — the case that still legitimately
  writes, such as a first-ever install creating the block.

## 0.71.6 - 2026-08-14

### Fixed

- A committed `docs/repomix-map.md` could name `.trellis/tasks/<slug>/` paths
  that the published head no longer had. The map is generated while the task is
  still active, and `task.py archive` then moves that directory, so a map
  committed ahead of the archive describes a tree that no longer exists. Four
  consumer PRs in the 0.71.5 fleet campaign published such a map and needed a
  post-push commit to repair it. `sd-ai-command-pack-review-preflight.mjs` now
  runs a `generated structural map paths` check: it parses the map's
  `# Directory Structure` listing and fails any `.trellis/`-prefixed entry that
  does not exist, naming the map file, the line, and the path. Only `.trellis/`
  is checked, because that tree is fully tracked and therefore reproducible in
  a fresh checkout of the same commit; broader trees can legitimately list
  files a clean clone does not carry. A map with no such section, a repository
  with no map, and a map whose indentation cannot be parsed are all
  non-failures — the last warns, because an unparseable map is a different
  defect and reporting it as drift would name the wrong remedy. An entry whose
  reconstructed path leaves the repository root warns for the same reason and
  is never resolved, so the existence probe cannot stat outside the tree.
  Configurable through `generatedStructuralMaps`, which unions with the
  default.

### Changed

- The `pr-publication` stage of `sd-fleet-refresh` states its order as an
  explicit four-step sequence — stage, fold finish-work through
  `sd-ai-command-pack-fleet-publish.py`, classify the pushed head, then open or
  reuse the PR. The previous prose put "push, and create or reuse one PR"
  before the sentence introducing the fold, which reads as publishing first and
  archiving afterwards. Repos the publish helper refuses now carry the same
  constraint in writing: regenerate the map after `task.py archive` and before
  the finish-work push. `docs/FLEET_ROLLOUT.md` defers to the skill as the
  single statement of that sequence instead of restating it.

## 0.71.5 - 2026-08-14

### Fixed

- A tracked install refused every pack file whose template had changed since the
  installed release, reporting it as a `conflict` that only `--force` could
  clear — in a checkout nobody had touched. `install_file` compared the
  destination against the new payload and nothing else, so it never read the
  per-target digest in `.sd-ai-command-pack/provenance.json` that proves the
  previous release wrote those exact bytes. Taking a release therefore required
  the one flag that also discards real local edits, and made using it routine.
  A vouched target now classifies `updated` and is written without `--force` and
  without a backup; the displaced bytes are a published release, recoverable
  from the pack. Content provenance does not vouch, a target missing from
  provenance, and a provenance file that is absent, symlinked, or malformed all
  still conflict, so genuine drift is unaffected and absent evidence fails
  closed. This is the repository-scope counterpart of the machine-scope
  `owned-stale` classification, decided from the same evidence `remove` already
  accepts as authority to delete a pack file. Every consumer in the 0.71.4 fleet
  campaign hit this as an identical four-file conflict set and was investigated
  as local drift before being forced.

## 0.71.4 - 2026-08-13

### Fixed

- `review-preflight seeded-task` accepted a context manifest that existed but
  carried no usable rows — an emptied file, a blank-line-only file, or rows that
  parse but have no `file` key. The gate that exists to prove a fleet-seeded task
  is grounded before a lane installs anything therefore passed the one shape a
  lane most plausibly produces. It now reports `task_context_unfilled` when a
  present manifest yields zero rows carrying a `file` key and the file emitted no
  other finding, so the more specific defect is never masked by the generic one.
  The 0.71.3 canary lane found this in the gate shipped an hour earlier.
- The pack's own documentation made this worse than a missed case: it told
  operators the generated scaffold "must be replaced or emptied before the task
  leaves planning", which is true for the two diff-scoped lanes and exactly wrong
  for `seeded-task`. That passage now states both rules where an operator reads
  it, and `seeded-task` gains the reference section it never had, including the
  `SD_AI_COMMAND_PACK_DEFAULT_BRANCH` precedence over a consumer's `origin/HEAD`.
- A consumer on an inline platform seeds no manifests at all, and that still
  passes; the new rule fires only on a manifest that is present and unfilled.
  This is covered by a test rather than an argument, because it is the criterion
  a careless fix breaks.
- `printBookkeepingResult` silently produced an `undefined` subject for any
  command not in its inlined chain. The composition moved to an exported
  `bookkeepingResultSubject`, which throws on an unrecognized command, so a
  future subcommand fails loudly at its first print instead of shipping a
  malformed receipt line. Argv cannot reach this state today; the throw exists so
  the next command cannot reach it either.

## 0.71.3 - 2026-08-13

### Added

- `review-preflight` gains a `seeded-task` subcommand that validates the Trellis
  task a fleet-refresh lane seeds in a consumer, before that lane installs
  anything. It reuses the existing bookkeeping task rules at a new lifecycle
  point (`completionReady: false`, `seedReady: true`), so there is one rule
  source rather than a second implementation that agrees on one sample.
  `seedReady` un-exempts the lone `_example` scaffold row that merge time
  deliberately tolerates — which is exactly the shape `task.py create` emits, so
  the fleet lane's real output was the one case nothing covered. Two reason codes
  are new, `task_prd_placeholder` and `task_base_branch_invalid`; an unresolvable
  default branch is `indeterminate`, not `invalid`, and an unreadable task
  directory or malformed `task.json` fails closed with exit `1`. The receipt
  records `evidence.defaultBranch` and `evidence.defaultBranchSource`, because
  under `--repo` the pack's default-branch override environment variable
  outranks the consumer's own `origin/HEAD` and would otherwise silently decide
  the rule it is being asked to enforce.
- A merge-time check rejects a Trellis task context row citing a path under its
  **own** task directory. `task.py archive` moves that directory, so the pointer
  dangles in the merged tree of the same bundle that publishes it. The finding
  names the three alternatives: repoint at `.trellis/spec/**` and move the
  substance into `reason`, cite a sibling task's `research/**`, or move the facts
  into the pack's own task. Four such rows in
  `08-09-deployment-thin-consumers` were repaired before the rule landed.
- A merge-time check rejects generated `TBD` placeholders left in a changed
  `prd.md` — the three shapes `task.py create` writes (`TBD.`, `- TBD`, and
  `- [ ] TBD`), whole-line only, so prose that discusses TBD still passes. A
  sweep of 384 PRDs found one pre-existing instance, in
  `08-10-rename-review-local-receipt-identifiers`.

### Changed

- `sd-fleet-refresh`'s `checkout-validation` stage now sets the seeded task's
  `base_branch` with `task.py set-base-branch` and validates the result with the
  new gate, replacing a prose assertion that could be — and was — skipped. It
  must not use `task.py create --base-branch`: that flag ships with the same
  vendored `task_store.py` revision that fixes the underlying defect, so on
  exactly the consumers that need it, `create` fails with
  `unrecognized arguments`. Every reachable consumer checkout — five of the
  eight in the fleet manifest; the other three are not cloned locally — still
  carries the older revision, which stamps `base_branch` as the checked-out
  branch unconditionally, on this stage the refresh branch. The gate runs from the pack source
  checkout with `--repo`, because `checkout-validation` precedes
  `install-update` and the consumer still carries the previous release.

## 0.71.2 - 2026-08-12

### Changed

- `codex` is no longer in the `shared` platform's `retainVendoredFor` list, so
  a consumer that declares it no longer keeps 77 vendored rows (49 `.agents/`,
  26 `scripts/`, 2 `docs/`) that the thin conversion would otherwise delete.
  The entry rested on a claim recorded in `0.64.35` — that Codex resolves
  skills against the project root and never reads `~/.agents/skills` — and an
  executed probe falsified it: Codex merges project-root `.agents/skills`,
  `$HOME/.agents/skills`, and `$CODEX_HOME/skills`. The machine installer's
  `agents-skills` family already writes the second of those, so the retained
  copy was a duplicate of a surface Codex reads either way. Evidence:
  `.trellis/tasks/08-09-codex-home-skills-family/research/codex-skills-resolution-probe.md`.
  `pi` is unprobed and keeps its retention. Codex's disposition is unchanged:
  still `repo-native`, still non-provisional.
- The thin resweep records undeclared Codex usage as an advisory rather than a
  blocker. The blocker existed because a missing declaration meant a retained
  surface got deleted; with nothing retained for `codex`, it was demanding a
  declaration that changes no plan. The blocking set is now read from the
  partition's `retainVendoredFor` lists rather than restated in the scanner, so
  retiring a platform's retention retires its blocker in the same edit.
  Detection, evidence, and the `packDefects` bucket for pack-owned `.codex/`
  occupancy are unchanged.

## 0.71.1 - 2026-08-12

### Fixed

- `sd-review` now recomputes the deterministic `sd-check` on every invocation
  instead of gating on the verdict stored in the attempt state. One registered
  check reads an input the attempt key does not capture — `pack.review-scope`
  reads the live pull-request body — so a stored verdict of either sign could
  disagree with what a direct `sd-check` run reports on the same tree. `0.66.2`
  stopped persisting a *failure*, which fixed the direction that false-blocks a
  remediated run; a stored *pass* false-allows, and was the worse half: a body
  that lost its scope heading after the check passed was reviewed as though the
  gate had held. The expensive local and remote stages, whose inputs the attempt
  key does cover, still replay from state, and a recompute no longer names
  `check` as the resume phase, so it cannot rewind an attempt that already
  completed later stages.

## 0.71.0 - 2026-08-11

### Added

- The pack now ships a digest history of every `if-not-exists` template it has
  ever released, at `docs/sd-ai-command-pack-provider-config-history.json`. It
  is generated during release prep from git history the first time a source is
  seen and appended to thereafter; a digest is never removed, because a removed
  digest silently re-arms the trap for whoever is still holding those bytes.
- `install.py` uses that history to tell a stale shipped default apart from a
  customized one. A file whose bytes match something this pack published under
  its own name is refreshed to the current template and reported with a new
  `refreshed` status; a file matching nothing the pack ever shipped is still
  `preserved`. Before this, a correction to a broken shipped default reached
  nobody — `--force` reported `preserved` for both cases alike. The refresh is
  not gated on `--force`, and a missing or malformed history preserves.
- The install audit reports, from inside a consumer's own CI, which of its
  `if-not-exists` configs are superseded shipped defaults and which are locally
  owned. `sd-status fleet` reports the same classification across the fleet
  without installing anything, which is what makes the population visible
  before any consumer changes.

### Changed

- Measured across the eight registered consumers on 2026-08-11: all eight carry
  the same superseded `.gito/config.toml`, while `.prism/rules.json` splits into
  one current, one superseded, and six genuinely customized. Converting those
  consumers is deliberately out of scope here; this release ships the mechanism
  and the measurement.

## 0.70.0 - 2026-08-11

### Changed

- The full-fleet candidate validator now exercises the thin install shape. A
  pack-side artifact lane runs once per candidate run — `generate-plugin.py
  --check`, `claude plugin validate --strict`, and a machine install into a
  scratch prefix — and each consumer's lane branches on its clone's own
  provenance pin rather than the registry's declared mode, so the two disagree
  safely during a conversion window. An unresolvable `claude` is reported as
  `unavailable` and fails; it is never degraded into a pass.
- `docs/fleet/candidate-validation.json` is schema version 4. Consumer status
  is now `passed`, `failed`, or `blocked`, and a `blocked` row requires a
  non-empty `reasons` array. A consumer-owned precondition — references the
  pack does not own, a dirty worktree — no longer has to be recorded as either
  a pack failure or a pass, because both answers are wrong in opposite
  directions.
- A pack-owned defect is measured **after** the conversion's own rewrite. The
  resweep's `packDefects` bucket is a pre-rewrite count of content that cites a
  removed path, and `THIN_PROFILE` repoints exactly those citations, so the raw
  count was never evidence of a release defect. The gate now fails only on
  residue that survives `rewrite_text`, and records the raw count as a note.
- Each consumer's resweep runs after the candidate install rather than on the
  pristine clone. A pristine clone carries whatever pack that consumer last
  installed, so the previous ordering measured the previous release and blamed
  the candidate for it.

## 0.69.0 - 2026-08-11

- `make release-prep` can now see a changed candidate validator. It skips fleet
  validation whenever the candidate ledger is current
  (`prepare-release.py:338`), and currency was decided by the pack version, the
  payload digest, and the fleet manifest digest — none of which move when
  `scripts/sd-ai-command-pack-fleet-candidate-check.py` is edited, because that
  file has no `manifest.json` row and no `templates/` twin. Editing the
  validator therefore left the ledger current and release-prep returned before
  ever running the new code.

  The candidate ledger gains a fourth binding, `validatorDigest`, over the
  validator sources the payload digest cannot see; `CANDIDATE_LEDGER_SCHEMA_VERSION`
  goes 2 → 3. The digest takes a source loader rather than a root, so the
  commit-scoped check in `verify_candidate_ledger_at_commit` reads the same
  commit's blobs as the ledger it validates — pairing a historical ledger with
  the working tree would report an ordinary post-release edit as tampered
  release evidence. It fails closed on an unreadable or absent source and never
  substitutes a default.

  Unlike `payload_digest`, this digest excludes the executable bit. The
  validator is invoked as `sys.executable <path>`, never as a bare executable,
  so hashing its permission bit would let `chmod +x` invalidate a ledger whose
  validator is byte-identical.

  No new finding code: a mismatch surfaces through the existing
  `provenance.candidate-stale` finding, which `prepare-release.py` already
  validates the exact shape of. Old ledgers self-migrate in both directions —
  the schema mismatch alone marks them stale, and a stale ledger is a
  regeneration, not a failure.

## 0.68.0 - 2026-08-11

- The planning adversarial review contract no longer ships its Codex lane. The
  contract told every consumer to run `codex exec`, and no consumer declares
  `codex`, so the thin resweep reported `undeclared codex usage` as a
  `packDefect` in all eight and no conversion could reach a clear verdict. The
  129-line document becomes an 80-line host contract at its existing path; the
  Codex lane moves to `docs/planning-adversarial-review-codex.md` in the pack's
  own repository, with no `manifest.json` row and nothing under `templates/`.
  The wording moved rather than changed: rewriting the invocation so it no
  longer looks like a command would have cleared the scan while leaving every
  consumer holding the same instruction.

  Shipping the lane conditionally, under a `platform: "codex"` row, was built
  and rejected. Three tested invariants encode that `codex` is a registered
  platform which ships no manifest files — it has no Trellis markers and no
  init flag, and the registry, adapter-declaration, and dogfood gates each
  assert that shape. Satisfying them by giving `codex` markers would have made
  it auto-select in every repository where Trellis installed its own Codex
  adapter, which is all eight consumers, reinstating the very `packDefect`
  being removed. Not shipping the lane touches no gate.

- **Capability loss, accepted deliberately rather than discovered.** The Codex
  lane is gated by runtime probes (`command -v codex`, `codex exec --help`),
  not by `docs/fleet/consumers.json`. Any repository whose developers have the
  Codex CLI on PATH has been running that lane regardless of what it declares,
  and after this release no consumer runs it. The host-side contract is
  unchanged and still runs everywhere; what is lost is the second opinion,
  including the `< /dev/null` detail that costs half an hour to rediscover.

  There is no per-consumer opt-in to restore it, and that is the shape of the
  decision rather than an oversight: any mechanism that puts the lane back into
  a consumer puts the `codex` invocation back into a repository that never
  declared the platform. The contract shipped to consumers now states that it
  is the whole review and must be held to the standard two lanes would have
  met. A consumer that wants a second lane defines its own, outside the pack.

- `docs/SD_AI_COMMAND_PACK.md` no longer describes the planning review as
  launching a `codex exec` peer lane. That guide installs `always`, so it
  reaches every consumer regardless of platform, and it would have contradicted
  the contract shipped beside it — telling a repository the lane runs while the
  contract states it is the whole review. Its "Local Review" section is
  untouched: `codex review --uncommitted` is `sd-review`'s own optional lane,
  a different surface this release does not change.

## 0.67.0 - 2026-08-11

- A converted consumer's repo-native surfaces now name the machine
  installation instead of the vendored paths the conversion deleted. The
  prompts, skills, workflows and the Copilot managed block that survive a thin
  conversion said `scripts/<name>` and `docs/SD_AI_COMMAND_PACK.md` — the
  files the conversion removes — so every one of them was a stale instruction
  into a path that is not there, and the thin resweep reported each as a
  `packDefect`. A third rewrite profile (`THIN_PROFILE`) supplies the thin
  wording, and the installer applies it where the payload's content is decided,
  so the digest, the provenance entry and the bytes on disk are one value. The
  fat payload is byte-identical: the thin discriminator is the existing
  `mode: "thin"` receipt, and a fat consumer takes the untouched path.
- The conversion records the digest of the text it leaves behind rather than
  the text it found. Previously a freshly converted consumer reported
  `state: invalid` with "vouched target content drifted" on every repointed
  file, and the next refresh exited 2 instead of reconciling.
- The Copilot managed block's globs are rewritten for a thin consumer rather
  than shipped in a second authored copy. The three globs select populations a
  conversion removes entirely, and the resweep calls a glob broken exactly when
  nothing it selects survives, so aiming them at another repository directory
  was not available — there is no surviving pack tree in a thin checkout.
- The KB script's generated `.gitignore` banner names the pack rather than the
  script path. That block is written by *running* the script, so a converted
  consumer keeps whatever text the last run emitted; both a path and a bare
  basename would cite a deleted file, since the resweep classifies an
  unambiguous basename exactly like the full path.

## 0.66.2 - 2026-08-11

- The review coordinator no longer caches a terminal-failure verdict in its
  per-attempt resume state. Resume caching is keyed by the attempt identity —
  repository, scope, base, head, worktree bytes, pull-request number and the
  typed controls — which does not cover every input a stage reads, so a stored
  failure survived the operator remedying the input it turned on. A
  deterministic-check failure (`pack.review-scope` reads the pull-request body),
  a rejected `--local-disposition` set, and a local provider
  `unavailable`/`failed`/`cancelled` report are now reported without being
  written, and the next invocation of the same attempt recomputes that stage.
  Previously each pinned the attempt to the stale verdict with no escape short
  of a fresh `--attempt-id`, which discards the attempt's local and remote
  review evidence too.
- A `blocked` local report stays cached, and a passing check and clean report
  still replay: local policy is decided by the configuration digest, which the
  attempt identity does cover, and the interrupted-resume guarantee is
  unchanged.

## 0.66.1 - 2026-08-10


- `install.py --status` / `--check` now understand a thin install. When the
  provenance receipt pins `mode: "thin"`, the inspection compares the checkout
  against the residual payload a conversion leaves behind instead of the full
  source payload, so a converted consumer reports `state: current` rather than
  `refresh-required` forever. The pack's `.gitignore` block is not reinstalled
  on that path, and the receipt's pinned `platforms` are reported as the
  installed platforms — a thin receipt no longer lists the machine-provided
  surfaces, so inferring platforms from it would shrink the set and make every
  fleet reader reject the consumer against the registry. A fat install takes
  the unchanged path: `mode: "thin"` is the only discriminator, and provenance
  written without a pin is byte-identical to before.
- `sd-ai-command-pack-install-audit.py` skips only its manifest-derived
  expected-target completeness check for a thin install, whose payload was
  deliberately reduced. Every receipt-to-disk check still applies: the receipt
  remains the allowlist, and every listed target must still be present.
  Verifying the receipt itself against the expected residual belongs to
  `install.py --check` run from a source checkout, which is where the surface
  partition lives.
- `install.py TARGET --thin` converts an installed consumer to a thin install:
  it deletes the machine-provided surfaces the surface partition classifies as
  such, strips the pack's `.gitignore` block, adds the marketplace and plugin
  entries to `.claude/settings.json`, rewrites all three
  `.sd-ai-command-pack/` bookkeeping files to the residual payload, and flips
  the consumer's `docs/fleet/consumers.json` row to `mode: thin`. It plans
  before it mutates and fails closed: a drifted file, a resweep verdict that
  does not bind this consumer *and* the current classifier digest, or an
  unwritable root all refuse before anything is deleted. `--dry-run` announces
  all six categories — deletes, retires, block strips, the three receipt
  rewrites, the settings additions, and the registry flip — because a
  delete-only printout passes a "the tree was unchanged" comparison while most
  of what makes the command irreversible goes unannounced.
- `install.py TARGET --revert-thin` restores what the pack can still produce
  and names what it cannot. The pinned version's payload comes back, the
  settings entries the conversion added are removed (and only those), and the
  registry row returns to `fat`. Files the conversion deleted that the pack no
  longer ships are recorded in the thin receipt's `retired` list and reported
  as `not-restored` rather than silently counted as restored. The platform set
  comes from the pin, never from re-detection: detection answers "what is
  active now", and revert's question is "what was taken away".
- An ordinary `install.py TARGET` now refreshes a thin consumer instead of
  refusing it. `sd-fleet-refresh` runs exactly that command, so a converted
  consumer that could not be refreshed was a consumer that could not receive a
  security fix. The refresh updates the version and nothing else: the machine
  payload is not re-created, the `.gitignore` block is not reinstalled, and the
  pin — including `retired` — is carried forward unchanged. Every way of asking
  it to also change *what* is installed is rejected: `--platform` and `--all`
  (the pin owns the platform set), `--local-only`, and `--remove`, which has no
  thin form.
- `sd-ai-command-pack-fleet-preflight.py` no longer skips a converted consumer
  on version equality alone. For a thin install the receipt is the allowlist,
  so the install audit skips its manifest-derived completeness check and a
  residual file that went missing is indistinguishable from a machine surface
  the conversion removed on purpose; preflight is the only place that can tell
  them apart. A thin consumer at the target version whose recorded targets are
  not all on disk now reports the new `residual-damaged` status, which flows
  through `--fail-on-refresh-needed` and the rollout runbook like any other
  non-`at-target` row. Fat consumers are judged on version as before. The
  printed repair command for a thin consumer omits `--platform`, which a
  thin-aware refresh rejects outright, and the text and JSON rows report the
  install mode and the *pinned* platform set rather than the registry's.

## 0.66.0 - 2026-08-10

- Fleet registry schema 5: each `docs/fleet/consumers.json` consumer may now
  declare `mode` (`fat`, the default, or `thin`) and `pinPath` (default
  `.sd-ai-command-pack/provenance.json`). Both are optional and both default,
  so a schema-5 registry that names neither reports exactly as the schema-4
  registry it replaces. Absolute, Windows-absolute, and `..`-bearing pin paths
  are rejected at load time, and the reader additionally resolves and contains
  the path so a symlink cannot leave the checkout.
- `sd-status fleet` reports a thin consumer by its pin — `present` with a
  version, `absent`, or `unreadable` — instead of by installed-tree drift,
  which a thin consumer no longer has. Fat consumers keep the existing
  installed-versus-target report unchanged.
- `sd-status fleet` collects the machine-scope inventory once per run, not once
  per consumer, and raises skew rows for pin versus machine install, machine
  install versus target, and plugin versus machine receipt. Those rows appear
  only when the registry contains at least one thin consumer.
- Fleet follow-ups are now derived from the complete row set and skew rows are
  ranked ahead of advisory rows, so a bounded human list can no longer drop a
  skew row.

## 0.65.0 - 2026-08-09

- Skills that positioned themselves against `sd-full-check` and
  `sd-review-local` — `sd-fix-ci`, `sd-test-gaps`, `sd-audit-repo`, `sd-check`,
  and `sd-review` — now name `sd-check` and `sd-review` instead. `sd-fix-ci`
  routed every local gate run through `sd-full-check`, so this is a behavior
  change, not only wording.
- The retired `sd-full-check` and `sd-review-local` command surfaces are
  removed. Both were transitional after 0.62.0 and are fully covered by
  `sd-check` (deterministic gate) and `sd-review` (routed review lifecycle).
  Every generated adapter, skill, prompt, and manifest row for them is gone,
  along with `scripts/sd-ai-command-pack-review-local.sh` and the 23
  `SD_AI_COMMAND_PACK_REVIEW_LOCAL_*` environment keys — including the four
  deprecated `SD_AI_COMMAND_PACK_FULL_CHECK_*` fallbacks that read them. A
  refresh retires the installed copies from prior releases; a locally modified
  copy is preserved and reported rather than deleted. `sd-review-pr` is
  untouched by this release. `scripts/sd-ai-command-pack-full-check.sh`
  survives as the pack-source gate that `make full-check` and CI still run;
  only the command surface named `sd-full-check` is retired.

## 0.64.35 - 2026-08-09

- The non-Claude surfaces now install once per machine instead of once per
  repository. `install.py --machine` (from a checkout) and
  `sd-machine-install` (bundled in the plugin) write the `machine-other`
  partition slice plus the shared runtime scripts into `~/.agents/skills`,
  `~/.agents/bin`, `~/.agents/docs`, `~/.gemini/commands`, and the XDG
  OpenCode config root, so Gemini CLI and OpenCode resolve the pack with no
  vendored copy. The engine plans before it applies: every target is
  classified against the receipt and the disk first, and a single unowned or
  locally changed file refuses the whole run naming each conflicting path.
  `--force` displaces those after copying each one to a `.bak` the receipt
  records, so `remove` can put the original back — it deletes what the receipt
  recorded installing and restores what the receipt recorded displacing, and
  nothing else. A run interrupted between writing files and committing its
  receipt is recovered through the intent journal it wrote first; byte
  identity alone never adopts a file, because a pre-existing user copy must
  not become something a later `remove` deletes.
- The plugin carries everything that install needs: the `installer/` package,
  the machine payload in target-relative layout, its gating `partition.json`
  copy, and a `bin/sd-machine-install` bootstrap (84 committed plugin files to
  215). Skill and command text that named repository-root resources is
  rewritten on the way into each payload — to bare `bin/` commands for the
  plugin, to `~/.agents/bin` and `~/.agents/docs` for the machine payload — by
  one shared implementation in `installer/references.py`, with residue and
  dependency-closure gates that fail the build when a payload would ship an
  instruction naming a file it does not carry.
- `sd-ai-command-pack-pack-update.sh` is the single machine update action:
  update the plugin, resolve the *new* plugin root from
  `claude plugin list --json` (never the running script's own location, which
  lives in the old root), install from there, then report both versions. Both
  halves are idempotent and the receipt only advances on success, so an
  interrupted update shows as version skew and a rerun converges.
- `sd-status` gains an advisory machine-scope line comparing the receipt
  against the installed plugin. Any plugin-discovery failure — no CLI, a
  nonzero exit, unparsable output, a missing or duplicated entry — reports
  `unavailable`, and the comparison is `unknown` whenever either side is
  unavailable, so a broken `claude` can never present as up to date. A
  malformed receipt is `invalid` and joins the other anomalies rather than
  reading as "not installed".
- Platform dispositions in `docs/fleet/surface-partition.json` are now
  evidence-backed. `gemini`, `opencode`, and `shared` cleared executed
  user-scope probes against the installed CLIs and are no longer provisional;
  `codex` is re-dispositioned `repo-native`, because it resolves `.agents`
  against the project root and never reads `~/.agents/skills`. `shared`
  carries the new additive `retainVendoredFor: ["codex", "pi"]`, which tells
  migration tooling to keep those rows vendored for any consumer whose fleet
  registry row serves either platform.
## 0.64.34 - 2026-08-09

- Skill frontmatter now pins a cost-appropriate Claude model tier where the
  workload is mechanical: `model: haiku` on the read-only reporting skills
  (`sd-status`, `sd-help`) and `model: sonnet` on the procedural flow skills
  (`sd-check`, `sd-start`, `sd-continue`, `sd-create-pr`, `sd-finish-work`,
  `sd-housekeeping`, `sd-update-deps`, `sd-fleet-refresh`, `sd-retro`,
  `sd-review-learnings`). Judgment-heavy skills (reviews, audits, CI fixes,
  `sd-ship`, `sd-work-backlog`, `sd-update-spec`, `sd-test-gaps`,
  `sd-full-check`) keep no `model:` field and inherit the session model, both
  to preserve verdict quality and to avoid prompt-cache invalidation on long
  orchestration turns. Non-Claude platforms ignore the extra frontmatter key.

## 0.64.33 - 2026-08-09

- The Claude-side pack surface now also ships as a Claude Code plugin.
  `.github/scripts/generate-plugin.py` builds the committed `plugins/sd/`
  tree from the `machine-claude` slice of `docs/fleet/surface-partition.json`
  joined to `manifest.json`: skills, the flattened `/sd:*` command surface
  (plugin name `sd` preserves the invocation), and the shared pack scripts as
  `bin/` executables. A repo-root `.claude-plugin/marketplace.json` catalogs
  it, `plugin.json` `version` is stamped from `manifest.json`, and the
  generator fails closed on a missing source row, unreadable source, unmapped
  kind, rewrite residue, empty version, or an unresolvable command reference.
  `.claude/rules/**` stays consumer configuration and is not in the plugin.
- Pack scripts now resolve sibling helpers from their own file location
  instead of a repository-root `scripts/` literal, so the payload works
  unchanged in a vendored install, the plugin cache, or a machine install. Fat
  installs are behavior-compatible — in a vendored layout the script directory
  *is* `scripts/` — with one deliberate hardening: the current working
  directory is no longer consulted, so a consumer file cannot shadow a pack
  helper. `sd-ai-command-pack-toolchain.sh run` / `run-python` accept the same
  bare and `scripts/`-prefixed pack-script arguments as before.
- `sd-review` now completes the documented local-rebuttal flow. Rerunning the
  same attempt with `--local-disposition` reaches the local stage even when the
  attempt already cached a report, so the rebuttals are applied to the stored
  receipt and persisted, and a local stage whose findings are all dispositioned
  (`disposition.outstanding == 0`) routes exactly as a clean one does instead of
  blocking forever on the immutable `findings` outcome. Findings left
  outstanding still block, and a receipt that is unreadable — or that reports
  findings while listing none for anyone to inspect — fails closed.
- Release gating now treats `plugins/**`, `.claude-plugin/marketplace.json`,
  and `.github/scripts/generate-plugin.py` as shipped payload in both
  classifiers (`prepare-release.py` and the `run_pack_source_drift_gates`
  release version gate), so plugin changes require a manifest version bump and
  a matching changelog heading. `make release-prep` regenerates the partition
  artifact and the plugin, then fails closed when the plugin and pack versions
  disagree. CI validates the built plugin with a pinned
  `claude plugin validate plugins/sd --strict`.
- The installed guide gains a "Claude Code plugin and private marketplace"
  section covering marketplace add/install, private-repository access via
  `gh auth setup-git`, `CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE=1` for
  background auto-update failures, and CI cache pre-seeding through
  `CLAUDE_CODE_PLUGIN_CACHE_DIR`.

## 0.64.32 - 2026-08-09

- `sd-status` now inventories the repository's Git worktrees. The
  collector enumerates `git worktree list --porcelain -z` (NUL-delimited,
  newline-safe for externally controlled paths) into an additive
  `git.worktrees` JSON block — per-row path, branch or detached HEAD,
  bare/locked/prunable flags, cleanliness, and a `current` marker for the
  reporting checkout — plus a `git.branchesHeldElsewhere` list of local
  branches checked out in another worktree. Human output gains a
  `==> Worktrees` section (explicit `linked worktrees: none` /
  `worktrees: unavailable` states) and marks held branches with
  ` [worktree]` in the local-branches line. Cleanliness probes run
  `git --no-optional-locks status` only after verifying the probed path
  still belongs to this repository (common-dir identity check), so a
  stale path reused by an unrelated repository reports `clean: null`
  instead of the stranger's state. Read-only throughout; the
  recovery-artifact classifier and its receipt-based ownership semantics
  are unchanged, and `--json` stays schema version 2 (additive keys).

## 0.64.31 - 2026-08-08

- Enrich every git-caused `*_unavailable` finding in the bookkeeping
  review preflight with the failed git command, its exit status, and
  bounded stderr (first line, 200 chars). A module slot captures the most
  recent `bookkeepingChangedEntries` diff failure for the silent-probe
  history recoveries; direct-status sites (rev-list histories, the
  successor subject probe, whitespace validation, the planning-recovery
  parents probe) append the same detail inline. Diagnostics only: reason
  codes, receipt schema, statuses, and dispositions are unchanged. This
  targets the kcov-lane flake of
  `test_completion_successor_finds_recent_anchor_in_long_history`, whose
  receipts discarded the underlying git error.
- Test fixtures: unexpected git failures in the `run_git`/`git_output`
  assertion wrappers now append a bounded repo-state context block (HEAD
  bytes, loose/packed ref state, lock files) so the fixture-side
  `fatal: could not parse HEAD` fingerprint carries discriminating
  evidence at its next occurrence.

## 0.64.30 - 2026-08-08

- Add a review-preflight rule for root-task `base_branch`: a changed active
  task record with no parent must target the repository default branch or
  carry a recorded `meta.base_branch_exemption` reason. The default branch
  resolves from the new `SD_AI_COMMAND_PACK_DEFAULT_BRANCH` variable (CI
  exports it from the event payload, since a pinned-SHA checkout never
  establishes `origin/HEAD`), then from the `origin/HEAD` symbolic ref, and
  the rule skips itself when neither source resolves. Twice a root task
  recorded the feature branch it was authored on as its PR target, passed
  the deterministic gate, and was caught only by a paid review round.
- Correct the four active root-task records still naming dead feature
  branches as `base_branch`; all now target `main`. These are data fixes
  independent of the rule and are not meant to be reverted with it.
- Pin the description-emptiness predicate divergence between the JavaScript
  gate (`String.trim()`: strips U+FEFF, keeps U+0085) and Python create side
  (`str.strip()`: the exact opposite) in tests, and require `--description`
  in the pack-owned documented `task.py create` example. The create-time
  refusal itself is parked on the Trellis fork
  (`08-08-create-empty-metadata-rejection`) via the upstream handoff
  register.

## 0.64.29 - 2026-08-08

- Upgrade the vendored Trellis surface from 0.6.7 to 0.6.14 via the official
  `trellis update` mechanism. `.trellis/scripts` is byte-identical to the
  0.6.14 release templates; `task.py create` on a feature branch now seeds
  `base_branch` from the repository default instead of the checked-out branch.
- Adopt `task.py current --json` in the status collector
  (`sd-ai-command-pack-status.py`), with a prose-path fallback for consumer
  repositories still on Trellis <=0.6.7 that reject the flag.
- Teach the record-session wrapper (`sd-ai-command-pack-record-session.py`)
  to insert the Testing / Next Steps journal sections when absent: Trellis
  >=0.6.14 omits sections scaffolded empty by <=0.6.7.

## 0.64.28 - 2026-08-08

- Let `stop` retire a paused work-loop run. `pause` releases the ownership lock
  by design, but `stop` reached `require_lock` through `mutate_state` and
  demanded one back, so a paused run could not be stopped at all — it failed
  with `work-loop state does not exist: .../lock.json`, naming the lock file
  through the generic state-read error. The only way out was a
  `start --run-id` resume purely to re-take a lock that the very next command
  would drop again, which also flips the run back to `active` and rewrites the
  checkpoint on the way through. Observed retiring run
  `d23a9c7f5f7447fd8ec5059776ed27f7` in a consumer repository.
  `mutate_state` now takes `released_lock_statuses`, and the commands that act
  on an already-unlocked run pass it.
- The same defect blocked `reconcile`, which is worse: `references/run-recovery.md`
  routes a stopped or red run *to* `reconcile`, so the documented recovery path
  could not be walked at all. Reconciling a real retired run failed with the
  same `work-loop state does not exist: .../lock.json`. `reconcile` now passes
  the allowance too.
- `stop` runs `release_lock` unconditionally after its mutation, so every
  status it can set — `paused`, `stopped`, and `completed` — ends lockless, not
  just `paused`. `LOCK_RELEASING_STATUSES` names all three. `active` is
  deliberately absent: a live run still owns its lock, so an active run whose
  lock vanished still fails exactly as before, and omitting the parameter keeps
  the strict default for every other `mutate_state` caller.

## 0.64.27 - 2026-08-07

- Close three helper defaults that fight the pack's own gates. Each produced a
  wrong or destructive result on its documented invocation; all three surfaced
  in a single downstream shipping session.
- `record-session`: recording a session without `--commit` wrote
  `add_session.py`'s "(No commits - planning session)" placeholder, and the
  final-bundle validator then rejected that same session with
  `journal_commit_missing`. The documented command produced an artifact the
  documented validator always refuses. Omitting `--commit` now derives the
  unrecorded work commits on HEAD — stopping at the first commit a journal
  already cites, and skipping commits confined to `.trellis/workspace` so
  journal and index commits never nominate themselves. It declines, preserving
  the previous behavior, whenever the answer is not obvious: nothing to record,
  git unavailable, no recorded boundary inside the scan window, or more
  candidates than one session plausibly covers. `--commit -` still asserts
  "genuinely none".
- `pr-eligibility`: the probe never derived a repository slug. It reported
  `github_repository_unavailable` with the diagnostic "could not derive GitHub
  repo from origin" — claiming an attempt that never happened — on every
  repository with an SSH remote, including ones whose merge gate resolves the
  slug fine, since `housekeeping.sh` has carried
  `github_repo_from_remote_url` all along. The probe now derives from
  `git remote get-url` with a parser held to byte-for-byte parity with that
  shell twin, `${slug%.git}` then `${slug%/}` ordering included, and reports
  the derived slug in its evidence.
- `review-learnings`: the managed block is rendered wholesale from whatever
  GitHub scope the run requested, so `--github-pr N` — the form `sd-ship`'s
  Stage 2b prescribes for the post-cycle pass — renders a block holding only
  that PR's clusters. Applying it replaced a repository-wide snapshot with one
  PR's signals; observed against a real snapshot, five clusters and 38
  task-metadata comments would have collapsed to a single comment. An update
  that would delete clusters already recorded in the snapshot is now refused,
  naming them, with `--allow-narrowing` to accept the deletion deliberately.
  Scan and `--dry-run` are unaffected, so the documented Stage 2b invocation
  never trips it.

## 0.64.26 - 2026-08-07

- Give verified-false local review findings a rebuttal channel. `sd-review`
  instructs the caller to verify every finding and to rebut rather than comply
  when one is wrong, but only the remote stage could act on that:
  `--remote-disposition <id>=rebutted` had no local counterpart. A local
  provider false positive therefore held `remoteGate:
  actionable-local-findings` shut with no way past it short of editing the file
  the provider misread. `--local-disposition <stable-id>=rebutted` closes that,
  with the same grammar and the same single accepted value. A rebutted finding
  stays in the receipt as `rebutted` under `disposition.localDispositions`, so
  the judgement remains auditable; the gate now blocks on findings left
  outstanding rather than on the provider's aggregate outcome, while a provider
  reporting findings but listing none still blocks. An id matching no finding
  at that head is an error rather than a silent no-op, because stale ids copied
  from an earlier head are the way this would otherwise go wrong. Observed on
  PR #353, whose diff is four `.trellis/tasks/` files and no code at all: the
  provider read the PRD's quoted `add_session.py` excerpts as the PR's own
  source and re-reported the documented defects as new ones, then reported a
  misspelling of a word spelled correctly at the cited line and absent from the
  repository entirely.

## 0.64.24 - 2026-08-06

- Stop excluding `.trellis/workspace/**` from the Gito local-review scope.
  0.64.21 narrowed the blanket `.trellis/**` exclusion so a task-only or
  spec-only change would still reach the provider with a non-empty diff, but it
  kept `.trellis/workspace/**` out of scope alongside `.trellis/tasks/archive/**`
  as bulk bookkeeping. Those two globs are precisely what a finalization commit
  range consists of: a completion bundle is an archive move plus a journal
  session, and a planning bundle is journal-only. Every finalization PR
  therefore reached Gito with nothing in scope, which exits 0 without a
  structured report and surfaces as `local provider failure blocks remote
  routing` — with no public combination of `local=` and `remote=` able to
  complete, because an absent optional router requires a *clean* local receipt.
  Observed on PR #346, whose eight changed paths were all under
  `.trellis/tasks/archive/**` or `.trellis/workspace/**`. The journal and its
  index are the only paths every finalization touches, so keeping them
  reviewable makes that class of PR non-empty by construction; the diff is one
  appended session rather than the whole file, unlike the archive move, which
  re-sends whole historical documents and stays excluded. Moves the glob from
  the test's required-exclusion list to its forbidden list so the contract is
  pinned from both sides.
- Note: this is the exclusion-list layer, not the underlying defect. Task
  `08-06-local-provider-empty-scope` records that an all-excluded diff should be
  a distinct typed outcome rather than a provider failure — a property of the
  coordinator that no exclusion list can fix for every repository.

## 0.64.23 - 2026-08-06

- Require `< /dev/null` on the `codex exec` invocation in the planning
  adversarial-review contract. In a background Bash task stdin is not a TTY, so
  `codex exec` treats it as piped input, prints `Reading additional input from
  stdin...`, and blocks indefinitely on a write that never arrives. It burns no
  CPU while hung, so the run reads as slow rather than stuck, and its fully
  buffered output means it emits nothing at all. Documents the near-zero-CPU
  signature that distinguishes the trap from a genuine failure, notes that a
  working foreground probe does not clear the background lane, and states that
  reporting such a run as `Codex: failed` records an absent second opinion as an
  attempted one.

## 0.64.22 - 2026-08-06

- Downgrade `sd-check`'s `knowledge.obsidian-kb` freshness row to advisory when
  `.obsidian-kb` is an absolute symlink to a vault outside the repository. That
  vault is gitignored, never shipped, and mutates independently of repo HEAD, so
  `update-spec-kb.py --check` fails non-deterministically against it — and the
  review coordinator memoizes the transient failure against a state key that
  excludes the gitignored artifact, false-blocking a merge gate whose GitHub
  checks are green. Observed on `platypeeps/anomaly-metric-creator` #316 and
  #325.
- The downgrade is narrow. A new `_is_external_symlink(kb_root, repo)` helper is
  true only when `kb_root` is a symlink whose `resolve(strict=False)` target
  lands outside the repository tree. Only a *failing* row for such a path
  becomes a non-blocking `skipped`, preserving its original `diagnostic`,
  `remediation`, `exitCode`, `command`, and `durationMs`; `skipped` is absent
  from `AGGREGATE_PRECEDENCE`, so it never contributes to the blocking verdict.
  A passing row stays `passed`. In-repo symlinks and real tracked directories
  are deterministic against HEAD and keep blocking, which also closes the
  `is_symlink()`-alone hole. A broken link resolves to its declared target:
  external becomes advisory, in-repo keeps blocking so the breakage surfaces.

## 0.64.21 - 2026-08-06

- Narrow the Gito local-review exclusion for `.trellis/`. The single
  `".trellis/**"` entry excluded every Trellis path, including the authored
  delivery documents the repository owns. A change confined to task or spec
  Markdown therefore left the provider an empty diff: Gito exited 0 without a
  structured report, `sd-review` classified that as a provider failure, and —
  because an absent optional router requires a *clean* local receipt — the
  review stage could not complete by any combination of `local=` and `remote=`
  controls. Observed on PR #339, whose four changed paths were all under
  `.trellis/tasks/`.

  The exclusion is now the copied/generated boundary rather than the whole
  directory, matching `isTrellisCopiedPath` in the review preflight:

  - still excluded: `.trellis/.template-hashes.json`, `.trellis/.version`,
    `.trellis/scripts/**`, `.trellis/agents/**` (copied Trellis surfaces), plus
    `.trellis/tasks/archive/**` and `.trellis/workspace/**` (bulk bookkeeping —
    1450 archived files and append-only journals, where review spend buys
    nothing).
  - now reviewable: active `.trellis/tasks/**` artifacts and `.trellis/spec/**`.

  Consequence to expect: task- and spec-only changes now cost a local provider
  round they previously skipped, and Gito may raise findings on PRD, design,
  implementation-plan, and spec prose it never saw before.

  `.gito/config.toml` installs `if-not-exists`, so an existing consumer keeps
  its current file; apply the same narrowing by hand to opt in.

## 0.64.20 - 2026-08-06

- Consolidate user-local state-root resolution into the shared library (A-046).
  `resolve_state_root` and `ensure_private_directory` now exist exactly once, in
  `sd_ai_command_pack_lib`, and the four modules that owned private state
  (`work-loop`, `recovery-artifacts`, `fleet-timing`, `fleet-controller`) bind
  thin wrappers that restate the shared failure in their own error type. Every
  existing call site is untouched. A new AST boundary test
  (`test_state_root_boundary.py`) enforces the single-definition invariant.

  Two behavior changes follow from the shared ladder:

  - `SD_AI_COMMAND_PACK_STATE_HOME` now moves *every* private state surface,
    not only the work-loop ledger. `fleet-timing` and `fleet-controller`
    previously ignored it.
  - `recovery-artifacts`' directory creation no longer lets a raw `OSError`
    escape; it raises `RecoveryError` like every other failure in that module.

  **Operator action — one-time state move.** The fleet subdirectories change
  root when the resolved root changes. Nothing is read from the old location;
  there is no fallback path. Perform the move with **no fleet operation in
  flight** (no active campaign, no running timing run).

  On POSIX with `SD_AI_COMMAND_PACK_STATE_HOME` unset, nothing moves — the
  `XDG_STATE_HOME` and home rungs resolve to the same place as before.

  If you set `SD_AI_COMMAND_PACK_STATE_HOME=<new-root>`:

  ```sh
  mkdir -p "<new-root>"
  mv ~/.local/state/sd-ai-command-pack/fleet-timing "<new-root>/fleet-timing"
  mv ~/.local/state/sd-ai-command-pack/fleet-campaigns "<new-root>/fleet-campaigns"
  # Rollback — reverse both moves:
  # mv "<new-root>/fleet-timing" ~/.local/state/sd-ai-command-pack/fleet-timing
  # mv "<new-root>/fleet-campaigns" ~/.local/state/sd-ai-command-pack/fleet-campaigns
  ```

  On **Windows the campaign state moves even with the variable unset**:
  `default_state_home` had no local-app-data branch, so campaign state lived
  under the home root while every other surface used `%LOCALAPPDATA%`. It now
  follows the shared ladder to
  `%LOCALAPPDATA%\sd-ai-command-pack\state\fleet-campaigns`, so move
  `%USERPROFILE%\.local\state\sd-ai-command-pack\fleet-campaigns` there
  (and reverse it to roll back).

## 0.64.19 - 2026-08-05

- Consolidate git subprocess invocation into the shared library (A-076).
  Every git-specific subprocess environment builder now routes through the
  shared `sd_ai_command_pack_lib` helpers — `run_git_minimal` for the
  prompt-disabled, cache-free path and `run_git_cached` for the cache-backed
  path — so no shipped script hand-builds a git-specific environment of its
  own. Six scripts were migrated off inline git subprocess calls
  (`review-local`, `surface-check`, `install-audit`, `work-loop`,
  `fleet-controller`, `fleet-publish`), each preserving its original stream,
  decoding, and timeout semantics. A new AST boundary test
  (`test_git_invocation_boundary.py`) enforces the invariant: only the shared
  library may build a direct git subprocess call, and the migrated files carry
  no git-argv literal at all. Behavior is unchanged; the payload change is the
  invocation-site consolidation.

## 0.64.18 - 2026-08-05

- Cut the per-check-row worktree re-hash in `sd-ai-command-pack-check.py`
  (A-101, R1/R2). Each check run snapshots the tree many times — before the
  checks, after every executed row, and once at the end — and previously
  re-read and re-hashed every tracked and guarded file's content on each
  snapshot, so hashing cost scaled with the number of check rows. A per-run
  content-hash cache now keys each regular file's content digest by a cheap
  `(st_mode, st_size, st_mtime_ns)` signature: unchanged files are hashed once
  and reused across snapshots, so the run performs exactly two full content
  passes — the cold pass that fills the cache and the deliberately cache-free
  final pass — regardless of row count. The cache is per-run and never
  persisted, and no metadata-only or `git status`/index digest is substituted
  for real content hashing. **Run-level granularity trade:** the cheap
  signature cannot see a same-size, mtime-preserving rewrite that happens
  between rows, so a per-row snapshot can miss it and no longer attribute the
  mutation to a specific check row. The run's final snapshot runs against a
  fresh cache and re-hashes from scratch, so it still fails the run for all
  three mutation classes (ordinary edit, symlink retarget, and the same-size
  mtime-restored rewrite); only per-row attribution for that one case is
  traded away. Symlinks are always read fresh, so every retarget is still
  caught at every snapshot.
- Cut the payload-size classifier cost in `sd-ai-command-pack-pr-body-scope.py`
  (A-105, R3). Each `ScopeRule` now partitions its normalized patterns once at
  construction into a `frozenset` of metacharacter-free literals and a tuple of
  globs; the classifier tests set membership before iterating the glob matcher,
  so per-path work tracks the changed diff rather than the installed payload
  size. Classification output is byte-identical. The root cause of the scaling,
  found by profiling, was not the glob scan but the dict-key hash: `_classify`
  uses each frozen `ScopeRule` as a `dict` key and hashes it once per matched
  path, and the generated dataclass `__hash__` rehashed the whole `patterns`
  tuple every call — making classify O(paths × patterns). The rule now caches its
  value hash once in `__post_init__` and returns it from an explicit class-body
  `__hash__`, collapsing per-lookup hashing to O(1) while leaving equality and the
  hash *value* unchanged. Measured `_classify` growth over a fixed 50-path diff
  drops from 2.98× (180→720 installed targets) to a flat 0.99–1.02× per doubling,
  inside AC3's 1.2× bound.

## 0.64.17 - 2026-08-05

- Unify the `outcome`/`status` vocabulary across emitted payload envelopes
  (A-077). One rule now holds at the top level of every emitted document: the
  `outcome` key carries a verdict and `status` is reserved for an embedded
  sd-status document. `sd_ai_command_pack_lib.py` owns the shared verdict core
  `VERDICT_CORE = {clean, blocked, skipped, failed}` and a `declare_verdict_domain`
  helper; the four multi-valued domains (`housekeeping`, `review-local`,
  `fleet-stage`, `fleet-consumer`) derive their sets from the core with explicit,
  named opt-outs, so a value cannot silently diverge across payloads while a
  legitimate domain verdict such as `findings` or `at-target` is still allowed.
  Declaring a non-core verdict without an opt-out now fails at import time.
- Resolve the one genuine single-document collision: the housekeeping result's
  embedded enum `outcome.status` is renamed to `outcome.verdict`, so
  `result["status"]` (the sd-status document) and `result["outcome"]["verdict"]`
  (the enum) no longer both spell `status` with different value types. The
  review-local stage report converges its top-level verdict from `status` onto
  `outcome`. Both renames ship additively: the old keys are still emitted for one
  release and are recorded in `DEPRECATED_PAYLOAD_KEYS` with
  `removed_version 0.66.0`. The shipped `sd-housekeeping` skill prose and
  `docs/SD_AI_COMMAND_PACK.md` are updated to name `outcome.verdict` in the same
  change so an agent never follows stale prose. `"ok"`/`"recorded"` keep their
  distinct spellings with a recorded justification (no consumer reads them). The
  exact-payload fleet ledger refreshes via the normal release fleet run.

## 0.64.16 - 2026-08-05

- Consolidate the three copies of `atomic_write_text`/`default_text_file_mode`
  into `sd_ai_command_pack_lib.py` as the single owner (A-085). The hardened
  67-line writer from `sd-ai-command-pack-review-learnings.py` — cross-device
  guard, parent-directory fsync, and an optional `revalidate` TOCTOU callback —
  now backs the session recorder and knowledge-base writers too, replacing their
  31-line copies. The two added guards fail by raising `OSError`, the same
  exception the pre-existing symlink refusal already produced, so no call site
  needed new error handling.
- Make the tool-cache environment key set data-driven end to end (A-080).
  `CACHE_ENV_KEYS` in the library is the single authority, but seven shell sites
  re-encoded the list: two `case`-glob allowlists, two magic arity assertions
  (`-ne 7`/`-eq 7`), and the `doctor` JSON heredoc's positional args, its
  hand-built `cache_paths` dict, and the human-readable `printf` block. All now
  derive from the library's `cache-env` output — validated generically as an
  environment-variable name with a non-empty value — so adding a cache variable
  needs no shell edit. Operator-facing text and `doctor --json` shape are
  unchanged; verified by adding a dummy eighth key to the library alone and
  observing it flow through `cache-env`, `doctor --json`, and `doctor`.
- The remaining two clusters of task `07-28-consolidate-shared-script-helpers`
  are split into follow-up tasks: state-root resolution (A-046) is a live-state
  relocation needing a recorded migration decision, and git invocation (A-076)
  needs a library git path that preserves the minimal-environment,
  prompt-disabled, binary-capable contract without coupling to cache setup.

## 0.64.15 - 2026-08-05

- Consolidate the two divergent secret redactors behind one shared shape set.
  `sd_ai_command_pack_lib.py` and `sd-ai-command-pack-fleet-timing.py` disagreed
  about what a secret looks like: the lib's `_ENVIRONMENT_SECRET_RE` missed
  fine-grained GitHub PATs (`github_pat_…` — `gh[pousr]_` excludes the `i`),
  Slack tokens, `sk-` keys, PEM private-key blocks, and most `key: value`
  shapes, so those leaked verbatim into agent-visible `environment_blocked`
  diagnostics. Both consumers now derive from one `_SECRET_SHAPES` table, but
  keep their asymmetric policies: the lib **substitutes** (fail-open — never
  drops the diagnostic recovery depends on) and fleet-timing **rejects**
  (fail-closed — refuses secret-shaped input). Each shape carries a loose
  detector form and a conservative substituter form with a body charset and a
  minimum length, so redaction never leaves a secret body behind (a prefix-only
  substituter would have been worse than the old redactor); the PEM row spans
  the whole block to its `-----END … PRIVATE KEY-----` footer, and falls back to
  a bounded span from the `BEGIN` header when the footer is missing so a
  truncated key body cannot leak; the `sk-` prefix is token-boundary anchored so
  ordinary hyphenated words are not over-redacted; and the key-value substituter
  is bounded so surrounding diagnostic context survives.
- Wire the orphaned `validate_environment_blocked_evidence` and the `cache-env
  --json` blocked-evidence path into production. `configure_cache_environment`
  in `sd-ai-command-pack-toolchain.sh` now re-invokes `cache-env --json` on a
  cache-setup failure (the success path keeps its `key=value` contract intact)
  and fails with the structured, validated `recoveryAction` instead of a
  duplicated hardcoded prose string, and stops discarding the underlying
  `error:` text.

## 0.64.14 - 2026-08-05

- Clarify fleet rollout PR audit scope so pack-owned receipt/provenance
  coverage is distinguished from Trellis-owned adapter validation. The install
  audit and `provenance.json` vouch pack-owned receipt targets only (the files
  in `installed-targets.txt`); a Trellis-owned platform adapter that becomes
  newly tracked when a consumer relaxes its ignore policy is never added to the
  pack manifest, receipt, or provenance to widen that vouch — it stays outside
  the pack-vouched set and is covered by the fleet review classifier's
  integration-only eligibility (which forces the normal remote-review loop for
  any changed path missing from the receipt) plus the consumer's own
  integration/readiness checks. `docs/SD_AI_COMMAND_PACK.md` and
  `docs/FLEET_ROLLOUT.md` state which check validates each ownership class, and
  a new `test_newly_tracked_trellis_adapter_stays_outside_pack_vouch` locks the
  classifier behavior in. Docs only; no shipped-script behavior change.

## 0.64.13 - 2026-08-04

- Parallelize `sd-status fleet` collection. `collect_fleet` collected each
  consumer serially, stacking per-repo subprocess and 20s network-timeout
  latency (a 10-20 repo fleet cost 15-40s). It now maps `collect_local` over
  the consumers in a bounded `ThreadPoolExecutor` (`min(8, len(consumers))`
  workers — the useful ceiling tracks git/gh concurrency, not CPU cores),
  so wall time floors at `ceil(consumers / workers)` waves instead of the
  serial sum. `ThreadPoolExecutor.map` yields in input order, so registry
  rollout order and per-row content are unchanged. A consumer whose
  `collect_local` raises is now isolated to its own degraded `unavailable`
  row instead of aborting the whole run; `KeyboardInterrupt` still propagates
  and in-flight subprocesses finish or are killed by their existing
  per-command timeouts. No cancellation contract, per-command timeout, or
  output shape changed.

## 0.64.12 - 2026-08-04

- Bound `sd-review-learnings` unsafe planning changed-path evidence to a
  phase-tagged diagnostic instead of an uncaught `ValueError` traceback. The
  main scan path's `build_review_learning_signal` call was unguarded, so a
  `--github-pr N --dry-run` run over a diff whose changed path escaped the
  repository (traversal, control characters, oversized, or over-count) exited
  with a Python traceback (observed in `platypeeps/people-profiles` PR #3). It
  now routes that expected invalid-evidence failure through the existing
  `_print_early_failure` emitter under the `sd-review-learnings:planning`
  phase, matching the already-guarded `--planning-attempt` path: a stable
  diagnostic that never echoes the raw unsafe path, the documented failure exit
  code, and a schema-valid bounded report in `--json` mode. Added CLI
  regression coverage for traversal (human mode) and control-character (JSON
  mode) inputs.

## 0.64.11 - 2026-08-04

- Batch `sd-review-learnings` review-thread collection into aliased GraphQL
  queries (up to `GITHUB_REVIEW_THREAD_BATCH_SIZE = 20` PRs per request)
  instead of one `gh` subprocess per PR, cutting a documented
  `--github-days 2 --update` run from ~30-45 serial GraphQL spawns to
  `ceil(N / 20)`. Aliased batching widens the failure domain, so a whole-batch
  failure (gh exits non-zero on a top-level `errors` array) or a per-alias
  `null` (partial failure) falls back to the pre-batch single-PR query for the
  affected PRs — one PR never drops the rest. Per-PR truncation and input
  ordering are preserved; identical learnings output on a fixed PR window.
  Tactical fix pending the parked reviewer-generalization rework, which will
  replace this collection path entirely.

## 0.64.10 - 2026-08-04

- Classify `.claude/hooks/*` as a copied/generated Trellis runtime surface in
  the JavaScript review-preflight classifier, matching the shell review-scope
  classifier that already listed it. Previously a change under `.claude/hooks/`
  was scoped as copied by the shell classifier but treated as source by the
  `mjs` preflight, so the two review-scope surfaces disagreed on platform hook
  paths. Added paired parity coverage (shell advisory + `copiedTemplateKind`)
  so they cannot silently diverge again for that path. No behavior change for
  any other surface.

## 0.64.9 - 2026-08-04

- Register the `fleet-refresh.operator-policy` structured-question decision and
  bind it to `sd-fleet-refresh`. The skill prose already specified the ask /
  do-not-ask rule, the lowest-risk-park recommendation, and the noninteractive
  park behavior; the gap was purely registry-side, so generated adapters could
  not expose host-native guidance at that boundary. The decision uses three
  static, mutually-exclusive dispositions for a blocked campaign — park (default),
  retry the blocked consumer, or continue without it — with `noninteractive="park"`.
  Claude and Gemini adapters now name their native question capability;
  the neutral skill body stays host-agnostic. No controller, receipt-vocabulary,
  or state-machine change.

## 0.64.8 - 2026-08-04

- Add `agent` as a first-class manifest artifact kind, gated by a per-platform
  subagent capability (`agent_kind` + `agent_target_pattern` on `PlatformInfo`,
  modeled on the existing `command_kind` pair). Platforms without the capability
  produce zero agent rows by construction; the capable wave-1 set is claude,
  codex, and gemini, read from the registry so later platforms are additive
  rows. The generator renders Markdown agents verbatim, renders codex to a TOML
  twin, enforces the `sd-` name prefix (a `trellis-*` name would leave pack
  management), and constrains gemini's tool set. Plumbing only: the pack ships
  zero agent bodies, so the manifest is byte-identical until an agent source
  exists.

## 0.64.7 - 2026-08-04

- Add a per-job dispatch protocol to the `sd-fix-ci` skill (Tier 1 pilot of the
  SD dispatch pattern). CI triage now fans out one read-only sub-agent per
  failing job — each fetching only its own
  `gh run view -j <job-id> --log-failed` output — so the parent context stops
  absorbing every job's full log. Workers return a typed
  `real-code | flake | infra | stale-baseline`
  classification with quoted evidence and a proposed disposition; the parent
  keeps job enumeration, run-level fact resolution, the shared `max-reruns`
  budget, all fixes/reruns, and the unchanged report contract. On inline
  platforms the fallback collapses to today's sequential pass with an identical
  outcome (R5). Fan-out is bounded to waves of at most six concurrent workers,
  and each dispatch prompt restates the command's already-resolved
  `checkout-trust` state without duplicating the generator-owned classifier.

## 0.64.6 - 2026-08-04

- Simplify completion-successor anchor assignment in
  `sd-ai-command-pack-review-preflight.mjs`: the recovery loop's
  `nearestAnchorFailure === null` guard was redundant — the loop always breaks
  the first time it reaches that assignment, so the guard was invariably true.
  Replaced with a direct `nearestAnchorFailure = anchor;`. Behavior-preserving;
  the invalid-anchor diagnostic (`completion_successor_anchor_invalid`) is
  unchanged and still covered by its focused regression tests. Canonical
  template edited first, root installed mirror kept byte-for-byte identical.
  Follows up code-quality feedback from `platypeeps/rwbp-coordinator` PR #177.

## 0.64.5 - 2026-08-04

- Three pack-source follow-ups surfaced by the 0.64.4 fleet rollout. All are
  hardening of the pack's own tooling; none change any consumer's installed
  payload behavior.
- Sibling-loader diagnostics (A): the unsafe-sibling loader in
  `sd-ai-command-pack-status.py` and `sd-ai-command-pack-surface-check.py` now
  maps `ENOTDIR` (a non-directory parent component ⇒ the module is unresolvable
  at the computed path) to reason `missing` rather than `non_regular`, in BOTH
  the advisory `lstat` branch and the authoritative `O_NOFOLLOW`-open branch, so
  an unresolvable path reads as "not installed" instead of "present but refused".
  Fail-closed refusal is unchanged; only the diagnostic reason/message differs.
- fleet-publish archive resilience (B): `sd-ai-command-pack-fleet-publish.py`
  now fails loudly on a non-zero `task.py archive` result — raising a
  `PublishError` that names the likely transient `.git/index.lock` cause and the
  exact recovery (the task may be moved on disk and staged but uncommitted;
  resolve `git status` or re-run the fleet action). It attempts no rollback,
  because the archive also flips task status, detaches children, and clears
  sessions before the move, so a dir-only undo would corrupt state. The
  framework-level commit-retry (which belongs in Trellis-owned `task_store.py`,
  not shipped by this pack) is handed upstream to the Trellis source owner.
- fleet-publish self-publish guard (C): `sd-ai-command-pack-fleet-publish.py`
  now refuses to run against a repo carrying the completion-mode bookkeeping gate
  (`.github/scripts/bookkeeping_ci_scope.py`) — including this pack repo itself —
  exiting with the precondition failure code and directing self-publish to
  `sd-finish-work`. The fold pattern trips that gate; fleet-publish is
  consumer-only, now documented as such in `docs/FLEET_ROLLOUT.md` and the module
  docstring.

## 0.64.4 - 2026-08-04

- Fleet-rollout hardening from recent live campaigns. Six shipped fixes and a
  set of source-only rollout-tooling improvements, none of which change any
  consumer's installed payload behavior beyond the fixes below.
- Merge-eligibility (finding #2): `sd-ai-command-pack-pr-eligibility.py` now
  classifies a PR that GitHub reports as `BLOCKED` but `MERGEABLE`. A non-clean
  merge state is given an actionable diagnostic — `merge_blocked_conflicts`,
  `merge_blocked_out_of_date`, `merge_blocked_conversation`, `merge_blocked_review`,
  or `merge_state_not_clean` — instead of a blanket skip, while the state stays
  `blocked` and such a PR is still never reported merge-eligible.
- Review-preflight task-context gate (finding #5): a manifest whose only row is
  the untouched generated `_example` scaffold that `task.py create` writes is
  treated as unfilled/advisory at any task status or archival state. The prior
  `status === 'planning'` gate was too narrow and produced a late, merge-time
  `task_context_seed` failure on completion; a lone scaffold is now always exempt
  while an `_example` row mixed with real rows still fails.
- Review scope resolution (finding #6): `sd-ai-command-pack-review-scope.sh` now
  requests and requires `state` from `gh pr view` and ignores a CLOSED PR whose
  head is the same branch, so a stale closed PR body can no longer redirect the
  review scope of a fresh open PR on that branch.
- Housekeeping merge gate (finding #7): a read-only Obsidian KB target no longer
  hard-blocks a merge. The `.obsidian-kb` copy folder is a regenerable mirror, so
  an `EACCES`/`EROFS` refresh failure is recorded as an advisory skip with a fix
  command; every other refresh failure (corrupt vault, disk full, broken symlink)
  still blocks.
- Sibling-helper loader diagnostics (finding #11): `sd-ai-command-pack-status.py`
  and `sd-ai-command-pack-surface-check.py` now distinguish a genuinely missing
  helper from one that is present but refused (symlink / non-regular / no
  `O_NOFOLLOW`) via a `reason` code. The refusal behavior is byte-for-byte
  unchanged; only the surfaced diagnostic improves. `recovery-artifacts.py`
  reports the expected-versus-actual schema version on a version mismatch.
- Fleet-refresh procedure (`sd-fleet-refresh` skill): checkout-validation now
  asserts the dedicated task's `task.json` `description` is present and non-empty
  before advancing, a belt-and-suspenders guard against an upstream
  `task.py create` that tolerates an empty description; and the pr-publication
  stage now prescribes the new finish-work publish helper.
- Rollout tooling (source-only, not shipped to consumers): a new
  `sd-ai-command-pack-fleet-publish.py` folds a rollout's own finish-work into
  the already-reviewed PR head under allowlist/restore/delta guards and never
  pushes an invalid receipt; `sd-ai-command-pack-fleet-controller.py` adds
  merge-queue transparency (`heldBehind`/`queueNote`), a read-only
  `status --show-issued` action peek, validated operator-decision provenance, and
  an `--allow-parked-canary` opt-in; `sd-ai-command-pack-fleet-wave-plan.py`
  settles a parked canary only under that opt-in; and
  `sd-ai-command-pack-fleet-timing.py` accepts `canary`/`post-canary`/`final`
  cohort labels alongside raw integer priorities. `docs/FLEET_ROLLOUT.md` documents
  the campaign-state file layout, the Copilot-request recipe, the cohort labels,
  and the fresh-campaign redo recovery.

## 0.64.3 - 2026-08-03

- Harden the sibling-helper module loaders against a check-then-load (TOCTOU)
  race. `sd-ai-command-pack-status.py` (work-loop and recovery-artifacts
  loaders), `sd-ai-command-pack-surface-check.py` (`_load_source_module`), and
  the source-only `sd-ai-command-pack-fleet-controller.py` (`_wave_planner`) no
  longer stat a path and then re-resolve it with `exec_module`. Each now reads
  the helper source atomically on one `O_NOFOLLOW | O_NONBLOCK` descriptor with
  an `fstat` regular-file check, then executes the already-read bytes via
  `compile`/`exec` — `spec.loader.exec_module` is never invoked, closing the
  race at all four sites. An advisory `lstat` preserves each caller's existing
  classification (symlink / socket / FIFO / directory → the prior
  "unavailable"/raised outcome); genuine I/O errors, module metadata,
  `sys.modules` registration, and the status bytecode-write suppression are all
  behavior-preserved on valid inputs.
- Add `tests/test_helper_loader_safety.py` covering symlink and non-regular
  rejection (including a Unix socket and a mocked raced-symlink that exercises
  the authoritative `O_NOFOLLOW` branch), metadata parity, registration
  semantics, and an old-vs-new seam differential; rework the status helper-loader
  tests off the retired `importlib` seam onto real temporary helpers.

## 0.64.2 - 2026-08-03

- Decouple the `sd:fleet-refresh` command from installed-skill resolution. The
  source-only `sd-fleet-refresh` skill is never materialized under
  `.claude/skills/`, so resolving it by name failed everywhere and the command
  could not start. Step 1 now reads
  `.agents/skills/sd-fleet-refresh/SKILL.md` from the pack source checkout
  directly; the skill stays source-only (unchanged manifest, still
  unresolvable by name, same auto-invocation protection).
- Give the command-surface generator a per-command checkout-trust injection
  anchor (`CommandInfo.injection_anchor`). The generator previously required
  every command's step 1 to read "Resolve `<skill>` skill by name" to locate
  where it injects the checkout-trust policy; fleet-refresh's reworded step 1
  sets its own anchor, and the other commands are unaffected (surfaces
  byte-identical).

## 0.64.1 - 2026-08-03

- Harden the vendored, installer-managed recovery/status/update-spec scripts
  flagged by consumer reviewers during the 0.64.0 fleet refresh. Behavior is
  unchanged on valid inputs; the only new behavior is on malformed or unsafe
  failure paths (schemaVersion mismatch and symlinked-helper rejection now fail
  closed to `invalid`/`unavailable` instead of trusting the input):
  - Replace empty `except: pass` handlers in
    `scripts/sd-ai-command-pack-recovery-artifacts.py` and
    `scripts/sd-ai-command-pack-work-loop.py` with `contextlib.suppress(...)` /
    `Path.unlink(missing_ok=True)` so CodeQL `py/empty-except` no longer fires
    on the shipped copies.
  - Catch `UnicodeError` alongside `OSError` when reading receipts and cleanup
    locks in `sd-ai-command-pack-recovery-artifacts.py`, so an invalid-UTF-8
    file surfaces a bounded `RecoveryError` instead of an unhandled exception.
  - Read only the trailing marker bytes in
    `sd-ai-command-pack-update-spec-kb.py`'s `file_ends_with_kb_copy_marker`
    instead of loading the whole file.
  - Fail closed in `sd-ai-command-pack-status.py` `collect_recovery` when the
    dynamically loaded helper returns an unexpected `schemaVersion`, and reject
    symlinked helper modules in both recovery and work-loop import guards.

## 0.64.0 - 2026-08-03

- Ship the `sd` skill set to Claude Code's `.claude/skills/sd-*` surface (full
  parity with the other skill-fanout platforms). `claude` is now in
  `SKILL_FANOUT_PLATFORMS`, so consumers receive the 21 non-source-only sd
  skills as `.claude/skills/sd-<name>/SKILL.md` (+ references) via `manifest.json`,
  so Claude Code's installed-skill resolver can now resolve those shipped `/sd:*`
  skills by name. `sd-fleet-refresh` stays source-only and is not shipped, so
  `/sd:fleet-refresh` remains intentionally unresolvable in consumers. The install
  audit now covers
  `.claude/skills/sd-*` in both the root and shipped-twin scripts.

## 0.63.0 - 2026-08-02

- Raise the planning adversarial-review convergence limit from two automatic
  rounds to three. Section 4 of `planning-adversarial-review.md` now permits up
  to two remediation rounds (three automatic rounds total) before stopping for
  user judgment, instead of one remediation round. The stop-and-ask escalation
  still fires when a substantive concern persists past the permitted rounds or
  the host and Codex lanes remain in material conflict. Documentation surface in
  `docs/SD_AI_COMMAND_PACK.md` updated to match.

## 0.62.0 - 2026-08-02

- Make completion-successor validation direction-aware in the review-preflight
  validator. `isAdjacentArchiveCommit` now qualifies a completion anchor only when
  a task both lands in `archive/` and vacates its active location in the same
  commit, so a pure un-archive is no longer mistaken for an archive anchor. When a
  successor commit un-archives the exact task a candidate anchor archived, the
  validator emits a new `completion_successor_anchor_reverted` reason code —
  alongside, not instead of, the existing scope findings — naming the stale
  finish-work receipt and the re-run recovery action, instead of leaving an opaque
  `completion_successor_scope_invalid`. The scope guard is unchanged; a reverted
  finalization still fails, now legibly.

## 0.61.0 - 2026-07-31

- Give the ship-to-work-loop handoff a validated schema-v1 receipt. `sd-ship`
  now materializes its merge result as a JSON receipt file and reports the
  path on an `SD_SHIP_MERGE_RESULT_RECEIPT:` line; the free-text
  `SD_SHIP_MERGE_RESULT` block stays display-only. The work-loop helper gains
  `result --from-receipt`, which fails closed on unreadable, malformed, or
  unsupported payloads with named `ship_receipt_*` reasons, cross-checks the
  run, iteration, task, and PR identity against the ledger, and independently
  verifies merged claims by requiring the reported final head to be an
  ancestor of the recorded base branch tip. The `sd-work-backlog` controller
  records iteration results exclusively through the receipt and treats a
  missing or rejected receipt as a blocked iteration.
- Fix two work-loop recording defects: `record_result` now routes its phase
  change through `transition_state` instead of mutating the phase directly,
  and it rejects pull request numbers or URLs that contradict recorded
  evidence, gating the `mergedPrs` counter on verified merge state.
- Track four new per-iteration ledger fields (`mergeState`,
  `finishWorkState`, `housekeepingState`, `anomalies`) with enum validation,
  and upgrade persisted ledgers from older schemas in place.

## 0.60.0 - 2026-07-31

- Announce a removal version for the transitional review surfaces (audit
  A-045). `sd-full-check`, `sd-review-local`, and `sd-review-pr` each gain a
  `RetiredCommandSurface` registry row with `removed_version = 0.62.0`, and
  the command catalog now reports their status as `included in installed
  pack — transitional until 0.62.0; use <successor>` instead of a plain
  `included in installed pack` line indistinguishable from a live command.
  `sd-help`'s `recommend` mode now routes to the named successor (`sd-check`
  for `sd-full-check`; `sd-review` for `sd-review-local` and `sd-review-pr`)
  instead of the transitional command. **Consumer-facing:** none of the three
  commands change behavior or stop working — this only publishes their end
  date and stops the help surface from steering new usage toward them.
  Deletion is tracked separately in `07-24-remove-retired-review-surfaces`,
  targeting the same 0.62.0.

## 0.59.1 - 2026-07-31

- Align the status and housekeeping selector contracts (review finding 1.1.1).
  `sd-status` and `sd-housekeeping` now describe only the shipped `F-*`
  follow-up and `T-*` task selectors — the retired `F/T/R` wording is gone —
  and a selector that does not resolve to an `F-*` or `T-*` row of the current
  snapshot is reported as unresolved input with no action taken. A new drift
  test scans the shipped surface (templates, docs, generated adapters and
  mirrors) so the retired selector contract cannot reappear; `.trellis/` task
  history stays out of scope by construction.

## 0.59.0 - 2026-07-31

- Declare and pin the build dependency toolchain (audit A-108/A-109/A-110).
  `pyproject.toml` gains a `[project]` table with `requires-python = ">=3.10"`
  as the single machine-readable Python floor — ruff now infers its lint
  target from it, and a new test checks the hand-written copies (CI matrix
  floor leg, toolchain interpreter probe) against it. **Consumer-facing:**
  `sd-ai-command-pack-review-preflight.mjs` now requires Node 22 or newer
  (was 16.9, EOL since 2023); repos that install the pack need a supported
  Node LTS to run the preflight. CI pins `actions/setup-node` to Node 22 in
  the jobs that execute or parse the script instead of taking whatever the
  runner image ships, and installs Python dependencies from hash-pinned
  compiled requirements with `--require-hashes`, so transitive dependencies
  stop re-resolving unreviewed on every run.

## 0.58.0 - 2026-07-31

- Close the shipped-script documentation gap (audit A-115). Every manifest
  `scripts/` target now carries an explicit public/internal classification:
  `sd-ai-command-pack-pr-eligibility.py` gains an installed-guide entry as the
  read-only exact-head PR eligibility evaluator, while
  `sd-ai-command-pack-review-local.py` and `sd_ai_command_pack_lib.py` are
  declared internal. The guide now distinguishes `review-local.sh` (documented
  operator runner) from `review-local.py` (internal review stage) — the two
  never call each other. CONTRIBUTING narrows the stable-surface promise to
  guide-documented script CLIs and names the internal category, and a new
  doc-coverage gate (`.github/scripts/check-shipped-script-docs.sh`, wired
  into `make test` and CI) fails when a shipped script is neither documented
  nor deliberately allowlisted — or is both allowlisted and given an explicit
  guide entry bullet — so the gap cannot reopen silently and a
  reclassification must update both places. The eligibility evaluator's guide
  entry documents its real exit mapping (`0` eligible, `1` blocked, `2`
  anything else).

## 0.57.2 - 2026-07-31

- Require a trailing `<!-- SD-AI-COMMAND-PACK:KB-COPY -->` provenance marker
  before the Obsidian KB prune deletes a plain file in a managed category
  folder, so user files are never removed just for sitting in a folder that
  shares a category title — or for quoting the marker text mid-file — including
  through a KB root symlink into a personal vault. Generated
  copies now end with that trailing marker instead of being byte-identical to
  their sources, and both the refresh currency check and `--check` compare
  against the marked payload. Copies written by older versions adopt the marker
  on the next refresh while their source exists; copies orphaned before the
  upgrade are no longer pruned automatically and need manual cleanup (audit
  A-070 residual).

## 0.57.1 - 2026-07-31

- Preserve the moved-aside foreign lock when work-loop lock recovery cannot
  restore it, and name the aside path in the raised error so an operator can
  move it back. Restore now falls back to an `O_CREAT|O_EXCL` rewrite on
  filesystems without hard-link support, so the canonical lock path is
  restored instead of silently voiding mutual exclusion (audit A-092).

## 0.57.0 - 2026-07-30

- Remove the public `sd-watch-pr` command. `sd-ship` Stage 3 now runs an
  internal read-only watch coordinator: it polls the PR-eligibility probe
  every 20 seconds with an attempt ceiling of `timeout-minutes × 3` (default
  30 minutes) and classifies the result as settled-green, settled-blocked,
  timed-out, or probe-failed; only settled-green continues to Stage 4. The
  retired command name joins the drift-scan retirement registry, and
  `no-merge` fails as an unknown `sd-ship` argument — `until=review` is the
  supported stop-before-merge point.
- Move finish-work finalization into `sd-ship` Stage 2b for both
  `until=review` and `until=merge`: the SD finish-work flow runs exactly once
  per chain, bound to the exact head Stage 2 reviewed, with the
  completion-vs-planning selection owned by the flow's typed deterministic
  contract. Stage 4 runs zero finish-work flow invocations of its own — on an
  unchanged head it passes Stage 2b's retained exact-head receipt to the
  housekeeping gate, and on a moved head it recomputes the receipt with a
  direct read-only final-bundle validator invocation (completion mode against
  the current head's empty delta, planning mode re-running the captured base
  under journal-only-recovery scope). The eligibility gate's independent
  recomputation remains the double-run guard.
- If Stage 2b's finalization produces a new head, the chain re-enters
  Stage 2's check/review once for that head; a second finalization head stops
  the chain as a defect. Re-entry repeats only Stage 2 — never the learning
  pass, finalization, or Stage 4's merge.
- Narrow `sd-create-pr` to publish-only in every invocation: Step 6 names the
  next command (`sd-review scope=pr`, or `sd-ship` for the full chain)
  instead of entering a review loop, and the composite-only Stage 1
  orchestration context (`caller:`/`stage:`/`return-after:`) is removed —
  `sd-ship` Stage 1 invokes the same public flow and reads the publish result
  from its report. The trusted `sd-work-backlog` and `sd-fleet-refresh`
  contexts are unchanged.

## 0.56.8 - 2026-07-30

- Repoint `sd-ship` Stage 2 from the transitional `sd-review-pr` loop to the
  routed successor, `sd-review scope=pr`. The successor is review-only, so the
  two lifecycle side effects that used to ride along with review move to a new
  explicit Stage 2b owned by the composite: the one read-only, PR-scoped
  post-cycle review-learning pass (run for both `until=review` and
  `until=merge`), and — for `until=review` only — the SD finish-work flow bound
  to the exact reviewed head. `until=merge` still defers finish-work to the
  Stage 4 housekeeping gate, which remains the only merge authority. The
  `until=review` stop-point now sits after Stage 2b instead of after Stage 2's
  loop; its user-visible contract — review completes, Trellis work finishes,
  no merge — is unchanged. The internal `defer-finish-work` delegation mode is
  gone from `sd-ship`; `sd-review-pr` itself stays installed and callable
  standalone.
- Rewrite the usage guide's recommended review loop around the successor
  lifecycle only: `sd-check`, routed `sd-review`, `sd-ship` with its stage
  composition, work-backlog delegation to `sd-ship until=merge`, and the
  lifecycle commands. The transitional `sd-review-local`, `sd-review-pr`, and
  merged-PR interception steps leave the recommended path; the commands remain
  installed, documented in the catalog, and callable.

## 0.56.7 - 2026-07-30

- Scope the finalization bundle validator to the change delta. The final-bundle
  gate previously validated every changed task directory wholesale, so a defect
  in an untouched sibling file — a stale `task.json` description, a leftover
  scaffold row — blocked finalization of work that never touched that file
  (PR #273 failed on 25 such findings). Defects anchored to files inside the
  bundle delta still block; defects anchored to untouched files are demoted to
  a new non-blocking `advisories` array in the result document (capped at 25
  entries, overflow reported via `evidence.advisoriesDropped`, same path and
  message truncation as findings). Topology findings follow the anchor rule:
  a broken link blocks when the anchoring `task.json` is in the delta and
  advises when it is not, including the two sites that report the neighbor's
  path. The `pre-archive` command and historical completion replay keep their
  strict whole-directory behavior, and the housekeeping receipt loader
  tolerates the new fields.
- Widen journal-only planning recovery to ordinary repository maintenance
  commits. Cited-commit paths now partition five ways: active-task paths keep
  the current per-path and lifecycle rules; ordinary repository paths are
  allowed, including deletes and renames; the task archive, malformed
  task-namespace paths, and `.trellis/workspace/**` paths remain forbidden.
  `planning_recovery_task_change_missing` now fires only when the cited
  commits collectively change no allowed path, so a maintenance branch can
  finalize with a journal session citing its repository-only work commits.
- Document the finalization receipt contract in `sd-finish-work`: the captured
  base is the last work commit (not the merge-base with the default branch),
  the maintenance-branch planning flow, the widened recovery scope, and the
  advisory semantics.

## 0.56.6 - 2026-07-30

- Allowlist the documented `.sd-ai-command-pack/review.json` configuration file
  in the shipped install audit. `sd-review` declares the path and the pack docs
  describe it as supported, but `LOCAL_ALLOWED_PACK_FILES` never admitted it, so
  a consumer that created the file exactly as documented failed `install-audit`
  — and with it the `pack.install-audit` gate in sd-check, sd-full-check, and
  sd-review — with a hard error. The audit collector walks the filesystem, so
  the failure hit tracked and untracked copies alike, and no managed gitignore
  pattern covers the path. A fixture-backed test now locks the entry in place:
  it installs the pack into a consumer fixture, writes the documented
  configuration file, and asserts the audit passes; removing the allowlist
  entry fails the test. Audit finding A-056.

## 0.56.5 - 2026-07-30

- Silence the pre-PR tooling/generated scope advisory once the PR body already
  carries the required section. Advisory mode previously warned on every branch
  that touched a tooling/generated file and returned before the PR body was ever
  consulted, so a correctly written PR body could not stop the warning and every
  local `make check` on such a branch reported one warning that no action could
  clear. Advisory mode now resolves the body through the same path the enforcing
  check uses — `SD_AI_COMMAND_PACK_SCOPE_PR_BODY` first, then `gh pr view` — and
  warns only when the resolved body lacks the section or when no body can be
  resolved. The pre-PR reminder is unchanged when no PR exists yet, the advisory
  still never fails, and it resolves nothing on a branch with no
  tooling/generated change, so no `gh` call is added to the common case. The
  enforcing full-check path is unchanged except that a PR body parser that
  crashes is now a named failure instead of an unlabeled abort, and a resolver
  that returns no state at all is reported as such rather than as an
  indeterminate one.

## 0.56.4 - 2026-07-30

- Resolve a deadlock between two finalization gates over `task.json`'s `branch`
  field. The pre-archive gate refuses a completion-ready task whose `branch` is
  null, but `task.py start` never writes that field, so every task is born in
  the refused state. Recording the branch where `sd-finish-work` step 4 puts the
  operator — after the finalization base is captured — lands the write inside
  the archive commit, which the completion bundle gate then rejects with
  `completion_archive_identity_changed` because an archive move may change only
  `status` and `completedAt`. A compliant run had no exit at all: the step's own
  stop clause forbids repairing an `invalid` pre-archive result by mutating the
  task.
- `sd-finish-work` step 4 now records a missing branch *before* capturing the
  finalization base, for every task directory the gate is invoked for. It takes
  the value from `git symbolic-ref --quiet --short HEAD`, stops rather than
  guessing on a detached HEAD or a value equal to `base_branch`, and commits
  only that `task.json` as a branch-metadata commit — not a work commit, which
  `trellis-finish-work` reserves for pre-invocation code commits. A task that
  surfaces only after the base is captured cannot be prepared this way and is
  declined for the round, or the finalization restarts with it included.
- The completion bundle gate tolerates exactly one branch transition across an
  archive move, `null` to a non-empty string, so a run already past base capture
  can still finalize. A rewrite, an erasure, and a key absent from the source
  record all stay rejected, as does any change to any other field. The reason
  code had no regression coverage in either direction before this change.

## 0.56.3 - 2026-07-29

- Add an explicit fleet-controller recovery transition for `retry-exhausted`
  lanes. A lane's retry budget is per stage, so a consumer whose infrastructure
  failure consumed both automatic attempts became permanently terminal: nothing
  short of a new campaign could reopen it, and because a `retry-exhausted` lane
  reads as a failed observation it also tripped the canary health stop for every
  other consumer in the campaign. `resume --recover-exhausted-consumer NAME
  --exhausted-action ID --release VERSION` now grants one operator-authorized
  attempt at the stage that exhausted, bounded to two recoveries per consumer
  and stage. It validates that the lane is terminal `retry-exhausted`, that the
  named action is the lane's latest receipt, and that the receipt's stage,
  attempt, and reason code all agree with the lane; `--release` is compared
  against the campaign's own target version rather than the current
  `manifest.json` version, so a campaign on an older release stays recoverable.
  Replaying the same exhausted action returns the existing record and changes
  nothing.
- Bump the campaign state schema to version 2 and migrate version-1 state on
  load: an absent `recoveries` key becomes an empty list and every untagged
  recovery row gains `kind: "pack-blocker"`. Recovery rows are now a tagged
  union on `kind`, so exhaustion recoveries and pack-blocker recoveries are
  validated against their own field sets instead of one shared shape, and the
  pack-blocker idempotency lookup filters on `kind` rather than assuming every
  row carries a blocking head. Migration is read-only — loading a version-1
  campaign to report on it leaves the state file byte-for-byte unchanged until
  the next mutating command writes it. Historical `receipts` remain immutable
  under both recovery kinds.

## 0.56.2 - 2026-07-29

- Exempt a planning task's untouched context scaffold from both review-preflight
  seed-row lanes — the diff-scoped task-context gate and the bookkeeping
  validator that emits `task_context_seed`. `task.py create` writes
  `implement.jsonl` and `check.jsonl` with a generated `_example` seed row,
  which both lanes failed on immediately, so creating a task put the repo into a
  failing state until the author blanked or rewrote both files by hand. This
  affected pack-installed repositories where task creation actually seeds those
  manifests; Trellis skips seeding when no sub-agent platform is configured. The
  exemption is deliberately narrow: a single row that parses to an object whose
  sole key is `_example`, in a non-archived task whose `task.json` status is
  `planning`. It matches on that shape rather than on Trellis's exact seed text,
  which is Trellis-owned and changes across versions — pinning it would re-break
  task creation on the next Trellis upgrade. A seed row that survives beside
  authored rows, carries extra keys, or appears in any non-planning or archived
  task still fails, so the curation requirement at `task.py start` is unchanged.

## 0.56.1 - 2026-07-29

- Treat a remote review body that reports no new comments as clean only after
  parsing it for a collapsed low-confidence block. Copilot withholds
  observations it scored as low confidence and discloses them only inside that
  block, so they never become inline comments or review threads and a loop
  reading only thread state never sees them. Each disclosed entry is now
  classified with the same rules as an inline comment, and the round is clean
  only when none survives verification.
- Compare every review event's `commit_id` to the recorded head before counting
  a review round. A reviewer can submit against an earlier commit while a newer
  one is already the head, and its body still reports full coverage because the
  file count is taken against the commit it actually read.
- Require the audit ledger and report to be committed separately from any
  `.trellis/tasks/**` planning artifacts written in the same session. The
  bookkeeping validator admits only task and workspace paths into a
  finalization delta, so a commit mixing `.trellis/audit/**` with task
  artifacts can be neither journaled nor finalized, and the mix cannot be
  undone once published.
- Extend the planning adversarial review to check a task's artifacts against
  each other, not only against the repository. A value repeated across
  `prd.md`, `design.md`, `implement.md`, and `task.json` is enumerated by
  search rather than by reading the artifacts in sequence, and any
  cross-artifact citation is confirmed to still describe what its target says.

## 0.56.0 - 2026-07-28

- Add a typed, additive `environment_blocked` recovery contract. When an
  environment or authority boundary refuses a Git-metadata, user-state,
  tool-cache, or knowledge-base write, the owning operation attaches a bounded,
  secret-safe fragment naming the boundary, last verified checkpoint, mutation
  state, and a non-authoritative recovery action, without changing its own
  outcome or exit. The housekeeping result surfaces these as an additive
  `environmentBlocks` array that consumers which do not understand it ignore.
- Route housekeeping by pull-request lifecycle state and validate the
  finish-work receipt path before any side effect, failing fast on an invalid
  receipt while leaving downstream merge eligibility unchanged.
- Gate task archival on a read-only pre-archive acceptance-readiness check that
  does not fire on handoff prose, non-canonical directories, or fenced examples.
- Make housekeeping the sole owner of general recovery-artifact cleanup while
  the creating workflow keeps success-path cleanup; ambiguous or unique content
  defaults to preserve and `sd-status` stays read-only.
- Recover a stale work-loop lock with an identity-checked rename-aside so a
  concurrent run cannot remove a live lock, and expose blocked and parked
  backlog markers so the selector distinguishes parked work from ready work.
- Scope toolchain caches per user with uid and ownership checks, and record the
  housekeeping-result schema migration explicitly as an in-major change with no
  silent contract break or compatibility alias.

## 0.55.5 - 2026-07-27

- Classify `.gemini/settings.json` consistently as Trellis-owned across the
  platform registry and shipped review-scope scanner, matching the JavaScript
  preflight and preventing consumer review-scope drift.

## 0.55.4 - 2026-07-27

- Accept a completed task archive move when Git reports a rewritten active PRD
  as deleted but exposes the matching task metadata only at its changed archive
  destination.
- Keep the topology guard fail closed when a live task directory is missing
  `task.json`, with focused regression coverage for both paths.

## 0.55.3 - 2026-07-27

- Let a controller-issued merge action record the required finish-work head
  advance as one bounded `pr-head-advanced` republication instead of forcing a
  contradictory old-head merge receipt or terminal pack blocker.
- Retain the exact finish-work receipt across successor publication, review,
  and merge eligibility, then consume it through housekeeping only after the
  new PR head remains unchanged and fully eligible.
- Preserve exact publication epochs, serialized merges, the two-attempt head
  churn bound, and the separate corrective-release path for terminal missing
  task evidence.

## 0.55.2 - 2026-07-27

- Make publication and review workflow invocation explicit standing approval
  for in-scope commits, PR-branch pushes, and configured GitHub review requests
  or re-requests, while preserving ambiguity, risk, round-limit, destructive,
  exact-head, and merge gates.
- Surface that authority in startup-visible skill descriptions and prevent the
  portable structured-question contract from adding redundant approval prompts
  for routine GitHub publication or review actions.
- Make a merge-capable `sd-fleet-refresh` campaign standing approval for every
  eligible controller-issued consumer housekeeping merge, including after
  review-finding remediation; retain `no-merge` as the explicit opt-out.
- Prefer the optional `archify` skill when `sd-update-spec` creates or
  materially updates repository documentation visuals, with a reported
  repo-native fallback when Archify is unavailable.

## 0.55.1 - 2026-07-26

- Pin strict UTF-8 decoding explicitly in the shipped housekeeping-result JSON
  reader and the source fleet-preflight provenance reader, preserving existing
  fail-closed behavior while satisfying consumer static-analysis contracts.

## 0.55.0 - 2026-07-26

- Commit `.claude/` by default like every other platform: replace the
  `.claude/**` blanket plus SD allow-list in the managed `.gitignore` block with
  the standard runtime deny-list, so Trellis runtime, agents, `settings.json`,
  and repo-authored skills are tracked instead of hidden. Only local Claude
  state (`settings.local.json`, caches, logs, tmp) stays ignored.
- Extend the Claude `--local-only` exclude set and the review-scope and
  review-preflight classifiers to cover `.claude/agents/trellis-*.md` and
  `.claude/settings.json`, and add a `git check-ignore` regression test that no
  platform ignores its own declared markers.

## 0.54.1 - 2026-07-26

- Require fleet refresh lanes to establish a dedicated consumer Trellis task
  before installation so deferred finish-work can produce canonical completion
  evidence instead of a structurally invalid taskless journal.
- Add an explicit corrective-release controller transition that preserves the
  blocker receipt, records recovery evidence, republishes on a new exact-head
  epoch, and avoids replaying the failed merge action.
- Document an append-only recovery for already-published taskless refresh PRs
  while keeping ordinary journal-only planning validation fail closed for
  arbitrary implementation commits.

## 0.54.0 - 2026-07-25

- Recover a canonical adjacent completion tail when review fixes follow task
  archival, proving a bounded linear successor without another journal or
  bookkeeping-only commit.
- Replace the head-only housekeeping attestation with the exact retained
  finish-work JSON receipt and independently recompute it inside eligibility
  before any merge mutation.
- Keep the public finalization modes at `completion|planning`, expose the
  internal `post-archive-review-successor` subtype, and fail closed on stale,
  forged, nonlinear, invalid-anchor, or bookkeeping-mutating successor evidence.

## 0.53.0 - 2026-07-25

- Let planning finish-work automatically validate a journal-only successor
  when its referenced work commits were already published before the captured
  finalization base.
- Prove one exact journal/index pair, unique published single-parent commits,
  regular active-task-only deltas, and planning lifecycle state while keeping
  normal planning bundles on the complete content-quality validator.
- Preserve schema version 1, `mode: planning`, and `planning_bundle_valid`,
  adding only the machine-visible `journal-only-recovery` evidence subtype and
  bounded recovered task directories.

## 0.52.1 - 2026-07-25

- Warn deterministically before remote review when the selected diff exceeds
  GitHub Copilot's configurable 300-file review limit.

## 0.52.0 - 2026-07-25

- Add `sd-review` as the unified exact-scope review lifecycle for changes,
  branches, codebases, and pull requests, composing the typed deterministic
  check with cost-aware local review receipts and routed GitHub review.
- Discover the released `sd-github-review` v1 capability from a strict
  repository descriptor, persist dispatch intent before mutation, reconcile
  durable exact-head receipts, and observe only receipt-declared finding
  channels without a direct reviewer fallback.
- Extend the shared review configuration with bounded `remoteIntegration`
  policy, keep optional router absence visibly local-only, and fail closed for
  provider failures, invalid routing, ambiguous dispatch, or stale heads.

## 0.51.0 - 2026-07-25

- Extend the canonical review-preflight executable with schema-version-1
  `pre-archive` and completion/planning `final-bundle` bookkeeping modes.
- Validate bounded task identity, descriptive metadata, lifecycle, topology,
  context, archive moves, journal/index content, commit reachability, and
  whitespace before finish-work may publish its final bookkeeping head.
- Make finish-work retain one exact validator result for review, ship, and
  housekeeping callers while preserving failed local archive/journal commits
  for inspection instead of rewriting or pushing them.

## 0.50.0 - 2026-07-25

- Add strict exact-head finding-family evidence to the internal local-review
  stage, using the bounded review-learning vocabulary while preserving original
  provider labels separately.
- Stop automatic remote eligibility when the same actionable family appears on
  a second round, emit a deterministic sibling-audit matrix, and require clean
  local-review, passing check, sibling, batch, and one-commit evidence before
  redispatch.
- Stop post-audit recurrence before another provider call until the existing
  structured round-extension decision is recorded, with bounded family, cost,
  batch, sibling, and redispatch telemetry.

## 0.49.0 - 2026-07-24

- Add the internal exact-scope local stage consumed by the successor
  `sd-review` lifecycle, with deterministic risk/cost provider plans and
  isolated parallel Prism/Gito attempts for substantive first heads.
- Persist normalized provider evidence and exact target-bound receipts so an
  unchanged pre-publication branch review can satisfy the PR stage without a
  duplicate provider call; invalidate reuse on any target, provider, or policy
  change.
- Keep failures and findings distinct, block remote routing on outstanding
  local findings, and permit bookkeeping-only skips only with exact external
  evidence and zero new confidence.
- Parse Prism and Gito native structured reports rather than treating exit zero
  as clean, and fail before dispatch when a provider cannot safely encode the
  exact target paths.

## 0.48.0 - 2026-07-24

- Expose bounded, normalized historical review-learning clusters as a typed
  path-filtered planning signal without copying full review comment bodies.
- Add one-scan-per-attempt private receipts with exact cache reuse, bounded
  GitHub evidence, explicit tracked-snapshot freshness, visible
  stale/unavailable states, and zero confidence credit.

## 0.47.0 - 2026-07-24

- Add `sd-check` as a typed deterministic verification command with strict
  argv-array repository configuration and normalized outcome/exit semantics.
- Keep checks read-only by removing provider and refresh behavior, routing tool
  caches outside the repository, and failing when before/after repository or
  Git state differs.
- Add a registry-derived shipped-surface closure validator shared by
  `sd-check`, local pre-publication, and CI. It explicitly registers
  source-only references and reports stale generated state with its owning
  preparation command.

## 0.46.0 - 2026-07-24

- Route XDG/GitHub CLI, Python, uv, pip, Ruff, and npm caches through one
  validated private per-user/per-repository environment shared by Python and
  shell entry points without changing authentication state.
- Replace command-specific UV and disposable-candidate cache fragments with
  the shared builder, controlled failures, deterministic external namespaces,
  and documented cache-root/retention behavior.

## 0.45.0 - 2026-07-24

- Keep formal repository audits read-only by replacing checkout-owned Make and
  help probes with static inspection.
- Add a deterministic committed-tree architecture inventory that safely ranks
  regular blobs while preserving hostile valid filenames.

## 0.44.0 - 2026-07-24

- Re-read the exact pull request head by retained PR number at local-branch
  eligibility completion, failing closed when it changes or becomes unreadable.
- Bind schema-major-1 eligibility evidence to additive initial and final PR
  head observations while preserving local-head and housekeeping safeguards.

## 0.43.0 - 2026-07-23

- Add a Claude project rule that adversarially reviews materially changed
  Trellis planning artifacts before implementation approval or task start.
- Run an optional read-only native `codex exec` peer review in parallel with
  Claude's host review, reconcile all concerns explicitly, and degrade cleanly
  when the Codex CLI is unavailable or fails.

## 0.42.0 - 2026-07-23

- Add a Claude-only native Codex CLI peer lane to normal `sd-review-local`
  scopes, running it concurrently with the selected Prism, Gito, or configured
  runner stack and joining verified findings before fix selection.
- Preserve runner-only fallback for missing, incompatible, failed, or
  full-codebase Codex review without requiring or patching the OpenAI Codex
  Claude plugin.

## 0.41.0 - 2026-07-23

- Remove the duplicate R-prefixed Trellis roadmap inventory from `sd-status`
  and advance its machine-readable report schema to version 2.
- Route unmatched task-like items from bounded roadmap sources into the
  existing F-prefixed follow-up list with deterministic source evidence and
  exact Trellis task deduplication.

## 0.40.0 - 2026-07-23

- Add a schema-versioned housekeeping result that composes the existing
  exact-head eligibility receipt and delegated status report with stable
  cleanup action and anomaly codes.
- Shorten `sd-housekeeping` around that typed runtime contract and move rare
  `sd-update-spec` architecture, repository-map, and knowledge-base mechanics
  into flat, conditionally loaded references.

## 0.39.0 - 2026-07-23

- Consolidate design-first backlog work into typed `sd-work-backlog`
  `selector=needs-design` and `until=design|merge` arguments, retiring the
  separate `sd-work-designs` command without an alias.
- Route stopped, red, missing-ledger, stale-owner, and terminal-reconciliation
  states through deterministic helper reason codes and conditional recovery
  references so healthy runs avoid rare recovery prose.

## 0.38.0 - 2026-07-23

- Add a deterministic, versioned audit-charter applicability router with a
  non-removable standard core, additive dimensions, transparent evidence, and
  fail-safe exhaustive fallback.
- Replace legacy quick/deep audit depths with `standard|exhaustive`, enumerate
  every charter's coverage state, and calibrate standard routing against UI,
  database, API, infrastructure, dependency, and release fixtures.

## 0.37.1 - 2026-07-23

- Make `sd-review-learnings` observably read-only by default, constrain local
  updates to canonical repository-contained UTF-8 files, and require an exact
  structured confirmation for exceptional external writes.
- Add atomic target revalidation and structured mode, containment, digest,
  finding, change, and write-status reporting without staging or publishing
  learning updates.

## 0.37.0 - 2026-07-23

- Add a private, atomic fleet campaign controller with deterministic
  `plan`/`next`/`record`/`status`/`resume`/`validate` operations, exact-release
  and exact-head receipts, bounded retries, interruption reconciliation,
  canary/wave enforcement, and single-candidate merge execution.
- Reduce `sd-fleet-refresh` to controller action ownership and exception
  interpretation, with rare recovery and corrective-release mechanics loaded
  only when needed instead of keeping the rollout state machine in prompt prose.

## 0.36.0 - 2026-07-23

- Add a validated portable structured-question registry, generate
  `AskUserQuestion` guidance only for capable Claude adapters, and preserve
  concise interactive fallbacks plus explicit noninteractive behavior for
  help, review, backlog, audit, retro, spec, PR, and finish-work decisions.

## 0.35.0 - 2026-07-23

- Expand `sd-status` with deterministic F-prefixed follow-ups, complete
  T-prefixed unarchived task inventory, and R-prefixed top-level roadmap work,
  preserving explicit empty sections and structured report-local selectors.

## 0.34.1 - 2026-07-23

- Add a registry-driven command-surface drift lint with exact-line JSON
  findings, reasoned historical allowances, canonical retirement footprints,
  and maintainer-gate coverage for stale names and missing targets.

## 0.34.0 - 2026-07-23

- Generate a capability-driven, fail-closed checkout-trust preflight for every
  execution-capable command adapter, with `sd-help` as the sole non-executing
  trusted-static exemption.

## 0.33.0 - 2026-07-23

- Centralize exact-head pull-request eligibility in a versioned read-only
  evaluator, keep housekeeping as the sole merge mutation owner, and route
  classified dependency updates through that shared gate.

## 0.32.2 - 2026-07-23

- Fail closed when changed Trellis task-context manifests contain malformed
  non-empty JSONL rows instead of silently skipping them.

## 0.32.1 - 2026-07-23

- Preserve review-learning path-family and test-harness signal classification
  for repositories using either `test/` or `tests/`.

## 0.32.0 - 2026-07-23

- Validate optional Trellis task priority provenance with deterministic,
  redacted diagnostics, and retain executable coverage that archived task
  evidence may reference later-deleted paths while live PRDs may not.

## 0.31.0 - 2026-07-22

- Reject changed deferred Trellis tasks whose bases are not grounded in their
  parent's durable or active branch, and require changed active parent PRDs to
  reference every declared child without disrupting intentional stacks or
  unchanged history.

## 0.30.8 - 2026-07-22

- Run deterministic review preflight in `sd-create-pr` before staging or
  pushing, and reject changed Trellis task-context references outside spec and
  task research roots before publication.

## 0.30.7 - 2026-07-22

- Keep the full-check Obsidian KB freshness lane strict for broken root
  symlinks and occupied non-directory roots in auto mode.

## 0.30.6 - 2026-07-22

- Make the missing finish-work attestation diagnostic resolve the tracked local
  branch after finish-work instead of suggesting the stale pre-finish commit.

## 0.30.5 - 2026-07-22

- Accept legacy task directory names inside month-bucketed Trellis archives
  while keeping active task directories date-prefixed.

## 0.30.4 - 2026-07-22

- Remove equivalent unmanaged Obsidian KB ignore rules when refreshing an
  existing managed block, and make live fleet refreshes run each consumer's
  declared deterministic preparation commands before the local gate.

## 0.30.3 - 2026-07-22

- Make changed non-planning Trellis task metadata trigger sibling context
  scaffold validation, matching the documented review-preflight contract.

## 0.30.2 - 2026-07-22

- Document the intentional best-effort cleanup in the installed PR-body scope
  helper so CodeQL accepts the copied payload without behavior changes.

## 0.30.1 - 2026-07-22

- Require an exact current-head finish-work attestation before housekeeping can
  auto-merge an open PR, while preserving cleanup-only and already-merged
  operation without the attestation.

## 0.30.0 - 2026-07-21

- Keep current unresolved review comments individually actionable while
  deterministically deduplicating historical comments into bounded,
  evidence-backed signal clusters with category-specific preventive actions.

## 0.29.0 - 2026-07-21

- Replace the generic first-review boundary warning with a deterministic,
  configurable six-category regression matrix that emits bounded
  good/base/failure prompts, scans executable workflow YAML, and excludes
  test, fixture, generated, vendored, and installed-mirror paths.

## 0.28.0 - 2026-07-21

- Make housekeeping create or refresh `.obsidian-kb`, preserve valid root
  directory symlinks, reject invalid root paths before writes, and manage the
  root with an anchored ignore rule that covers directories and symlinks.

## 0.27.0 - 2026-07-21

- Preserve GitHub's auto-filled PR summary while automatically appending the
  required tooling/generated scope section for fully classified bookkeeping
  branches before standalone or `sd-ship` review handoff.

## 0.26.1 - 2026-07-21

- Reject completed Trellis journal sessions that claim successful validation
  while retaining the default no-validation Testing fallback, and route
  non-deferred PR review through the safe SD finish-work recorder wrapper.

## 0.26.0 - 2026-07-21

- Add a diff-scoped review-preflight guard for Trellis task identity,
  lifecycle, branch-target, layout, and reciprocal parent/child metadata while
  grandfathering untouched historical records.

## 0.25.5 - 2026-07-21

- Make full-check Prism review local-first: when tracked staged or unstaged
  changes exist, review each non-empty local layer and defer the committed
  branch range, avoiding a redundant paid scan during iteration.

## 0.25.4 - 2026-07-21

- Let the default full-check repair and recheck an existing ignored stale
  Obsidian KB once, while keeping required mode and unignored state read-only
  and fail-closed.

## 0.25.3 - 2026-07-20

- Remove the unused terminal reconciliation pull-request normalizer parameter
  so the helper signature reflects its value-only validation contract.

## 0.25.2 - 2026-07-20

- Restrict the first-review boundary-risk token scan to production source so
  conventional test harness files do not create subprocess, filesystem, or
  environment advisories for behavior they only exercise.

## 0.25.1 - 2026-07-20

- Reject generated `_example` scaffold rows in diff-changed Trellis task
  context files even while a task is still planning, without scanning
  untouched historical context.

## 0.25.0 - 2026-07-20

- Keep fleet canaries sequential, then schedule independent post-canary
  refresh work in manifest-configured bounded waves while serializing gated
  merges in deterministic manifest order.

## 0.24.8 - 2026-07-20

- Report a verified terminal reconciliation attached to a non-terminal run as
  an invalid `terminalReconciliation` record without mislabeling its valid
  nested status.

## 0.24.7 - 2026-07-20

- Require an already-recorded concrete base branch before treating an
  unchanged shipped SHA as historical evidence during work-loop recovery.

## 0.24.6 - 2026-07-20

- Distinguish active and stale terminal reconciliation locks so stale-lock
  failures point operators to explicit `reconcile-terminal
  --recover-stale-lock` recovery instead of waiting for an abandoned owner.

## 0.24.5 - 2026-07-20

- Fixed work-loop checkpoint recovery after a verified squash merge so a
  later default-branch advance can retain the historical shipped feature SHA
  without weakening merge-boundary or changed-SHA ancestry validation.

## 0.24.4 - 2026-07-20

- Teach Copilot that source-only fleet helpers and source-workflow documentation
  are intentionally absent from consumer manifests, and require receipt,
  provenance, and install-audit evidence before reporting a missing-file defect.

## 0.24.3 - 2026-07-20

- Reject malformed pull-request URLs, including invalid ports and malformed
  IPv6 authorities, without leaking `urllib.parse` exceptions from work-loop
  ledger or status-snapshot validation.

## 0.24.2 - 2026-07-20

- Route `sd-review-pr` through a deterministic helper that honors a
  repository-owned `check:full` prelude, preserves the direct pack-script
  fallback, disables Prism/Gito on both paths, and rejects recursive wrappers.

## 0.24.1 - 2026-07-20

- Keep work-loop checkpoints as lifecycle overlays and recover paused ledgers
  atomically from complete, locally verified forward evidence, with explicit
  schema-v1 fallback for legacy human-only checkpoint targets.

## 0.24.0 - 2026-07-20

- Add a fail-closed `reconcile-terminal` work-loop operation that records
  preverified external task and PR completion without reviving stopped runs or
  rewriting their historical evidence and counters.
- Surface verified terminal completion as historical in status and
  housekeeping, with exact delivery/bookkeeping PR evidence and no obsolete
  red-checkpoint recommendation.

## 0.23.16 - 2026-07-20

- Record private, resumable fleet stage timing with monotonic elapsed evidence,
  reviewer/CI overlap, retry and critical-path summaries, and no change to the
  authoritative rollout gates.

## 0.23.15 - 2026-07-20

- Classify verified fleet findings by canonical owner so only blocker families
  interrupt the rollout, while deferred and duplicate observations retain
  evidence-backed replies, thread settlement, and one recorded follow-up.

## 0.23.14 - 2026-07-20

- Classify exact fleet refresh heads against verified release, audit,
  provenance, and receipt-bounded diffs so pure integrations skip redundant
  remote implementation-review requests without skipping existing feedback,
  consumer checks, CI, watch, or housekeeping.

## 0.23.13 - 2026-07-20

- Fail fleet preflight before consumer inventory unless the local and remote
  release tag, exact tagged payload, ancestry, and tagged/current full-fleet
  candidate evidence agree.

## 0.23.12 - 2026-07-20

- Batch related fleet-rollout defects into one bounded corrective campaign,
  one release identity, and one canonical full-fleet validation before the
  original rollout resumes.

## 0.23.11 - 2026-07-19

- Include base-branch and last-shipped-SHA evidence in canonical work-loop
  status snapshots, and render every non-null current-state field in the
  direct human-readable status output.

## 0.23.10 - 2026-07-19

- Reject transition task and base-branch values that are non-string or become
  empty after normalization, preserving field-specific diagnostics and leaving
  the phase and persisted ledger unchanged.

## 0.23.9 - 2026-07-19

- Reject optional work-loop snapshot strings that are present but become empty
  after bounded sanitization, while preserving explicit `null` values and
  fail-closing blank terminal diagnostics.

## 0.23.8 - 2026-07-19

- Reject empty or whitespace-only persisted work-loop current-state strings,
  including recorded branch evidence, before a head-only evidence update can
  preserve malformed ledger state.

## 0.23.7 - 2026-07-19

- Preserve bounded diagnostics when a dynamically loaded work-loop helper
  reports an invalid snapshot without an error.
- Allow head-only evidence updates after a recorded local branch is removed,
  while retaining branch-tip consistency checks whenever that ref is
  available and requiring explicit branch evidence to resolve locally.
- Limit the work-loop `transition` CLI to task and base-branch identity fields
  so its help and accepted arguments match the transition contract.

## 0.23.6 - 2026-07-19

- Require reconciliation to supply every non-null recorded current-state field
  before clearing a ready or blocked recovery checkpoint, preventing unrelated
  partial evidence from erasing unresolved contradiction context.

## 0.23.5 - 2026-07-19

- Keep ready or blocked work-loop recovery checkpoints fail-closed until
  reconciliation supplies matching current-state evidence; a phase-only
  observation can no longer erase unresolved contradiction context.

## 0.23.4 - 2026-07-19

- Normalize dynamically loaded active work-loop snapshots to an allowlisted,
  bounded output contract before status JSON or terminal rendering.

## 0.23.3 - 2026-07-19

- Normalize dynamically loaded terminal work-loop snapshots before status
  rendering, discarding untrusted fields and sanitizing bounded diagnostics.

## 0.23.2 - 2026-07-19

- Prevent phase transitions from bypassing work-loop branch, commit, PR, and
  shipped-SHA evidence validation; mutable facts now require the dedicated
  `evidence` operation.
- Validate shipped SHA membership against the recorded branch tip when no HEAD
  was recorded, with a targeted diagnostic when neither source is available.

## 0.23.1 - 2026-07-19

- Remove the expired `REVIEW_PREFLIGHT_PR_BODY` compatibility fallback from
  current shipped `sd-full-check` guidance.
- Guard every manifest-declared skill, command, prompt, and guide source
  against reintroducing the retired variable while preserving historical and
  runtime retirement evidence.

## 0.23.0 - 2026-07-19

- Add an atomic work-loop `evidence` operation for verified same-phase commit,
  pull-request, review-fix, finish-work, and merge updates.
- Keep stable task/base identity and invalid Git ancestry, branch, or PR changes
  fail-closed while letting successful recovery clear obsolete checkpoints.

## 0.22.0 - 2026-07-19

- Add `--if-present` to the shipped Obsidian KB helper so lifecycle workflows
  can refresh an existing KB without opting other repositories into one.
- Make housekeeping refresh generated knowledge after finish-work task
  archival and make the autonomous backlog loop refresh again after any later
  follow-up task creation, with actionable failure handling and one owner per
  lifecycle boundary.

## 0.21.7 - 2026-07-19

- Report completed Trellis tasks stranded outside the archive in `sd-status`
  and fail review preflight with the exact `task.py archive` remediation.
- Ignore archived, non-completed, nested, and symlinked task entries while
  keeping the recurrence scan bounded to direct active-task records.

## 0.21.6 - 2026-07-19

- Validate dynamically loaded work-loop status snapshots before rendering and
  report missing, unsupported, or incomplete shapes as bounded `invalid`
  anomalies instead of printing absent run metadata.

## 0.21.5 - 2026-07-19

- Keep generated GitHub review provenance inside the managed review-learning
  block out of local documentation-path validation while preserving checks and
  line diagnostics for surrounding human-authored content.
- Render remote review paths containing backticks with safe Markdown code-span
  fences and keep managed-marker neutralization intact.

## 0.21.4 - 2026-07-19

- Keep direct `sd-status` local and fleet reads from creating repository-local
  Python bytecode caches while restoring the caller's bytecode setting after
  helper imports.

## 0.21.3 - 2026-07-19

- Reject missing positional `sd-status` repository paths instead of silently
  inspecting an existing parent repository; existing file paths inside a
  repository remain supported.

## 0.21.2 - 2026-07-19

- Rely on `tempfile.mkstemp()` for private temporary-file creation so work-loop
  state writes remain portable when a filesystem does not support `chmod`.

## 0.21.1 - 2026-07-19

- Pin strict UTF-8 decoding for work-loop candidate files so consumer defect
  scanners and locale-independent file-boundary policy agree.
- Document intentional best-effort permission and cleanup suppression in the
  work-loop helper without changing its atomic-write behavior.

## 0.21.0 - 2026-07-18

- Make `sd-work-backlog` a resumable autonomous plan-to-merge controller and
  make `sd-work-designs` its `needs-design` selector, with ordered focus,
  strict focus-only, planning-only stops, operator controls, and bounded
  iteration checkpoints.
- Ship a standard-library, user-local work-loop ledger and lock helper with
  atomic state, repository identity, legal transitions, conservative focus
  evidence, context-health reconciliation, and interruption-safe resume.
- Add trusted nested `sd-ship` results and read-only loop visibility to
  `sd-status` without changing existing review, finish-work, merge, or cleanup
  ownership.

## 0.20.0 - 2026-07-18

- Accept bare primary subjects for retrospective topics, coverage target files,
  fleet consumers, audit dimensions, and status repository paths while keeping
  lifecycle and safety controls explicit and fail-closed.

## 0.19.12 - 2026-07-18

- Narrow the first-review structured-input advisory so routine string
  `.split(...)` calls do not trigger it, while direct CLI argument,
  environment-value, and file-content splits remain covered.

## 0.19.11 - 2026-07-18

- Compare review-size and added-code risk advisories from the branch merge
  base so upstream-only changes do not create false first-review warnings.

## 0.19.10 - 2026-07-18

- Bound first-review risk scanning of untracked code with the existing byte
  limit and warn when oversized files are skipped.

## 0.19.9 - 2026-07-18

- Count all review events for the relevant pull request with GitHub GraphQL's
  bounded `reviews.totalCount` field instead of the first REST page length.

## 0.19.8 - 2026-07-18

- Run `sd-status` repository discovery from the normalized candidate directory
  so file arguments do not retain an avoidable dependency on the caller's
  current working directory.
- Skip the GitHub commit-to-PR API lookup for traditional two-parent merge
  commits while preserving fail-closed evidence checks for squash and rebase
  merges.
- Preserve the reserved Trellis `archive/` task root as non-task state while
  continuing to recognize valid `archive/<month>/<task>/` artifacts.

## 0.19.7 - 2026-07-18

- Add a review-preflight byte-size guard for untracked files so very large
  artifacts are treated as large diffs without loading the full file into
  memory just to count lines.

## 0.19.6 - 2026-07-18

- Add explicit review-preflight regression coverage for Markdown and code-span
  documentation references that use `path.md:line` and `path:line:column`
  anchors.

## 0.19.5 - 2026-07-18

- Resolve `sd-status --repo` when callers pass relative files or other
  non-directory paths inside a Git checkout by probing the parent directory
  before `git -C`. Paths whose parent cannot be used as a repository still
  fail cleanly.
- Clarify first-time fleet profile creation by documenting the intentional
  missing-file path instead of leaving an empty exception block.

## 0.19.4 - 2026-07-18

- Resolve repository status correctly when `--repo` names a file within a Git
  checkout, while continuing to reject missing repository paths.

## 0.19.3 - 2026-07-18

- Exempt forward-looking `design.md` and `implement.md` planning artifacts under
  `.trellis/tasks/` from the review-preflight path-existence check, so a task's
  proposed (to-be-created) files no longer fail the local gate. `prd.md` and
  specs still describe current state and keep the check.
- Extend the review-preflight line-anchor stripper to resolve `~` approximate
  markers (for example `path:~145` and `path:~315-366`) alongside the
  comma-joined multi-ranges added in 0.19.2, so compact citations of existing
  files in PRDs and specs are no longer reported as missing.

## 0.19.2 - 2026-07-18

- Resolve documentation citations that use comma-joined multi-line ranges
  (for example `path:1-2,3-4,5-6`) in the review preflight, so valid anchored
  references are no longer flagged as missing paths. Existing single-range,
  column, and internal-colon citation forms continue to resolve unchanged.

## 0.19.1 - 2026-07-18

- Fail review preflight when changed Trellis task context still contains
  generated `_example` rows after the task enters implementation, while
  preserving planning-time scaffolds and existing archive safety boundaries.
- Report the Git stash count in local, fleet, human-readable, and JSON status
  output without treating saved stashes as an unhealthy working tree.
- Inspect complete GitHub review-learning windows by default, report PR
  inventory/truncation, and support explicit PR-scoped analysis.
- Warn before remote review when changed code adds boundary-sensitive behavior,
  the authored source surface is large, or the diff spans multiple Trellis
  tasks; installed/generated mirrors remain outside the authored threshold.
- Run one read-only PR-scoped review-learning pass after the complete
  `sd-review-pr` cycle, never after individual rounds or again from `sd-ship`.

## 0.19.0 - 2026-07-17

- Add the read-only `sd-status` command across supported adapters, with bounded
  local reports, portable fleet aggregation, explicit cached/refreshed
  ref labels, schema-versioned JSON, pack/Trellis version visibility, and
  evidence-backed numbered next steps.
- Ship the fleet parser to consumers and add an opt-in machine-local profile so
  `sd-status fleet` can locate canonical versioned fleet policy from any
  installed repository while preserving per-machine checkout path overrides.
- Add `install.py --configure-fleet` with dry-run, profile validation, atomic
  writes, and preservation of existing checkout overrides; ordinary installs
  and status collection remain free of user-global side effects.
- Make housekeeping delegate final Git, GitHub, Trellis, anomaly, and next-step
  reporting to the shared status collector in strict mode while preserving its
  existing merge and cleanup safety gates.

## 0.18.0 - 2026-07-17

- Add the read-only `sd-help` command across supported adapters, with
  list/explain/compare/recommend/examples/tour modes, honest runtime
  availability labels, bounded workflow recommendations, and copy-ready native
  invocations.
- Generate the help catalog and all shared-reference fanout from a validated
  command/family registry so command names, descriptions, source-only policy,
  adapters, and installed skill resources cannot drift independently.
- Make fleet candidate checks representative of generated repository metadata
  and isolate npm, uv, and Python bytecode caches during disposable validation.

## 0.17.0 - 2026-07-17

- Separate `sd-ship` publication and review ownership: Stage 1 now delegates
  an internal publish-only `sd-create-pr` flow and Stage 2 runs review exactly
  once according to the selected stop-point.
- Keep standalone `sd-create-pr` behavior unchanged and reject user attempts
  to select the composite-only orchestration context before any side effects.

## 0.16.2 - 2026-07-17

- Keep standalone `sd-review-pr` and `sd-ship until=review` finish-work
  behavior while allowing the merge-through composite to defer finish-work to
  Stage 4.
- Run the composite watch stage with its existing `no-merge` mode so
  `sd-housekeeping` owns finish-work, merge, and cleanup exactly once, and a
  blocked watch leaves the active Trellis task available for resume.

## 0.16.1 - 2026-07-17

- Fail the generic review preflight when changed `implement.jsonl` or
  `check.jsonl` files in newly completed or archived Trellis tasks still
  contain generated `_example` seed rows.
- Check both context siblings when `task.json` marks completion while
  grandfathering untouched historical archives, active planning scaffolds,
  and symlinked context files.
- Identify SD pack source checkouts by the parsed manifest name rather than the
  generic presence of `install.py`, `manifest.json`, and `templates/`, so other
  installer repositories skip SD-only drift and hook checks.
- Fail conservatively, with a controlled diagnostic, when a malformed manifest
  asserts the SD identity or omits the fields required by the source gate.
- Explain when the source-hook advisory cannot verify pack identity because
  Python is unavailable instead of silently skipping hook configuration checks.

## 0.16.0 - 2026-07-17

- Added read-only installer self-inspection with human and schema-versioned
  JSON output: `--status` optionally runs the install audit, while `--check`
  always audits and returns exit `3` when a valid target needs a refresh.
- Validate installed receipts and vouched hashes before classifying a target,
  report installed and active platform adapters, and preserve the target
  byte-for-byte during every inspection mode.
- Removed the expired `REVIEW_PREFLIGHT_PR_BODY` compatibility fallback; use
  `SD_AI_COMMAND_PACK_SCOPE_PR_BODY` or the dedicated PR-body-scope variable.

## 0.15.8 - 2026-07-17

- Surface the tooling/generated PR-scope requirement early. `review-scope.sh`
  gains an `advisory` mode (`SD_AI_COMMAND_PACK_SCOPE_CHECK=advisory`) that
  classifies the working/branch diff and, when a scope-requiring file is
  present, warns naming the required PR body section (e.g.
  `Tooling/generated scope:`) with no `gh`/PR lookup and no failure. The shared
  review preflight now runs this advisory, so the local pre-PR gate reminds the
  author to add the section before the PR exists. The full-check hard-fail with
  a PR present is unchanged; `off`/`disabled` now also disable the checks.

## 0.15.7 - 2026-07-17

- Fixed `sd-ai-command-pack-housekeeping.sh` flagging a false
  "remote source branch still tracked" anomaly (nonzero exit) after a clean
  merge on remotes with GitHub's auto-delete-head-branch enabled. The branch
  is removed server-side at merge time, after the initial fetch/prune; the
  "already absent" cleanup path now prunes the stale local tracking ref so the
  final verification passes.

## 0.15.6 - 2026-07-16

- Add an explicit fast-canary fleet order and repo-owned lightweight
  compatibility checks, with anomaly-metric-creator last.
- Validate release candidates in disposable consumer-origin clones and require
  a payload-bound all-pass ledger before release PRs can merge or tags can be
  created.
- Document the rollout interruption threshold and keep consumer refresh review
  focused on installation, provenance, integration, and repo-owned changes.
- Make `sd-create-pr` pass custom Markdown bodies through literal temporary
  files and `--body-file`, preventing shell expansion of body content.
- Keep fleet payload digest framing uniform and make exact-commit tag checks
  resolve supported in-repo manifest symlinks like candidate validation does.
- Prevent candidate subprocess environments from adding an implicit
  current-directory search when the inherited `PATH` is empty.

## 0.15.5 - 2026-07-16

- Make the install audit's optional upstream-manifest read explicitly use
  strict UTF-8 decoding, preserving its existing advisory-only failure path
  while satisfying repository encoding-policy checks.
- Add regression coverage for malformed UTF-8 upstream manifests.

## 0.15.4 - 2026-07-16

- Route every shared SD skill invocation of a pack-owned Python helper through
  the shipped toolchain selector, preventing older system `python3` binaries
  from failing on the pack's Python 3.10+ syntax.
- Add regression coverage that rejects direct
  `python3 scripts/sd-ai-command-pack-*` invocations in shared skill templates.

## 0.15.3 - 2026-07-16

- Convert shared Git/GitHub helper `CommandError` failures in the shipped
  review-learnings command into its existing phase-tagged diagnostics and exit
  code `2` instead of leaking Python tracebacks.
- Add focused regression coverage for both local Git scanning and GitHub
  comment collection failures.

## 0.15.2 - 2026-07-16

- Make all variable-path cleanup in the shipped shell review and full-check
  tooling option-safe with `rm -f --`, including every temp-file path surfaced
  by fleet PR review.
- Add a regression guard that rejects unguarded variable-path `rm -f` cleanup
  in shipped shell templates.

## 0.15.1 - 2026-07-16

- Made `sd-fleet-refresh` a source-checkout-only operator command because it
  depends on the pack's installer, fleet registry, and rollout procedure.
  Consumer refreshes now retire vouched copies shipped by earlier releases,
  while the pack source checkout keeps its generated command surfaces.

## 0.15.0 - 2026-07-16

- Added a distributed review-preflight guard that treats Trellis journal
  history as append-only relative to the review base. It rejects accidental
  edits, removals, and renumbering of older sessions while allowing the newly
  appended/current session to be completed, preventing broad repeated-text
  replacements or whole-workspace deletion from corrupting historical records
  before remote review.
- Review-learning summaries now truncate at word boundaries while honoring
  their configured length limit.

## 0.14.2 - 2026-07-16

- Resolved audit-roadmap cleanup items: generated install receipts no longer
  pretend to have a manifest template source, installer apply can reuse
  preflight source bytes/digests, provenance prefers install-result digests,
  and review-scope fallback docs now name the `0.16.0` removal target.
- Documented coverage.py exemptions for shell/GitHub automation and corrected
  historical 0.7.1-0.7.4 changelog dates against the release tags.

## 0.14.1 - 2026-07-16

- Added a shipped `sd_ai_command_pack_lib.py` helper for common Python script
  behavior, moved four shipped helpers onto the shared git/command runner, and
  shared the shell `have()` probe through the shell helper.
- Hardened pack git/gh/Trellis subprocess calls with bounded timeouts and
  clearer timeout diagnostics in installer, audit, full-check, and
  housekeeping paths.
- Added manifest-backed scanner coverage so PR-body scope and install-audit
  static path tables fail tests when shipped manifest targets drift.

## 0.14.0 - 2026-07-16

- Restored the remote PR review round limit default to five
  (`SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_ROUND_LIMIT`; it was reduced to two in
  0.9.0 — the env var still overrides).
- Added review-cycle counters to the reports: `sd-review-pr` now reports
  `Remote review rounds used: <n> of <limit>` as a mandatory row, and the
  `sd-housekeeping` final state gains a mandatory `PR review rounds:` row
  (submitted reviewer review count for the merged/confirmed PR, or `n/a` on
  verification-only runs).

## 0.13.3 - 2026-07-16

- Hardened pack text writes: generated installer text files now report
  symlink conflicts instead of replacing in-repo symlinks, and the shipped
  recorder, review-learnings, and update-spec KB helpers write user-facing
  markdown/ignore files through temp-file + `os.replace` atomic writes. The KB
  refresh reports symlinked ignore files as partial refresh conflicts instead
  of silently writing through or replacing them.

## 0.13.2 - 2026-07-16

- Batched install-audit `git check-ignore` probes so each audit phase resolves
  candidate ignored paths with one `git check-ignore --stdin -z` subprocess
  instead of one subprocess per missing or unlisted pack-shaped path. Existing
  fail-closed behavior is preserved for missing git, non-repo roots, git
  errors, and the `check-ignore` exit-code-1 no-match case.

## 0.13.1 - 2026-07-16

- P3 polish batch from the 2026-07-15 audit (nine items). Shipped-payload
  changes: the review preflight's git subprocess calls now set an explicit
  64 MiB buffer and fail hard when git cannot run instead of proceeding with
  an empty diff; the preflight also caches its documentation file list and
  file reads per run; typing-only fixes in the session recorder and install
  audit. Repo-side: the install.py facade drops 42 unused re-exports, the
  installer modules gain responsibility docstrings, the REVIEW_PR_REMOTE_*
  variables are documented in the configuration references, review-learnings
  gains git-failure and untracked-diff tests, `make sync` wraps the dogfood
  install and KB refresh, `STRICT=1 make lint` turns missing-tool skips into
  errors, and mypy now covers install.py and the shipped scripts.

## 0.13.0 - 2026-07-16

- Generated the bespoke Claude/Gemini/GitHub command adapters and all derived
  manifest command entries from a single registry command list
  (`make generate` + a drift test); adding a command is now a skill, a neutral
  body, and one list entry. One-time canonical manifest reordering; entry set
  unchanged.
- Merged `sd-review-local-all` into `sd-review-local` behind the `all`
  argument (same runner, `--full-codebase`). The old command is removed;
  refreshes delete the retired installed files automatically when their
  content is vouched by prior provenance (drifted copies are preserved unless
  `--force`). Invoke `sd-review-local` with `all` for the full-codebase loop.
- Added `sd-ship`: a composite orchestrator sequencing the sd-create-pr flow,
  the sd-review-pr loop, the sd-watch-pr settle watcher, and the
  sd-housekeeping merge gate with `until=pr|review|merge` stop-points. It adds
  no new gate logic; every stage's own gates remain authoritative.

## 0.12.0 - 2026-07-16

- Added six distributed SDLC edge-loop commands, each with the full adapter
  surface and format-drift tests: `sd-watch-pr` (bounded PR settle watcher
  handing off to the housekeeping merge gate), `sd-fix-ci` (red-CI triage that
  classifies real/flake/infra failures and never weakens tests), `sd-update-deps`
  (sequential gated triage of dependency-bot PRs; majors always manual),
  `sd-fleet-refresh` (consumer fleet rollout per the documented procedure, one
  consumer at a time), `sd-test-gaps` (coverage-driven test authoring, test
  files only), and `sd-retro` (structured debug retrospectives recorded to the
  journal with consent-gated prevention proposals). All tuning is via command
  arguments — no new environment variables — and merge-affecting behavior
  defers to the existing housekeeping gate criteria.

## 0.11.0 - 2026-07-15

- Added the distributed `sd-audit-repo` command and shared skill: a formal
  multi-dimension repository audit that dispatches one read-only reviewer per
  charter (12 always-on dimensions plus fingerprint-selected consumer-impact,
  observability, and accessibility-i18n), adversarially verifies findings,
  reconciles them against the Trellis backlog, and produces a canonical report
  with mandatory sections backed by a committed findings ledger at
  `.trellis/audit/ledger.md`. Supports `dimensions=` filtering,
  `depth=quick|standard|deep`, and a `follow-up` mode that re-verifies open
  ledger items instead of re-sweeping the repository. The review preflight
  treats `.trellis/audit/ledger.md` as an optional documented path so repos
  that have not yet run their first audit pass the documentation path check.

## 0.10.5 - 2026-07-15

- Made the `sd-housekeeping` skill always report the current Trellis task and a
  `Next Steps` section listing the next high-value Trellis tasks / roadmap items,
  including on verification-only clean runs. Previously the report could end with
  "No follow-up needed for this cleanup stream." and omit the task inventory, so
  the end-of-run handoff format was inconsistent across repos. Documentation only
  — no command, flag, or script behavior change.

## 0.10.4 - 2026-07-15

- Internal micro-refactors of shipped helpers (no behavior change): unified the
  review-learnings git-command wrappers behind one runner, and precompute the
  PR-body scope rule's normalized glob patterns at rule-build time instead of
  re-normalizing them on every path match. Byte-identical output and exit codes.

## 0.10.3 - 2026-07-15

- Internal consolidation of shipped helpers (no behavior change): deduplicated
  the three inline git wrappers in the update-spec KB tool behind one helper,
  compute the source→destination mapping once per run instead of four times, and
  simplified the review-learnings GraphQL response walk. Byte-identical output
  and exit codes.

## 0.10.2 - 2026-07-14

- Trimmed the installed guide's verbatim per-platform `.gitignore` example to a
  single representative block plus a note that the installer regenerates the
  full per-platform set, and removed README prose that duplicated the guide's
  "Updating the pack" and "What is installed" sections. Documentation only — no
  command, flag, or behavior change; ~240 fewer lines across README and the guide.

## 0.10.1 - 2026-07-14

- Replaced the update-spec KB dry-run/`--check` conflict classification — which
  matched human-readable message suffixes — with structured issue kinds, so
  editing a display string can no longer silently change which entries count as
  conflicts. Emitted text and exit codes are unchanged.
- Micro-efficiency in shipped helpers (no behavior change): hoisted the KB
  category-title lookup out of the directory-walk loop, removed a duplicate
  `git status` on the session recorder's no-new-journal fallback, and made the
  review-learnings shell-shebang probe split once and cache its verdict per path.

## 0.10.0 - 2026-07-14

- Made remote PR review rounds use GitHub's documented Copilot request identity
  and require author-matched review activity before counting a request as
  materialized.
- Added plan-before-apply installer conflict handling, concurrent-run coverage,
  rollback guidance, and an optional fail-soft consumer version comparison.
- Hardened CI with SHA-pinned actions, bounded dependency updates, installer
  mypy coverage, OpenCode syntax checks, and a server-side direct-main scope
  backstop.
- Closed shell and housekeeping reliability gaps around disjoint histories,
  interrupt cleanup, delimiter parsing, default-branch detection, and per-user
  review-tool caches; refreshed contributor and security documentation.

## 0.9.2 - 2026-07-14

- Backfilled the missing release ledger and historical version tags since
  `v0.6.0`.
- Required every manifest version bump to add a matching top changelog release
  heading, and added post-CI automation that creates the corresponding tag on
  `main`.

## 0.9.1 - 2026-07-14

- Migrated the exact legacy Claude adapter ignore sequence into the managed
  `.gitignore` block without changing later project-owned overrides.
- Excluded generated Repomix maps from legacy-reference scans while retaining
  scans of their source documentation.

## 0.9.0 - 2026-07-11

- Added a distributed, Bash 3.2-compatible toolchain preflight that selects and
  verifies a supported Python once, reports project-check candidates without
  executing them, and provides deterministic JSON diagnostics.
- Updated SD workflow guidance to separate project checks, pack full-checks,
  and optional AI review while avoiding nested Git writes during finish-work.
- Reduced the default remote PR review loop from five rounds to two while
  retaining the environment-variable override for exceptional review cycles.

## 0.8.7 - 2026-07-09

- Bounded Prism and Gito provider calls, capped repeated Prism fallback
  failures, and tightened empty-response detection and Prism rules validation.
- Hardened the direct-main pre-push guard for rename and unusual-filename
  handling with NUL-delimited Git paths and behavioral coverage.
- Replaced installer wildcard imports with explicit public surfaces, restored
  Ruff import checks, and enabled import-order and Bugbear lint rules.

## 0.8.6 - 2026-07-09

- Fixed rollout CI blockers by classifying the installed pack manifest as
  generated SD command-pack state in review preflight and scope checks.
- Reworded shipped Copilot guidance and remove-mode docs to avoid optional
  directory/glob examples tripping consumer narrow-glob preflight checks.

## 0.8.5 - 2026-07-09

- Added a generated installed manifest snapshot and manifest-backed audit
  completeness checks, including explicit `--expected-platform` support for
  fleet refreshes.
- Added checked-in fleet inventory and a source-owned fleet preflight helper
  so at-target repos are skipped before opening refresh PRs.

## 0.8.4 - 2026-07-09

- Single-sourced OpenCode command adapters from the neutral command templates
  and added registry-derived parity coverage for thin command fan-out.
- Reconciled GitHub prompt body drift against the neutral command source and
  strengthened bespoke adapter body-parity tests.

## 0.8.3 - 2026-07-09

- Hardened `install.py --remove` so consumer-editable receipts and provenance
  can discover prior pack files but cannot authorize deletion of `.git/*` or
  arbitrary non-pack repository files, even when hashes match and `--force` is
  set.

## 0.8.2 - 2026-07-09

- Fixed session recorder retry safety for local-only or fresh workspaces where
  `.trellis/workspace/` is still untracked, so reruns patch the pending journal
  entry instead of appending duplicate sessions.

## 0.8.1 - 2026-07-09

- Made the session recorder retry-safe after a post-append staging or commit
  failure, so rerunning finish-work patches the pending journal entry instead
  of appending a duplicate session.
- Reconciled the closed fleet-refresh loop, archived stale rollout acceptance
  criteria, and the duplicate Session 29/30 journal entry.

## 0.8.0 - 2026-07-09

- Added the distributed `sd-work-designs` command and shared skill for working
  through Trellis tasks that still need `design.md` or `implement.md` planning
  artifacts.

## 0.7.5 - 2026-07-09

- Moved shared command adapter bodies to neutral templates and generated the
  OpenCode command surface from those sources.

## 0.7.4 - 2026-07-09

- Consolidated common shell helpers used by the local review runners while
  preserving the shipped script interfaces.

## 0.7.3 - 2026-07-08

- Added maintainer contributor workflow docs and a Makefile for setup, tests,
  linting, audits, and the SD full-check gate.
- Made the shipped full-check script warn in the pack source checkout when the
  `.githooks` pre-push guard is not armed.
- Pinned the OpenCode plugin dependency used by the dogfood platform files.

## 0.7.2 - 2026-07-08

- Fixed installed-guide quick links, documented
  `SD_AI_COMMAND_PACK_REVIEW_PR_SELECTOR`, and made the pack-source full-check
  env-var documentation gate cover shipped skill-only variables.
- Added maintainer guidance that `templates/**` are the shipped payload source
  of truth and replaced stale-prone README per-command platform lists with
  references to the supported adapter mapping.

## 0.7.1 - 2026-07-08

- Hardened `sd-ai-command-pack-review-preflight.mjs`: symlink invocation now
  runs the preflight instead of silently exiting, Node versions below 16.9 get
  a clear error, copied-surface checks include untracked files, workspace index
  parsing tolerates trailing whitespace, and the regular-file-only
  documentation scan behavior is documented.

## 0.7.0 - 2026-07-08

- Added the distributed `sd-work-backlog` command and shared skill for
  sequentially selecting implementation-ready Trellis backlog tasks, completing
  them through the normal `sd-create-pr`/`sd-housekeeping` flow, and recording
  or addressing follow-ups before moving to the next task.

## 0.6.1 - 2026-07-08

- Hardened the `sd-review-pr` wait-for-review step against a remote-review race:
  the completion signal (a reviewer request clearing / a review event) can fire
  before the reviewer's inline review-thread comments are queryable, so an
  immediate thread read can report a false "clean". The skill now waits a short
  settle interval before reading threads and treats the pre-merge unresolved-thread
  re-check (the housekeeping merge guard) as the authoritative clean check, never a
  single post-completion read.

## 0.6.0 - 2026-07-08

- Added the full-check Obsidian KB freshness lane
  (`SD_AI_COMMAND_PACK_FULL_CHECK_KB`) for repos that maintain generated
  `.obsidian-kb/` knowledge folders.
- Made `sd-ai-command-pack-update-spec-kb.py` return exit code 3 when a KB
  refresh is blocked by conflicts that need manual reconciliation.
- Hardened shipped scripts and audits across Bash 3.2 compatibility,
  all-platform install-audit coverage, PR-body scope matching, review-runner
  robustness, recorder/housekeeping behavior, and KB runtime exclusions.
- Added a release guard in full-check so shipped payload changes under
  `templates/**`, the installed usage guide, or `manifest.json` must include a
  manifest version bump.
- Started the release log and tag process at `v0.6.0`; earlier versions remain
  traceable through git history but are not retroactively changelogged here.
