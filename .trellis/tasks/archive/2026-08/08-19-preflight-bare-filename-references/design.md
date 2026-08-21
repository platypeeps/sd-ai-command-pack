# Design — validating bare-filename documentation references

## Authoring boundary

`templates/**` is the source of truth (CONTRIBUTING, "Release And Payload
Rules"). The checker exists in four byte-identical copies:

```
templates/scripts/sd-ai-command-pack-review-preflight.mjs   <- edit here
scripts/sd-ai-command-pack-review-preflight.mjs             <- `make sync` (install.py . --force)
plugins/sd/bin/sd-ai-command-pack-review-preflight.mjs      <- `make generate`
plugins/sd/machine-payload/scripts/sd-ai-command-pack-review-preflight.mjs
```

`tests/**`, `.trellis/spec/**` and `.trellis/tasks/**` are repo-local and do not
participate in the mirror.

## The shape of the problem

One lane is in scope: `checkDocumentationPathReferences()` at
`scripts/sd-ai-command-pack-review-preflight.mjs:3180-3218`. Its pipeline:

```
documentationGuardFiles()                   -> the guard corpus
  exemptions                       :3184-3194
  extractDocumentationPathReferences :5070   -> code spans + markdown links
    shouldCheckDocumentationPathReference :5133  -> eligibility
    isAbsentPathMarked                    :5066  -> point-of-use escape
  resolveDocumentationReference    :5197     -> reference text -> repo path
  findMissingDocumentationPathReferences :5011
    exists() probe                 :3204-3207
    resolvesToLineSuffixedPath     :5049-5057  -> strips `:12-34` and retries
```

Eligibility ends at `:5179`:

```js
return referencePrefixes.some((prefix) => normalized.startsWith(prefix));
```

A bare filename has no `/`, matches none of the 26 `config.referencePrefixes`
(`:357-384`), and unless it is one of the eight `config.topLevelReferenceFiles`
(`:385-394`) returns false. Verified live: `shouldCheckDocumentationPathReference('review.py')`
returns `false`.

Widening this needs two things the pipeline does not have: a way to turn a
basename into a repo path, and a way to tell a *citation* from a *noun*.

## The central decision: locator form, not basename existence

A prefixed reference is unambiguously a locator — nothing but a path looks like
`scripts/foo.py`. A bare filename is not. Prose uses one as a noun constantly,
and the corpus shows the noun sense dominates. Inspecting every bare filename
that resolves to no tracked file:

| Reference | What it actually is |
|---|---|
| `coverage.py` | the name of a Python package, twice |
| `a.sh`, `b.py` | literal placeholders in a worked example |
| `MIGRATED.md` | a tombstone filename from a *rejected* proposal |
| `Dashboard.md`, `LLM-KB.md` | legacy generated names, cited in the rule that removes them |
| `USER_DATA.txt` | a hypothetical unsafe path in a test scenario |
| `journal-N.md` | a filename *pattern*, with `N` standing for a number |
| `update.ts`, `regression.test.ts` | files in the upstream Trellis repository |
| `ci.yml`, `sd-ai-command-pack-sync.yml` | files in consumer repositories |
| `test_review_local.py` | named in the sentence recording its own deletion |

None is a typo. Every one is a filename used as a name. Demanding that these
resolve is not a stricter gate, it is a wrong question — and answering it costs
160 failures across 43 documents.

Line-cited references are the opposite. A noun does not carry a line number.
`review.py:555` is a claim about a specific file at a specific offset, and it is
exactly the class Copilot flagged on PR #339. Restricting the widening to
locator form keeps the high-precision half and discards the noise:

- **107 locator-form references become newly checked and pass** — `review.py`,
  `install.py`, `task_store.py`, `shell-lib.sh`, `work-loop.py`,
  `review-preflight.mjs` and 30 other names.
- **4 fail**, all inspected, all real.
- 59 noun-form references stay declined, for a stated reason rather than by
  accident of missing a `/`.

The 107 is exact and decomposes as 95 + 12. `research/measure-proposed.mjs`
buckets 95 locator-form references as resolving to a unique or mirrored
candidate set, and a further **12** — across `SKILL.md`, `design.md`,
`implement.md` and `prd.md` — land in its `ambiguousDistinct` bucket. Those pass
too: under the final rule resolution succeeds whenever the index returns ≥ 1
candidate, and R3 forbids reporting a multi-match name as missing. The script
prints all three figures, so the decomposition is re-derivable rather than
asserted. 107 + 4 + 556 = 667, the whole skipped population at `09993578`.

This also answers R7. A consumer's prose nouns stay declined, so a repository
whose corpus this project has never measured cannot go red on
`coverage.py`-shaped text. The only class that widens for consumers is line-cited
filenames, which in any repository is the class most likely to be a genuine
citation.

## Resolution rule

Exact, closed, and enumerable. Given a reference target with no `/`:

**1. Eligibility — shape only, never the index.** All existing disqualifiers at
`:5140-5165` apply unchanged. Additionally, the target is a bare-filename
candidate only when, after stripping the line suffix, it matches
`BARE_REFERENCE_PATTERN`:

```
^\.?[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_])?\.<ext>$
```

where `<ext>` is an alternation over `config.bareReferenceExtensions`. The
leading `\.?` is what admits `.mcp.json`; `.gitignore` still fails, because no
allowed extension follows (and it is already a `topLevelReferenceFiles` entry).

`..` is rejected by a **separate explicit guard**, not by this pattern. The
middle character class contains `.`, so `a..b.py` matches the regex — a reader
who assumes the pattern alone excludes traversal is wrong. Both the guard and
the pattern are published here because both are load-bearing, and
`research/measure-proposed.mjs` implements exactly this pair.

Eligibility does **not** consult the basename index. `nope-xyz.py:9` is eligible
and is reported missing at resolution; that is R1's failing half, and the whole
reason the task exists.

**2. Locator form.** The target must carry a line or range suffix. This is
tested with the *same* regex `resolvesToLineSuffixedPath` uses at `:5056`,
hoisted to a module constant `LINE_SUFFIX_PATTERN` so the two cannot drift.
A bare filename without a suffix is declined here, and that decline is R4.

**3. Basename index.** One `git ls-files -z` call, cached for the process,
grouped basename -> tracked paths. One batched query for the whole corpus
satisfies R8. `git ls-files` is the right source rather than a filesystem walk:
the gate is about references to *repository content*, and a build artifact
sitting in the working tree should not make a stale citation resolve.

**4. Lookup, in order:**

```
a. index[name]                          -> exact basename
b. index['sd-ai-command-pack-' + name]  -> hyphen script convention
c. index['sd_ai_command_pack_' + name]  -> underscore module convention
```

Steps b and c are skipped when `name` already starts with that prefix. **That is
the entire transformation set.** No substring containment, no edit distance, no
suffix scan — a closed list of two prefixes, both literally the pack's own name,
which is why R2 can be asserted by a test that an arbitrary near-miss does not
resolve.

The two prefixes are not arbitrary: they are the pack's file-naming convention
in its two forms, hyphens for executables and underscores for importable Python
modules. Measured, they recover 97 of the 160 would-be failures — `review.py`,
`full-check.sh`, `fleet_lib.py`, `shell-lib.sh` and 30 other names.

**5. Outcome.** The first step that returns a non-empty candidate list resolves
the reference and it passes. All three steps empty means unresolved, and a
locator-form unresolved reference is reported missing, reusing the existing
message verbatim.

### Where this hooks in

`shouldCheckDocumentationPathReference` gains the eligibility half (steps 1-2)
only. It takes **no** new parameter: steps 1-2 are pure shape tests over the
target string, so the index has no business there. An earlier draft threaded
`options.trackedBasenames` into it; that is removed. It would have been a dead
parameter at best, and at worst the thing that collapses "eligible" into
"resolves" and destroys R1's failing case.

`resolveDocumentationReference` gains the lookup half (steps 3-4) and receives
the index through its existing `options` bag, defaulting to the cached git
query.

**It must be exported.** At `:5197` it carries no `export` keyword while 40
sibling functions in the same module do — verified at `7f02caaa`. R2 (the prefix
set is closed) and R3 (multi-match resolves rather than failing) are both claims
about *resolution*, so with the function private they are reachable only through
a full end-to-end run against a real repository. Exporting it is what lets the
closed-prefix assertion be written at all: a near-miss name is eligible by
shape, exactly as `nope-xyz.py:9` is, so asserting it against the eligibility
predicate can never falsify the prefix set.

`findMissingDocumentationPathReferences` is unchanged. It already threads
`options` through to both functions, and its injected `existsPath` callback keeps
working: a resolved bare filename becomes a real tracked path, which the existing
`exists()` probe answers `true` for by construction.

### One git query, not one per reference (R8)

The naive implementation calls `git ls-files` inside the resolver, which runs
once per bare reference — 667 subprocesses on this corpus. The index is built
once and memoised in a module-level cache beside `installedTargetsCache` and
`documentationGuardFilesCache` (`:35-36`), reset in the same block at
`:307-308`. `08-02-speed-review-preflight-inproc-install` exists because this
gate's process cost was already a problem once; R8 is asserted by a test that
counts invocations rather than left to inspection.

### Config surface and fail-closed behaviour

`bareReferenceExtensions` joins the `loadConfig` merge list at `:451-467`,
which takes the `Array.isArray` / `typeof value === 'string'` path. That gives
R9 for free by construction, in the same shape as the seven existing arrays: a
malformed value is dropped and the built-in defaults survive, so references stay
*checked*. A malformed config file as a whole already fails the run at `:447`.

Note the merge is a **union** — a consumer can widen the extension set but not
narrow it. That is the correct direction for a gate, and it matches every other
array key.

## Mirror collapse: measured, and subsumed

The rescope brief asked for a rule that treats candidates differing only by
being the same logical file in `scripts/`, `templates/scripts/`,
`plugins/sd/bin/` and `plugins/sd/machine-payload/scripts/` as resolved rather
than ambiguous, on the expectation that this recovers most of the multi-match
class. Both halves of that expectation were tested and neither holds.

**It does not recover most of the class.** Classifying every multi-match name by
content hash: 203 references belong to true mirror sets, and **212 references
across 11 names are genuinely distinct files**. `SKILL.md` has roughly 130
tracked candidates across nine agent surfaces; `prd.md`, `design.md`,
`index.md`, `task.json`, `settings.json`, `check.jsonl` and `implement.jsonl`
are structural names that identify no particular file at all. No mirror rule
touches these.

**It changes no outcome.** R3 requires that a multi-match name is not reported
as missing. "Resolved as a mirror set" and "declined as ambiguous" are therefore
the same observable result — pass. The distinction is invisible to the gate.

**It has a real cost.** Detecting mirrors by content identity means hashing
every candidate, including all 130 `SKILL.md` copies, on every run of a gate
whose speed was the subject of `08-02-speed-review-preflight-inproc-install`.
Detecting them structurally instead means a hard-coded table of mirror roots —
which is precisely the fact the `08-09-thin-*` and `08-10-thin-*` tasks spent a
month changing, so the table would be stale maintenance from the day it landed.

**Decision: do not implement it.** Resolution is "the index returned at least
one candidate". Mirror sets and genuinely-distinct sets both pass, which is what
R3 demands anyway, and no hashing or mirror-root table is needed.

This is cheap to revisit and the measurement is checked in. What would make
mirror collapse load-bearing is a future decision to *fail* on genuine
ambiguity — at which point the 203/212 split becomes the thing to act on, and
`research/measure-proposed.mjs` already computes it. Recorded so it is not
re-derived from scratch.

## Residual policy: point-of-use `[absent: <reason>]`

Four references need a disposition. The three candidate mechanisms:

| Mechanism | Verdict |
|---|---|
| Report as missing, fix the prose | Rejected — the referenced things are *supposed* not to exist. Rewriting a retirement record to stop naming the surface it retired damages the record to satisfy a gate. |
| `optionalReferencePaths` in `.sd-ai-command-pack/review-preflight.json` | Rejected — see below. |
| `[absent: <reason>]` at the point of use | **Chosen.** |

The config route fails on two counts. First, the file does not exist in this
repository — `git ls-files .sd-ai-command-pack/` returns `bin/`, `check.json`,
`manifest.json` and `review.json` only, so adopting it means creating a tracked
config file to carry four entries. Second, and fatally, `optionalReferencePaths`
is matched against the normalised full path at `:5167`; a bare `ci.yml` never
equals a qualified entry. Making it match would mean either bare-name entries or
basename-aware comparison, and both turn a path allowlist into a **global
filename suppression list** — one `ci.yml` entry silences that name in every
document, forever, including a future genuine typo. That is a much larger blast
radius than the problem.

The marker is the right size. It is per-reference, carries a required reason,
fails closed on every malformation, is already shipped and already tested, and
was built by `08-08-preflight-absent-path-prose` for exactly this class. Four
markers, each stating a fact worth stating:

| Site (located by content — these files move) | Marker reason |
|---|---|
| `08-07-default-local-review-lanes/prd.md` | surface deleted by `07-24-remove-retired-review-surfaces` |
| `08-08-upstream-handoff-register/prd.md` | upstream Trellis repository |
| `08-09-deployment-thin-consumers/research/consumer-ci-usage.md` (twice) | consumer repository |

The last three are foreign-repository references, which R5 keeps out of scope —
the marker is how "out of scope" is *expressed* at the point of use, and its
reason names the owning repository as the 2026-08-07 operator decision requires.

Noun-form references get no marker. They are declined by rule, not suppressed
by annotation, which is the difference between the 4 sites above and the 59 that
need no edit at all.

## Compatibility and rollout

The change is additive to eligibility. Every reference checked today is checked
identically afterwards: the new logic is reached only on the `:5179` return
path, which today answers `false` for every bare filename. No existing prefix,
top-level file, relative-link or absent-marker behaviour moves.

Staged, with a measurement gate between each step:

1. **Measure first.** Run `research/measure-baseline.mjs` and
   `research/measure-proposed.mjs` on the current HEAD and record the
   locator-form residual. The corpus is live — it shifted three guard files
   mid-planning when another session archived a task — so the snapshot in
   `prd.md` is a shape, not a number to trust.
2. **Fix the corpus before enabling the rule.** Add the four markers and
   re-measure. `measure-proposed.mjs` must report a locator-form residual of
   **zero** before any checker edit lands. Markers are inert until the rule
   ships, so this step cannot break the gate.
3. **Enable.** Edit `templates/`, propagate, run the full gate.
4. **Verify against the real checker**, not the model. The measurement scripts
   import the real `shouldCheckDocumentationPathReference` but reimplement the
   guard walk, so they can agree with a checker that is still wrong. The
   binding check is the preflight's own exit code.

Ordering steps 2 before 3 is the whole safety argument: the gate is never red
between commits, and a bisect lands on a green tree at every point.

## Rollback

`git revert` of the merge commit. Nothing here writes persistent state,
migrations or consumer-side files. The four markers are inert prose once the
rule is gone, so a partial revert of the checker alone is also safe.

Consumers are unaffected until the next pack release reaches them, and the
widening they receive is bounded to line-cited filenames by construction.
