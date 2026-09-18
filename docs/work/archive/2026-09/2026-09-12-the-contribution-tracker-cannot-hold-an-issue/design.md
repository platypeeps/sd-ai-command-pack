# Design — the-contribution-tracker-cannot-hold-an-issue

## The boundary verdict, first

This item edits code in two repositories. That is the first thing to settle,
because sd:392 files the boundary between them as a cycle, and a design that
adds coupling to a known cycle without saying so is the defect.

**Verdict: sequenced through the boundary, not blocked behind it.** The
argument, from measurements taken on 2026-09-12, not from either item's body:

**What sd:392 says is broken.** Pack CI checks out the private `system`
repository with a PAT to obtain `sd_db`; pack test modules import it, which is
why a bare public checkout fails collection; and the cycle closes the other way
at a system test that executes this pack's `bin/sd-ship`. Its stated fix has
two halves — `sd_db` becomes a built, tagged package, and the two system tests
driving `bin/sd-ship` move into the pack.

**Half one is under way, and this pack already consumes the part that exists.**
The distinction matters, because half one as defined three lines above is a
*tagged* package and there is no such tag: the library is built but not
released. sd:392's own body calls the packaging half "under way", and its note
records that system still does not own `sd_db` as a tagged release. What has
landed is the build: `local-sd-db/pyproject.toml` sets
`build-backend = "_build"` with `backend-path = ["."]` and an empty `requires`,
so the build needs nothing from an index. Pack CI installs a built,
non-editable copy —
`.github/workflows/tests.yml:103` runs
`python3 -m pip install "$HOME/repos/system/local-sd-db"`, and the comment
directly above it states the rule ("A built copy, never `-e`") and names the
test that asserts it.

**Half two has not started.** The reverse edge is live. In the system
repository, `local-sd-runner/tests/test_ship_lifecycle.py` line 30 resolves a
`PACK` path from `SD_ACCEPTANCE_PACK`, and line 43 skips the whole class unless
`PACK / "bin/sd-ship"` is a file. A second module, `test_hard_stops.py`, writes
a stub at the same path. Neither has moved.

**Neither half gates this item.** This work touches the contribution modules
and this pack's two readers. It does not touch `bin/sd-ship`, so the unmoved
tests are irrelevant to it. It does not need a tagged release, because the
commit-pin path already works and has been exercised: the comment at
`.github/workflows/tests.yml:74-79` records the pin last moving for
`record_check`.

**But this item pays the boundary's cost, and must budget for it.** Pack CI
pins the library at a commit — `.github/workflows/tests.yml:84` reads
`ref: 3c4c723a724c5922fb464042a036ded0408a3d51`. The same comment block records
the failure mode precisely: for `record_check`, "the reader landed before this
pin could see the writer, so CI failed on an ImportError that no local run
reproduced, every local venv already carrying it." This item adds a reader
change and a writer change on opposite sides of that pin, so it will reproduce
that failure exactly unless the landing order in `implement.md` is followed.

**The honest cost, stated rather than hidden.** This item does not *fix* the
cycle and it does not *worsen* it — it adds no new import edge in either
direction, only new fields across an edge that already exists. What it does is
raise the price of sd:392 staying open by one more three-step landing. That is
an argument for doing sd:392 sooner; it is not an argument for holding this
item, because holding it would leave sd:244 unwatched for the duration.

**A drift worth recording.** sd:392's body says the pack pins
`system@89dcd866` and that twenty pack test modules import `sd_db`. Measured
today the pin is `3c4c723a72…`; the module count is **22** by an actual
`import`/`from sd_db` statement and **28** by any mention of the string, so the
right correction depends on which was meant and the import count is the one
that governs collection. The collection-error count in the same item has
drifted too: a `pytest tests/ --collect-only -q` at cc93ea85 reports **21**
errors, not 19, and all 21 are the single cause
`ModuleNotFoundError: No module named 'sd_db'`. Those numbers belong to sd:392,
and a note carrying all three corrections now exists on that item; they are
recorded here because this design was written against them.

## Approach

**Extend the existing contribution row; do not add a second kind.** An issue and
a pull request are the same thing to a reader — upstream work that may need you
— and the whole value of the row is that `bin/sd-status` and the dashboard give
one needs-you answer. A parallel `issue` kind would mean a second projection, a
second lane assignment and a second sort, and every reader would have to merge
them. This is also the reason the pull-request row gave for absorbing unfiled
branches rather than splitting them out.

**Rejected: widen the existing URL validator.** The obvious change is to let
the pattern at `sd_db/contributions.py:34` match `/issues/` as well as `/pull/`.
It is wrong, and quietly so. That validator is not only `pull_url`'s — it is
also the validator for the `merge` dependency's `url` and for the `release`
dependency's `contains_pull`. Widening it would let an issue URL be accepted as
proof that a pull request merged, which is a false *satisfied* verdict on a
dependency, not a cosmetic error. An issue URL gets its own pattern and its own
validator, and the pull-request one stays exactly as strict as it is.

**Rejected: carry the draft body in the row.** `draft_path` is a path plus a
digest, not the text. The row lives in a database that is backed up and synced;
an unfiled bug report about somebody else's project is a document, and putting
document bodies in the metadata store makes the store the wrong size and the
wrong shape. The digest gives the property that matters — the draft that was
reviewed is the draft that gets filed — and it reuses the evidence-artifact
mechanism at `sd_db/contributions.py:126-142` rather than inventing a second
one.

**Rejected: model an unfiled issue as an unfiled branch.** It is the closest
existing shape and it does not fit: the unfiled-work rule at
`sd_db/contributions.py:191-192` demands a clone and a branch, and a bug you
found in a project you have not cloned has neither.

## Decisions

**D1 — identity is exactly one of three, enforced in one place.**
`_configuration` is already the single gate every write passes through; the
mutual exclusion goes there beside the existing unfiled-work rule, not into the
CLI. Decided 2026-09-12 by this design. Reversed if a row ever legitimately
needs both — an issue that became a pull request — at which point the answer is
a `filed_as` transition, not two live URLs.

**D2 — a new dependency kind is a nine-place change, and that is the same
defect as the recited field lists, not a routine cost.** The `depends_on` kind
is enumerated independently in **nine** places across three modules and two
repositories, with nothing checking that they agree — exactly the shape sd:602
names for the field lists. Listing nine edits as though they were routine would
be recording the tax and calling it a plan. They are enumerated here so that
none is missed *and* so that the count is on the record as an argument for
collapsing them:
1. the `allowed` map at `sd_db/contributions.py:160-161`;
2. the cycle walk at `sd_db/contributions.py:211`, where only `item` recurses;
3. the satisfaction predicate, `_satisfied`, at `sd_db/contributions.py:471`;
4. the remote-cost table `DEPENDENCY_REQUESTS` at
   `sd_db/contribution_sync.py:27`, which today prices `merge` at 1 request and
   `release` at 7;
5. the remote collector `dependency` at `sd_db/contribution_github.py:295`,
   whose guard at `sd_db/contribution_github.py:365-366` raises
   `unsupported remote dependency kind` for anything but `merge` and `release`
   — `release` is handled just above at `sd_db/contribution_github.py:310`;
6. the local-versus-remote split in `observe_dependencies` at
   `sd_db/contributions.py:522`, where `item` is resolved in-process and
   everything else must arrive as a supplied observation or the row is held at
   `sd_db/contributions.py:528-529` with `Dependency state is unknown`;
7. the mirror of that split in the collector, `sd_db/contribution_sync.py:181-182`,
   which sends every non-`item` dependency to the GitHub collector — so a new
   kind reaches place 5's guard whether or not place 5 was taught about it;
8. the cost function `_cost` at `sd_db/contribution_sync.py:74`, whose
   `DEPENDENCY_REQUESTS.get(dependency["kind"], 0)` prices an unknown kind at
   **zero** requests, silently under-reserving budget rather than failing;
9. the release/merge cross-proof at `sd_db/contributions.py:536-537`, which
   names both kinds by string to check that a satisfied `release` contains the
   configured merged commit.
A change that stops after place 1 produces a kind that validates, never
resolves, and never says why — and places 6, 7, 8 and 9 are precisely where
that happens without an error. Decided 2026-09-12; reversed only if the
dependency machinery is consolidated into one table first, which would be a
better change and is not this one.

**D3 — issue events extend the existing vocabulary rather than forming a second
one.** The accepted kinds at `sd_db/contributions.py:451-452` are `comment`,
`label_added`, `label_removed`, `converted_to_draft`, `ready_for_review`,
`closed` and `reopened`. Issues reuse `comment`, `label_added`,
`label_removed`, `closed` and `reopened` unchanged. Two are new and both are
genuinely new information: `closed_completed` and `closed_not_planned`, because
the PRD requires them to be distinguishable and GitHub reports the reason as a
separate field rather than a separate event. `converted_to_draft` and
`ready_for_review` simply never occur on an issue.

The kind list is not the only list. The *triggers* in `_pull_attention` decide
which kinds raise attention, and they are narrower than the vocabulary: a
`comment` fires only for a maintainer or an `@`-mention
(`sd_db/contributions.py:359`), and a `label_added` fires only for a configured
blocking label that is currently applied (`sd_db/contributions.py:361-362`).
This design deliberately **widens the comment trigger on the issue path only**:
on an upstream issue the operator filed, any non-author comment is the signal,
because there is no review machinery to carry it. The label trigger is not
widened. Recording this is the point — porting `_pull_attention` unchanged
would satisfy requirement 5's vocabulary and still notify nobody. Decided
2026-09-12; reversed if any-comment proves too noisy in practice, at which
point the fallback is the existing maintainer/mention predicate, not silence.

**D4 — the fix and its test both target the *text* renderers, not `--json`.**
The two literal tuples are `bin/sd-status:3248-3250` and
`bin/sd_work.py:417-418`, both `for key in (...)` loops guarded by `.get()`, so
a projected key they do not name is dropped without a word. Neither `--json`
path reaches them: `bin/sd_work.py:402-404` returns from `_emit_contributions`
before its tuple, and `bin/sd-status:3343-3344` serialises the whole result
object while the tuple lives in `_render_contributions`, reached only via
`render()` at `bin/sd-status:3206`. A criterion written against `--json`
therefore passes before and after any change and verifies nothing — which is
why criterion 7 names the default output instead. The live witness is
`blocking_labels`: allowed at `sd_db/contributions.py:31`, projected at
`sd_db/contributions.py:599`, named in neither tuple, and missing from both
text reports today. Extending the two lists fixes today's bug and leaves
tomorrow's in place, so the test asserts the *set of keys* the text report
renders. Decided 2026-09-12; this is the one place this item chooses to do
slightly more than asked, and the reason is that the failure is silent.

**D5 — the new state is called `draft`, not `unfiled`.** "Unfiled" already
denotes a contribution with no `pull_url`, and the validator carrying that
meaning demands a clone and a branch — which an issue draft does not have. Two
states behind one word inside the same function is how the source issue came to
propose a rule that contradicts an existing one without noticing. Decided
2026-09-12. Reversed if the unfiled-branch state is itself renamed, at which
point one word can be freed and reassigned deliberately.

**D6 — sd:602 lands before this item's field work.** Four new fields against
three disagreeing lists is four chances to ship data nothing displays. sd:602
removes the tax once; paying it here costs more and leaves it in place for the
next field. If sd:602 slips, this item still ships — but then it owes the
field-set assertion itself, and its pull request says plainly that it paid the
tax rather than removed it. Decided 2026-09-12.

**D7 — this item is not split, and here is the test that would change that.**
It spans two repositories, nine dependency enumerations, three field lists and
a data-model widening, which is a legitimate case for splitting. It is kept
whole because the parts are not independently useful: an `issue_url` that no
collector observes produces a row that never updates, and an issue observer
with no `issue_url` has nothing to observe. The split that *is* real is the one
already made — sd:602 out, as a prerequisite that stands on its own. If the
library half grows a second natural seam in implementation — most likely
between "the row can hold an issue" and "the collector watches it" — split
there, because those two do have independent value: the first alone already
gives sd:244 a home that survives, which is the reason this item exists.
Decided 2026-09-12.

**D8 — the system-side work needs its own item in the system repository.** The
majority of the code lands there and this pack's `docs/work` is described by
`docs/work/README.md` as "the entire tracked footprint of the
sd-ai-command-pack workflow". Writing system's plan here would put it where
system's own tooling does not read it. This item covers the pack's half in
full and specifies the library's half as an interface contract; the system item
is to be created by the operator, not by this lane, which must not write into a
shared checkout.

**D9 — a filed issue does NOT share the `github:` key prefix, and this is a
precondition rather than a detail.** Extending the key form is the obvious move
and reusing the prefix is the obvious way to do it. It breaks the projection in
two places at once, both silently:

- `_projection_row` at `sd_db/contributions.py:569-571` chooses its observation
  by `next((s for s in sources if s["key"].startswith("github:")), sources[0])`
  — the *first* source whose key starts with `github:` becomes the one and only
  observation. An issue checkpoint sharing the prefix can be selected as a
  registered row's pull-request observation.
- That observation is then read as pull-request-shaped. The lane at
  `sd_db/contributions.py:580` is
  `"merged" if observation.get("state") == "merged" else "awaiting_them"`, so
  an issue arrives in the projection as a pull request that never merges.
- The unregistered-checkpoint sweep at `sd_db/contributions.py:622` scans
  `key LIKE 'contribution:github:%'` and hands each hit to `_projection_row` at
  `sd_db/contributions.py:627`; the slice `key[7:]` at
  `sd_db/contributions.py:625` hard-codes the seven characters of `github:`.

None of that raises. It produces a malformed row that reads as a real one.
Issues therefore take their own prefix, and the sweep and the source-selection
predicate are both taught to discriminate — which is checkable, unlike the
alternative. Decided 2026-09-12. Reversed only if `_projection_row` is first
rewritten to take its observation shape as an argument rather than sniffing it
from a key prefix, which would be the better fix and is not in this item.

Note for the same reason that a **draft** needs no key change at all: an
unfiled contribution already lives entirely under `item:<id>`, because
`sd_db/contributions.py:615-618` appends the second source only when
`pull_url` is set. Only the *filed* issue reaches `_key`.

**D10 — a closed issue gets a new terminal lane, `closed`, sorted last;
`awaiting_them` is refused.** The lane assignment at
`sd_db/contributions.py:580` is
`lane = "awaiting_you" if needs_you else "merged" if observation.get("state") == "merged" else "awaiting_them"`,
so `awaiting_them` is already the fallback for everything that is not merged.
Choosing it would therefore be choosing the current behaviour, and a criterion
written against it would pass with zero code change — while the defect
requirement 10 names survives intact: `LANES` at `sd_db/contributions.py:32` is
`{"newly_unblocked": 0, "awaiting_you": 1, "awaiting_them": 2, "merged": 3}`, so
a terminal closed issue would sort at index 2, permanently among live
awaiting-them work and permanently ahead of merged pull requests. Every reader
inherits that order from the sort at `sd_db/contributions.py:630`.

The decision is therefore a fourth lane: `closed`, at an index at or after
every non-terminal lane. Adding it — rather than renaming `merged` to something
neutral — keeps `merged` meaning exactly what it means today for pull requests,
so no existing row moves and no existing reader's expectations change. The
operator-facing reason string moves with it: `sd_db/contributions.py:367` reads
`"Closed without merge"`, which is the same pull-request vocabulary one layer
down, and the issue path states the close reason instead.

Whether `closed` sorts equal to `merged` or after it is left to implementation;
what is *not* left open is that it must not sort before a non-terminal lane, and
that the sort stays total — `LANES` is a total map and the projection sorts on
it directly, so a lane added to one and not the other is a `KeyError` at read
time, not a silent misordering. Decided 2026-09-12. Reversed if lanes ever
become per-contribution-kind rather than one shared vocabulary, at which point
the terminal lane for an issue is named by its own kind and this decision is
moot.

## Risks

**Accepted: the three-step landing can be left half-done.** If the library
change lands and the pin never moves, the pack keeps working and the new fields
are simply never shown — a silent no-op rather than a failure. `implement.md`
makes the pin bump its own step with its own verification for this reason, but
nothing enforces that the third step ever happens. The mitigating fact is that
criterion 7's field-set test fails until the readers are updated.

**Accepted: the issue timeline is a different GraphQL query, and the cost is not
yet measured.** The existing query at `sd_db/contribution_github.py:25-37` is
rooted at `repository.pullRequest(number:)` and selects six pull-request
timeline types. Issues need `repository.issue(number:)` and a different node
set. The request budget for a pull is `PULL_REQUESTS = 8` at
`sd_db/contribution_sync.py:26`; whether an issue costs fewer is a measurement
the implementation must take, not a number this design may assert. Until it is
taken, issues should be priced at the pull-request rate, which is safe in the
direction that matters — over-reserving budget delays a refresh, under-reserving
truncates a collect.

**Accepted: `draft_path` points outside the database and can rot.** A draft
moved or deleted makes the digest unverifiable. The evidence mechanism already
has this property and treats it as a refusal on read, which is the right
behaviour: a draft whose body cannot be produced is not ready to file.

**Not mitigated, and named: this design was written without running the
library's own test suite.** The library lives in a shared checkout this lane is
forbidden to write to, and `sd_db` is not importable in this worktree — the 21
collection errors above are that fact. Every claim here about the library is a
claim about what the source says, verified by reading the cited lines. None is
a claim about behaviour observed running.
