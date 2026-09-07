# Design — the sweep trusts a branch field it never resolves

## Approach

### The exclusion goes; an annotation replaces it

`bin/sd_sweep.py:91` reads:

```python
if item.status != SWEEPABLE_STATUS or item.branch:
    continue
```

The `or item.branch` clause is deleted outright. It is not made smarter — a
smarter exclusion is still an exclusion, and criterion 5 says liveness is
advisory. After the cut, every non-archived, non-parked `planning` item past
the age threshold is in `due`, whatever its `branch:` field says, and the field
buys an annotation instead of an escape.

Three annotations, on the row beside `branch`:

| `branch_state` | meaning |
|---|---|
| `live` | the name resolves to a head this root publishes or holds |
| `gone` | the root answered, and no head has that name |
| `unknown` | git could not be asked, or refused |

An item with no `branch:` field carries no annotation at all. Absence of a
claim is not a claim that cannot be checked, and giving it `unknown` would put
every item in the repository into the state criterion 4 reserves for a broken
root.

### Two queries per root, never one per item

`sweep()` already walks `(where, root)` pairs, so the root is in hand exactly
where the query belongs. A new `branches(root)` runs two commands and unions
the result:

```
git ls-remote --heads <remote>        # every published head, no branch argument
git for-each-ref --format=... refs/heads
```

It returns a `frozenset[str]` of short ref names, or `None` when git could not
answer. `sweep()` calls it once per root and hands the answer to `scan()`.

**The remote query takes no branch argument.** C-20 on the parent item found
the reason: a query filtered by one item's branch can only classify that item,
and a second remote-only branch in the same root comes back `gone` because it
was never asked about. Fetching every head and matching locally classifies all
of them from the one answer.

**Local refs are consulted as well as remote ones.** A branch created here and
not yet pushed is live work, and calling it `gone` would sweep exactly the item
somebody just started. The union is the answer; either source suffices.

### Why `scan()` receives the set rather than building it

`scan(root, today, days)` gains a fourth parameter, `branches: frozenset[str] |
None`. It could resolve the set itself — it has the root — and that would be
one less argument. It does not, for two reasons.

The first is criterion 3. Resolution is per-root, and the way to prove a
function is per-root is to give it a different answer per root and watch the
classification differ. A `scan()` that reaches for git itself can only be
tested against whatever repository the test happens to run in.

The second is criterion 4. "git cannot answer" has to be reachable in a test
without a broken git binary. As a parameter it is the literal `None`; as an
internal call it needs a fixture root that is not a checkout, which tests one
of the two ways git fails and not the other.

### `unknown` is said once per root, not once per item

Criterion 4 says a failing root "annotates every item inside it unknown and
says so once per root". The per-root line lives in `render()`, keyed off the
root's own `branches` result rather than off counting item annotations:
a root with no branch-carrying items still failed its query, and a report that
stayed silent about it would claim a clean answer it never got.

The repo row gains `branches: "ok" | "unknown"` for that line. It is a
different fact from any item's annotation and is not derived from one.

**"Every root" means every root the report prints.** `sweep()` already drops a
root with no live items (`bin/sd_sweep.py:128`), and `render()` skips a
root with nothing due and nothing undated (`:148`). A root filtered out
there has no annotated item to explain, and printing a query failure for it
would put a line in the report about a repository the report is otherwise
silent on. The line is attached to the root's own heading and appears exactly
where that heading does.

### A root with no remote is answered, not unknown

`sd_lib._upstream()` returns `""` for a checkout with no remote: with no
remotes, `names` is empty, so `fallback` is `""` and no `tracked` value can
beat it. That is not a failure. A repository with no remote holds every branch
it has, so local refs alone are the complete answer and the annotations are
`live` and `gone` as usual. `unknown` is reserved for a root that is not a
checkout at all and for a git invocation that returns non-zero — the two cases
where the answer is missing rather than empty, and both of them the two ways
`sd_lib._git` returns `None` (`bin/sd_lib.py:136-139`).

**`_upstream` becomes `upstream`, and the change is a rename.** It is private
today and `bin/sd_skill.py:217` already reaches across for it, carrying a
`noqa: SLF001` and the comment "the one reader of this fact". This design would
make a second reader, which falsifies that comment and adds a second `noqa`
rather than removing the first. Duplicating the remote-selection rule in
`sd_sweep` is worse: it is three fallbacks deep — HEAD's upstream, then
`origin`, then the first remote listed — and a second copy would drift. So the
name loses its underscore, its three call sites follow, and one `noqa` and its
comment go with it. Net zero lines under `bin/`.

### Exact ref names, and nothing cleverer

`ls-remote --heads` prints `<sha>\trefs/heads/<name>`, `for-each-ref
--format='%(refname:short)' refs/heads` prints `<name>`; the first is stripped
to the second's shape and the two sets are unioned. Matching is string
equality against the `branch:` field as written. A field written
`origin/task/thing` is annotated `gone` — correctly, since no head has that
name — and this design does not try to normalise it. Every `branch:` field in
the repository today is a bare name, and guessing at a remote prefix is how a
`gone` branch gets read as live.

### What this breaks in the existing suite

`tests/test_sd_sweep.py:78`,
`test_a_branch_field_protects_an_old_planning_item`, asserts the exclusion this
item deletes. It is not a regression to be repaired: its premise is the defect.
It goes, and the annotation tests of criteria 1 through 5 take its place. The
test module's own docstring (`:5`) lists three exclusions and must list two,
and `SWEEPABLE_STATUS`'s comment in `bin/sd_sweep.py:46-48` says a `branch:`
field "claims a branch exists for the item" — the sentence this item was
written about — which becomes the annotation's description.

`scan()`'s fourth parameter defaults to `None`, so the eleven surviving tests
that reach it through the module's own `scan()` helper (`:47-48`) keep
compiling — twelve of the eighteen call the helper, and one of those twelve is
the exclusion test that goes. The default is not a convenience: `None` is the honest answer for a
caller that did not ask git anything, and it is the same value criterion 4
assigns to a caller whose git could not answer. A default of "empty set" would
have silently annotated every item `gone`.

## Validation

Criteria 5 and 6 put two requirements on the tests that the approach above does
not by itself satisfy, so they are settled here.

**A recording git, not a recording remote.** Criterion 5 asks a fixture with
two remote-only branches to assert that "the recording remote answered exactly
one query". Nothing here talks to a remote directly — `sd_lib.git_output` runs
`git`, and `git` talks to the remote — so the recorder goes where the calls
are: a `git` executable earlier on `PATH` that appends its argv to a log file
and prints a canned `ls-remote` answer. `tests/test_sd_suggest.py` already
ships that shape for `gh` (`GH_RECORDER`), and this reuses it rather than
inventing a second mocking style. The assertion is then a count of `ls-remote`
lines in the log, which is one whether the root holds two branch-carrying items
or twenty — the property criterion 5 is actually about.

**The count-is-unchanged assertion is one test over three fixtures.** Criterion
5 asks that the report's item count be the same across `live`, `gone` and
`unknown`. Three separate tests each asserting their own count would pass while
disagreeing with each other; one test that builds the same item three times,
varies only what the recording git answers, and asserts the three reports have
equal `due` length is the assertion the criterion describes.

**The mutation set of criterion 6, and where each one dies.**

| mutation | the test that fails |
|---|---|
| `live` and `gone` swapped | the count-is-unchanged test still passes — it is the per-annotation tests of criteria 1 and 2 that catch this, which is why both must assert the annotation and not only the listing |
| the per-root argument replaced by a fixed root | criterion 3's two-root fixture, where the same branch name is live in one root and absent in the other |
| the "git cannot answer" path made to report `gone` | criterion 4's non-checkout root, which must annotate `unknown` and print its once-per-root line |

The first row is the reason criteria 1 and 2 are two tests rather than one
parametrised over a boolean: a swap that preserves the listing is invisible to
any assertion about the listing.

## Decisions

**D1 — the exclusion is deleted, not repaired.** Considered: resolve the branch
and exclude only when it is live. Rejected. It keeps a gate whose failure mode
is silence, and it makes `unknown` load-bearing — a root whose remote is down
would hide every branch-carrying item exactly as today. Criterion 5 settles it
in the item's own words: *never an exclusion*.

**D2 — the annotation is a string, not a boolean plus a flag.** Two booleans
(`live`, `checked`) encode four states for three, and the fourth — not live,
not checked — reads as `gone` to anything that tests `live` alone. One field
with three values cannot be misread that way.

**D3 — `render()` shows the annotation inline, and adds no section.** The
item's open question 2 asked whether a stale branch deserves its own line.
Criterion 5's "every item past the age threshold is in the report" already puts
them in one list; a second list would mean deciding which one an item belongs
to, and the annotation carries that without a second decision. `gone` and
`unknown` print; `live` prints; an item with no `branch:` prints as it does
today, which is what makes the annotation visible rather than ambient.

**D4 — `done` items stay out of scope.** Open question 3. They are excluded by
status before the branch field is read, and this change moves neither boundary.
The dangling claim on a `done` item is real and costs nothing today, and
picking it up here would mean sweeping items the sweep is not for.

**D5 — no caching.** Criterion 5 says *one fresh remote query per root*. A
cached observation is what C-7 rejected: remote-tracking refs survive a deleted
branch until `git fetch -p`, so anything read from the ref store answers about
the last fetch rather than about the remote. Two subprocesses per root, on
every run.

## Risks

**The remote query is a network call in a function that had none.** `scan()`
read the filesystem and nothing else, and `sd sweep --fleet` walks every
checkout under `SD_REPO_ROOT`. Thirteen checkouts is thirteen `ls-remote`
calls, each a round trip. That is the cost criterion 5 chose over a cache, and
it is bounded by root count rather than by item count — the shape that stays
flat as the backlog grows. `git_output` already carries the timeout, so a
hanging remote fails to `unknown` rather than to a hung sweep.

**A shared branch name across repositories still misleads a reader, not the
code.** Two checkouts each holding `main` is normal, and each is classified
against its own root. The report prints the annotation beside the item, under
the repository heading it belongs to; nothing compares names across roots. The
failure this rules out is the code's, and the reader's remains theirs.

**`bin/` headroom.** The directory stands at 17,123 against `BIN_CAP` 17,250 —
127 lines. This adds roughly fifty. It fits, and the cap-raise rule means a
miss is not absorbed here: it is a re-derivation in its own pull request first,
touching nothing under `bin/`.
