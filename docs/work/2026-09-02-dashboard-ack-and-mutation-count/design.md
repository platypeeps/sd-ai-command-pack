# Design — the dashboard's three open gaps

The PRD's five open questions are answered here. Four of the five turned out to
be answerable from constraints the codebase had already written down and not
yet applied to this problem; the fifth (open question 4) is a number, and a
number is chosen rather than derived.

## Approach

**One append-only ledger serves all three gaps.** The PRD costs the item as two
mechanisms sharing 94 lines of code, with gap 3 sent to `bin/` if it does not
fit. The three gaps ask for different facts but the same *shape*: append one
JSON object per event to a file under the state root, with an exclusive lock,
and read it back with `wc -l` and `jq`. `record_load`
(`bin/sd-handoff-restore:157`) is that shape already — an exclusive `flock` over
`O_APPEND` against concurrent writers and torn records, and a `load_age_seconds`
that survives an unparseable timestamp. Its **59 code lines** are the PRD's own
yardstick, re-measured today with the same tokeniser: `record_load` 48 plus
`load_age_seconds` 11.

So the item ships one writer, not three, and three record kinds through it:

| kind | written by | answers |
|---|---|---|
| `mutation` | `do_POST`, after the guards, before the response | R11-D10's count |
| `ack` | the ack endpoint | requirement 3 |
| `bind` | `serve`, once per start | "no demand" vs "no path" |

The third row is the one that makes this a design rather than a convenience.
The PRD's acceptance list requires that *"the command that answers R11-D10 can
distinguish no demand from no tailnet path"* — and nothing in gaps 1 and 2
produces that fact. It is gap 3's byproduct. Recording bind outcomes in the same
ledger, on the same clock, is what lets one `jq` expression say "eleven mutating
requests over sixty days, during which the tailnet bind was achieved on 58 of 60
starts" instead of two numbers from two places that have to be trusted to line
up. Gap 3 stops being a coupled risk to gap 2's counter and becomes its
denominator.

**Rejected: the SQLite index.** R11-D10's criterion says *"the index shows fewer
than ten mutating requests"*, so the index is the literal reading. It is the
wrong home, and `dashboard/store.py:1-22` is where the repository says so in its
own words: *"observability only, rebuildable, never an input"*, `rm
index.sqlite` *"loses time, never a fact"*, and *"Nothing reads this database to
decide anything — no gate, no lint rule, no merge check."* A deletion criterion
reading a number out of it is exactly a gate, and mutation events are
rebuildable from nothing — no tracker holds them, so a cache eviction would
silently reset the count toward the zero that deletes the write path. Putting
them there would violate both halves of the doctrine at once, and would do it in
the one file that states the doctrine.

The PRD anticipates this and grants the correction: *"the criterion's wording is
this repo's to correct if the other shape is better."* R11-D10's wording is
corrected, and D-1 below records that as a decision rather than a slip.

**Rejected: a general parameter mechanism.** R11-D25 rejected ~100 lines of
parameter validator, and the ack does not need it. An ack id is not an argument
to a command — it never reaches `actions.run`, never reaches an argv, and is
written to a store as an opaque string. A separate `POST /api/ack` beside
`/api/run`, behind the same three guards, keeps R11-D25's load-bearing property
(*"nothing a caller sends is interpolated"*) true by construction rather than by
validation, because the ack path has no interpolation site to protect.

## Decisions

**D-1 — the mutation record is an append-only file under the state root, not a
row in the SQLite index. R11-D10's wording is corrected to match.** Decided
2026-09-03 in this design, on the evidence of `dashboard/store.py:1-22` quoted
above. Path: `~/.local/state/sd-ai-command-pack/dashboard/ledger.jsonl`, the
state root (`bin/sd-handoff:162`) rather than the cache root, because the state
root is where this repository already puts facts that cannot be regenerated.
Reversed by: the index gaining a durable, non-rebuildable partition with its own
doctrine, at which point this is one table and a smaller diff.

*Amended 2026-09-03 at implement time, C-22.* The **file** is where this
decision said. The **module** is not: it is `bin/sd_ledger.py`, not
`dashboard/ledger.py`, because the measured cost put `dashboard/` over its total
cap (see The budget). `dashboard/` never imports it — `serve` and `make_handler`
take `record=` and `acked=` callables defaulting to a no-op sink, and
`bin/sd-dashboard` passes the real ones down the dependency edge that already
runs that way. Nothing about the path, the format, or D-6's three states
changes; what changes is which cap pays, and that a second entry point wanting
records must pass them in rather than import them.

**D-2 — an ack is permanent, keyed by the R11-D20 id, and recurrence is the id's
problem rather than the ack's.** Decided 2026-09-03. This is not a new rule;
`dashboard/now.py:16-19` already decided it and the ack store only has to not
break it: *"a repo that gains a commit is a new fact, and an ack of '2 unpushed'
should not silently cover '9 unpushed' tomorrow."* The backbone ids honour that
— `ahead:{name}:{ahead}`, `dirty:{name}:{dirty}`, `worktrees:{count}`
(`dashboard/now.py:59,71,161`) all key on the changing count, so a recurrence
mints a new id and reappears without the ack store knowing anything about
recurrence.

*Reversed 2026-09-03 at implement time, C-27. An ack holds for the day it was
taken.* The reasoning above is true of a count that **changes** and false of one
that **returns**. `dirty:{name}:{dirty}` keys on the count, so dismissing
`dirty:repo:1` and then having the repo go clean and pick up a different single
dirty file mints the *identical* id — and the permanent ack hides it, silently,
for as long as the ledger lives. The branch review found it; the sentence
"a recurrence mints a new id" is what it disproved, not the id scheme.

The day bound closes the whole class without the ledger having to know which ids
are count-keyed and which are not, which is the property that makes it cheap:
`acked` compares the record's own `at` against today and returns nothing older.
An ack with no stamp is not honoured, rather than honoured forever. D-3 survives
unchanged and is still worth having — a PR going quiet inside one day should
still resurface, and the rank band is what makes it.

**D-3 — `pr:{repo}#{number}` gains the rank band, making the one non-fact-keyed
id fact-keyed like the rest.** Decided 2026-09-03. `dashboard/now.py:129` is the
exception to D-2: a PR id encodes identity but not condition, so an ack taken
while the row was `FRESH` (rank 4) would permanently hide the same PR when it
goes `STALE` (rank 2) — a state change the view exists to raise. The
alternative, leaving it permanent on the grounds that dismissing a PR reminder
is a deliberate "I know", was rejected because it makes the ack semantics
depend on which row you clicked, which is the kind of rule nobody can hold. Cost
is one f-string; net zero lines.

**D-4 — `bound_addrs` re-probes a bounded number of times, then continues on
loopback and says so, loudly and durably.** Decided 2026-09-03, answering open
questions 4 and 5. The number is **3 probes, 2 seconds apart**, chosen not
derived: the failure being defended against is a boot-order race with
`tailscaled` that resolves in seconds, and the three ways `tailnet_addrs`
returns empty (`dashboard/server.py:89`) all return *immediately* — `tailscale`
absent from `PATH` raises `OSError`, a non-zero exit and an unparseable line
both return without waiting — so in every failing case this design expects, the
whole cost is the **4 seconds of deliberate delay**, not the probe.

The worst case is not bounded that way and the risk section says so: `tailscale`
present but hanging costs the existing 10-second timeout three times over. That
is 34 seconds, which exceeds `ThrottleInterval` (`bin/sd-dashboard:80`), so the
retry budget is deliberately *not* justified by fitting inside launchd's window
— there is no startup deadline for it to miss, and claiming one would be a
tidier argument than the facts support. Placed in `bound_addrs`
(`dashboard/server.py:129`), which charges `dashboard/`.

Of open question 5's four shapes, three are rejected:

- *`serve` exits non-zero and lets `KeepAlive` retry* — rejected. On a machine
  deliberately without Tailscale it is a permanent 30-second crashloop, and
  requirement 6's allowance for "report and continue" exists precisely so that a
  Tailscale-less machine is not broken by this fix.
- *the plist waits on a network condition before `RunAtLoad`* — rejected. It
  fixes the boot race and nothing else; the other two causes `tailnet_addrs`
  collapses into an empty list (`tailscale` absent from `PATH`, output that does
  not parse) are unaffected, and it is untestable by fixture.
- *restore a `tailscale serve` proxy* — rejected. It re-introduces the component
  `platypeeps/system#190` deleted, which the PRD requires be argued rather than
  assumed; nothing here argues for it.

The cache in `_ADDRS` keeps its stated reason — one answer feeds both the
allow-list and the bind — and gains the cost the docstring never wrote down: it
is latched *after the retries*, not on the first empty answer. Open question 7's
mid-run address change is **not** fixed by this and is recorded as an accepted
risk below rather than silently inherited.

**D-5 — every start writes one `bind` record whether it succeeded or not.**
Decided 2026-09-03. This is what makes D-1's counter interpretable and it is the
non-obvious half of the whole item: `{"kind":"bind","requested":3,"bound":1}`
turns "zero mutating requests" from an unreadable number into either evidence
about demand or evidence about reachability. Without it, gap 2 ships a counter
whose zero means two different things, which is the PRD's C-8.

**D-6 — a ledger write can only ever cost a row, and the criterion is written so
that a lost row cannot be read as evidence.** Decided 2026-09-03, closing the
PRD's requirement 2 and the tension it hides.

Requirement 2 says the record is *"a byproduct of serving, never a
precondition"* — a failed write degrades to a missing row, never to a refused or
500'd request. That is straightforward on its own: the append is wrapped, every
exception is swallowed, and it happens after `actions.run` has produced its
status so there is no path where it can change one.

What is not straightforward is that this puts requirement 2 in direct conflict
with requirement 1. A ledger nobody can write produces zero rows, and zero rows
is the exact reading that deletes the write path. The failure mode this whole
item exists to fix — *a mechanism that fails by producing nothing, inside a
system that reads nothing as a number* — would be reintroduced by the very
mechanism fixing it, one level down.

The resolution is D-5's `bind` record, which is why it is a decision and not a
detail. Every start writes one, so at evaluation time the three states are
distinguishable and the criterion command must treat them differently:

| ledger state | reading |
|---|---|
| absent or unreadable | **no evidence** — criterion not evaluated |
| present, `bind` rows, no `mutation` rows | genuine zero demand |
| present, no rows at all | **no evidence** — a server that ran would have written `bind` |

A criterion that maps the first and third rows to "fewer than ten" is wrong, and
writing it that way is how this repeats a third time.

**D-7 — the ledger is a new mechanism, so standing rule 1 attaches to it here
rather than to a later item.** Decided 2026-09-03, closing requirement 5.

*Linked incident:* R11-D10's criterion arriving without a counter, which is this
item's gap 2, and R10-D3's identical shape a week earlier
(`bin/sd-handoff-restore:157`). Two instances of one failure is the evidence.

*Deletion criterion, evaluable by command:* the `mutation` and `bind` kinds
exist to answer R11-D10 and have no other reader. On the date R11-D10 is
evaluated and its answer recorded, both writers and their record kinds are
deleted unless a second question has been written down that needs them —
`grep -rn 'ledger\.jsonl' docs/ skills/ bin/ dashboard/` returning a citation
outside this item's own directory is what "written down" means, and an empty
result deletes them. The `ack` kind is not covered by this: it is live state
serving the R11-D20 contract, and its lifetime is that contract's.

This is the requirement the PRD wrote for itself — *"the counter that makes the
criterion evaluable ships with the mechanism rather than after it"* — applied to
the counter's own mechanism.

## The budget

The binding constraint is 94 code lines under `dashboard/`, re-derived today
with the repository's own tokeniser rather than quoted from the PRD:

```
dashboard/ code 2206 / 2300  headroom 94
dashboard/ total 4190 / 4300  headroom 110
```

Estimated spend, to be replaced with measured numbers at implement time:

| Item | Est. code lines | Charges |
|---|---|---|
| `ledger.append` + path helper (locked, `O_APPEND`) | 30 | `dashboard/` |
| `mutation` record site in `do_POST` | 6 | `dashboard/` |
| `bind` record site in `serve` | 5 | `dashboard/` |
| `bound_addrs` bounded re-probe | 8 | `dashboard/` |
| `POST /api/ack` handler + ack read in `now` | 22 | `dashboard/` |
| dismiss control in `app.js` | 20 | `dashboard/` |
| **Total** | **~91** | against **94** |

Three lines of margin is not a plan, so the deletion candidate is named now
rather than found later: `dashboard/plugins.py` is 719 lines and holds the
`registry`/`dark`/`refused` alert construction (`:678-713`), which predates the
plugin split and is the largest single block in `dashboard/` whose behaviour is
covered by fixtures. **If the measured spend exceeds 94, the item's first move
is to cut there, not to trim the mechanisms.** Raising `DASHBOARD_CODE_CAP` is
not available (`tests/test_loc_caps.py:20,66` — the cap that "may only move downward").

`bin/` was to be unspent by this design. Its headroom is **1,783 lines
(12,217 / 14,000)** — `bin/` grew by 1,070 lines between 2026-09-02 and today,
so the PRD's original 2,853 was stale. Open question 5 was posed against that
figure, so it was corrected in the PRD's measured-state table and in both places
its prose repeated it, rather than only here.

### What the measurement said — amended 2026-09-03, C-22

Both loads above are wrong, and they are kept rather than rewritten because the
shape of the error is the useful part. `implement.md`'s Budget carries the
measured table; the two corrections that belong to *this* file are:

1. **The binding constraint was not 94 code lines.** It was 110 total lines.
   The first module written landed at 64 code lines against a 30-line estimate,
   which left the code cap 15 lines of room and put the total cap **53 over**.
   A budget stated only in code lines cannot answer the question the caps
   actually ask, in a repository that counts its own prose.
2. **The named cut was not available.** `plugins.py:678-713` is `alert_rows`.
   It is what turns a plugin failure into a Now row, and it carries per-complaint
   ids so that dismissing one cannot hide its siblings — the property D-2 and D-3
   depend on. Cutting it to buy room for a mutation counter would have made
   plugin losses silent, which is requirement 1's failure class. It was chosen
   for being fixture-covered; coverage measures what a deletion would *break
   loudly*, not what a deletion would *cost*.

What was done instead is D-1's amendment: the module moved to `bin/`, spending
199 of `bin/`'s 1,783 lines and leaving `dashboard/` at **4,348** total and
**2,269 / 2,300** code once both rounds of the branch review's remediation are
counted. Against
4,300 that is red, which is why `DASHBOARD_CAP` was re-derived at 4,350 in
R11-D29 — a separate change, touching nothing under `dashboard/`, because
`tests/test_loc_caps.py`'s own rule is that a cap moves in its own record by a
change that fits under the ceiling it replaces. This branch is rebased on it and
measures 4,348 / 4,350, with two lines to spare.

## Evaluating R11-D10

The criterion becomes a command, per the PRD's acceptance list and the R10-D3
precedent:

```bash
L=~/.local/state/sd-ai-command-pack/dashboard/ledger.jsonl
SINCE=$(date -u -v-60d +%Y-%m-%d)   # the window R11-D10 actually asks about

# A damaged line must not take the run with it. `jq -c . "$L" 2>/dev/null`
# looks like it does this and does not: jq aborts at the parse error, so every
# record *after* a damaged line silently disappears and the count comes back
# low. Reading raw lines and dropping the ones that will not parse is the form
# that actually skips. Checked against a ledger with a torn line in the middle:
# the first form returned 1 of 3 records, this one returns 3.
records() { jq -Rc 'fromjson? // empty' "$L"; }

# D-6's three states, in the order that matters: "no evidence" is checked
# first, because every reading below returns 0 on an absent file and 0 is the
# answer that deletes the write path.
[ -r "$L" ] || { echo "no evidence: no ledger"; exit 2; }
[ -n "$(records | head -1)" ] || { echo "no evidence: nothing parses"; exit 2; }

# The denominator has to cover the window, not merely exist. One `bind` row
# from ninety days ago proves the writer worked once, which is not the claim
# being made -- the claim is that a zero over sixty days means nobody used it.
starts=$(records | jq -r --arg s "$SINCE" \
  'select(.kind=="bind" and .at >= $s) | .at' | wc -l)   # `.at`, not the object:
                                       # `jq -r` pretty-prints a bare object
                                       # over several lines and `wc -l` then
                                       # counts those, not records
[ "$starts" -gt 0 ] || { echo "no evidence: no start inside the window"; exit 2; }

# mutating requests from a tailnet Host, inside the window
records | jq -r --arg s "$SINCE" \
  'select(.kind=="mutation" and .tailnet_host==true and .at >= $s) | .at' | wc -l
# how often the bind that was asked for was achieved, and whether the probe
# ever found a tailnet address at all
records | jq -r --arg s "$SINCE" \
  'select(.kind=="bind" and .at >= $s) | "\(.requested) \(.bound) \(.tailnet)"' \
  | sort | uniq -c
```

Four things about that command are review findings or its own test, rather
than first drafts.
It compares `.at` as a string, which works because every stamp is ISO-8601 with
a fixed-width date and the comparison only ever needs the day. It counts starts
**inside the window** rather than ever, because a criterion that reads "nobody
used it in sixty days" is not supported by a writer that last proved itself
three months ago. It routes every read through `records`, because `jq`
aborting on one malformed line would have printed a low count and let the caller
read it as no demand. And it counts a field rather than a record, which is the
one the command's own dry run caught: the first version counted seven starts in
a ledger holding one, because `jq -r` pretty-printed the selected object and
`wc -l` counted its lines.

Run against a fixture before being written down, in all three of D-6's states:
a ledger with only an out-of-window start exits 2, a ledger that parses to
nothing exits 2, and a ledger with an in-window start and a torn line reports
one tailnet mutation against `3 1 0` — asked for three addresses, bound one,
found no tailnet.

The two guards are the command, not preamble around it. A version of this that
opens with the `jq` count is the same defect as the criterion it replaces:
`jq` on a missing file writes to stderr and `wc -l` prints `0`, so the criterion
would read "fewer than ten" off a file that was never created and delete the
write path on the strength of it. Exit 2 is "not evaluated", which is a third
answer and not a failure.

Sixty days run **from the counter, not from the item** — the resolution Sven
gave for R10-D3 and which the PRD proposes inheriting explicitly rather than
quietly. So R11-D10's evaluation date moves from 2026-10-31 to sixty days after
the ledger lands, and **this design is where that move is recorded**. If the
item does not land before 2026-10-31, the criterion is evaluated on that date
with a documented "no evidence" and the write path survives on that basis; it is
not evaluated against a zero.

## Risks

**Accepted: a tailnet address that changes while the server runs is still not
picked up.** Open question 7 asks for "picked up or reported" and this design
delivers neither for the mid-run case — `_ADDRS` is still latched for the life
of the process, just latched later and more honestly. The PRD's own evidence
shows the address changing across starts (`100.82.165.108` → `100.73.1.43`), not
within one. Fixing it means either re-probing per request, which puts a
subprocess in front of a page load, or a background thread, which is a new
mechanism attracting standing rule 1. Both cost more than 94 lines allows, and
`KeepAlive` restarts the process often enough that the window is bounded. **This
is a knowing partial answer to requirement 7, not a claim to have met it.**

**Accepted: the budget is an estimate.** Every line count in the table above is
predicted, and the closest precedent overshot its own first estimate. The
mitigation is the named deletion candidate, not confidence.

**Accepted: `tailnet_addrs` keeps a 10-second timeout, so three probes can add
up to 34 seconds to a start.** The failure modes that matter return
immediately — `tailscale` absent from `PATH` raises `OSError`, a non-zero exit
returns at once — so the slow path requires `tailscale` to be present *and*
hanging, which no observed start has done.

**Not mitigated, stated: the ack store is the first durable fact the dashboard
owns.** Everything else the dashboard writes is a cache and can be deleted and
rebuilt; `store.py:1-22` says so in as many words. `ledger.jsonl` cannot be —
an ack is user intent and a mutation record is evidence for a deletion
criterion — so the dashboard acquires a backup obligation it did not have.
D-1's amendment moved the *writer* to `bin/`, which does not soften this: the
obligation follows the file, and the file is under the state root either way.
What the move does change is that the backup obligation is now visibly attached
to the state root rather than to a directory whose own doctrine says it holds
nothing worth backing up. Named here because the storage doctrine deserves to
be told when something changes character.

## Corrections to the PRD

- The PRD quotes `dashboard/now.py:15` as *"identifies one alert and not one
  row"*. The file says **"not one source"**. The argument the PRD builds on it is
  unaffected; the quotation is wrong and is corrected here rather than in place,
  so the PRD's converged review record stays intact.
- `bin/` headroom was restated from 2,853 to **1,783** in the PRD's measured-state
  table and in the two places its prose repeated the old figure (requirement 8 and
  the measured-state note). See The budget.

## Planning adversarial review — 2026-09-03

Host lane only; this repository defines no additional lane, and the pack ships
none (`.claude/sd-ai-command-pack/planning-adversarial-review.md`, §2). Trigger:
`design.md` is new — `prd.md` existed at `d50b14f1…`, `design.md` and
`implement.md` were absent. Concern ids continue the PRD's ledger, which ended
at C-10.

- **C-11 — D-4 justified its retry budget with a bound it does not have.
  Blocking. `addressed`.** The first draft argued 3 probes fit inside
  `ThrottleInterval`'s 30 seconds while the same document's risk section stated a
  34-second worst case. Both cannot be true. Evidence: `tailnet_addrs`
  (`dashboard/server.py:89`) keeps a 10-second timeout per probe. Owning
  artifact: this file, D-4, which now rests the choice on the failing cases
  returning immediately and states plainly that the worst case exceeds the
  throttle window and is not bounded by it.
- **C-12 — the `bin/` headroom was stale, and correcting it invalidated the
  citation of it. Material. `addressed`.** The PRD's 2,853 was measured
  2026-09-02; `bin/` is 12,217/14,000 today, so 1,783. It appeared three times in
  `prd.md` and open question 5 was posed against it. Fixed in all three, then
  this file's "not the 2,853 the PRD states" became false and was rewritten —
  the second half of the trap the contract names. Verified by `grep` returning
  only historical mentions.
- **C-13 — the 59-line yardstick was inherited rather than measured.
  Material. `addressed`.** The whole budget is calibrated against it. Re-measured
  with `test_loc_caps.code_line_count`: `record_load` 48 + `load_age_seconds` 11
  = **59**, matching exactly.
- **C-14 — "hardened over eight review rounds" was repeated from the PRD and is
  not verifiable from the tree. Minor. `addressed` by removal.** Replaced with
  the two properties that are readable in the code: an exclusive `flock` over
  `O_APPEND`, and a timestamp parse that survives garbage.
- **C-15 — requirement 2 was not addressed at all, and hides a conflict with
  requirement 1. Blocking. `addressed`.** A ledger nobody can write produces zero
  rows, and zero is what deletes the write path — the item's own failure mode,
  reintroduced by its own fix. Owning artifact: this file, D-6, which resolves it
  through D-5's `bind` record and states which ledger states are "no evidence"
  rather than zero.
- **C-16 — requirement 5 was not applied to the mechanism this item adds.
  Blocking. `addressed`.** The design gave R11-D10 a counter while giving the
  counter no incident and no deletion criterion, which is the requirement the PRD
  wrote against exactly this move. Owning artifact: this file, D-7.
- **C-17 — the PRD misquotes `dashboard/now.py:15`. Minor. `addressed`.** It
  reads "not one row"; the file says "not one **source**". The argument built on
  it is unaffected. Recorded in Corrections rather than edited into the PRD's
  converged text.
- **C-18 — `sd-review --scope planning` never asks a provider. `rebutted`
  2026-09-04, by the concern's own author.** The premise is false and the
  conclusion with it.

  The routing half was right: `docs_skip` is `["docs/**", "*.md"]`, `never_skip`
  is `["docs/spec/**"]`, and every work item does route to tier `skip`. The
  concern then treated the tier as the whole answer. It is not.
  `plan_providers` prepends the providers a *scope* names ahead of the tier
  chain, and says so in its own docstring — *"a challenge run is an extra stance,
  not a substitute for the review"*. This repository sets
  `"planning_providers": ["codex"]` in `.github/sd-review.json`. Executed against
  the live policy:

  ```
  work item PRD -> tier=skip   tier chain=()
     scope=worktree  challenge=False -> ()
     scope=planning  challenge=False -> ('codex',)
  ```

  `skip` means the tier contributes nothing. The scope contributes codex anyway.
  The lane asks a provider, the name `--scope planning` describes what it does,
  and there is no decision for anyone to make. The owner field is cleared and the
  parking trigger withdrawn.

  **Why it was wrong is the useful part.** The concern read the router, found the
  tier, and stopped one function short of the thing that consumes the tier. It
  was written during a review round whose whole subject was claims made about
  behaviour nobody executed — C-22, C-25, C-30 and C-33 in this same file — and
  it is that error again, committed while cataloguing it. Nothing in the
  repository disagreed with it, because nothing pins the interaction between a
  `skip` tier and a scope's provider list; a test asserting that
  `scope=planning` yields a non-empty chain at tier `skip` would have refuted
  this in the round it was written. That test now exists:
  `ScopeProvidersOverASkipTier` (`tests/test_sd_review.py:589-705`), seven
  tests, killed against four mutations of `plan_providers` — the planning
  branch deleted, its provider list emptied, the scope appended instead of
  prepended, and the scope replacing the chain rather than adding to it.

  Writing it found one more thing worth recording. The ordering assertion first
  went through the live policy, where the `deep` tier begins with codex and
  `planning_providers` is also codex — so prepend and append produce the same
  chain, and the mutation that swapped them survived. A test that cannot fail is
  the same defect as a concern that was never run, one layer up. The assertion
  now substitutes a provider taken from the tier's own chain. Not one absent
  from it -- an earlier draft of this sentence, and of the test's docstring,
  claimed disjoint names and was wrong on its own fixture, where the
  substituted name sits second in the `deep` chain. What the name has to be
  is not *first*, since first is the one position where prepending and
  appending agree.
- **C-19 — cross-artifact sweep. `addressed`.** Two artifacts now, so the sweep
  is real rather than internal. Every figure appearing in both was enumerated by
  `grep` rather than by reading in sequence: 94 and 110 (agree, re-derived from
  the tokeniser today), 59 (agree, re-measured), 2026-10-31 (agrees), 719
  (agrees), and 2,853 (disagreed — C-12). Every citation this file makes *out* of
  itself was opened: `store.py:1-22`, `now.py:15-19,59,71,129,161`,
  `server.py:89,122`, `sd-dashboard:69`, `sd-handoff:162`,
  `test_loc_caps.py:20,66`, `plugins.py:678-713`.

Implementation is **unblocked**: no blocking concern is unresolved, the five
open questions the PRD posed are answered in D-1 through D-5, and requirements 2
and 5 are closed by D-6 and D-7. `implement.md` is the next artifact and does not
exist yet.

## Log

- 2026-09-03 `design.md` written. Open questions 1, 2, 3 and 5 answered from
  constraints already in the tree — `store.py`'s storage doctrine, `now.py`'s
  id-is-the-fact rule, `record_load`'s shape — and open question 4 answered with
  a chosen number and its reasoning.
- 2026-09-03 host adversarial review run. C-11, C-15 and C-16 were blocking and
  changed this file; C-12 changed both artifacts; C-13 and C-14 tightened claims
  to what was measured; C-18 parked with a named trigger (and rebutted on
  2026-09-04 — the premise did not survive being run).

## Planning adversarial review, second round — 2026-09-03

Trigger: C-11, C-15 and C-16 were blocking and changed `design.md`, so the
contract's §4 rerun applies. C-11 through C-19 stand. One new concern; the
cross-artifact sweep was rerun over the figures D-6 and D-7 introduced.

- **C-20 — the criterion command did not implement D-6. Blocking. `addressed`.**
  D-6 had just decided that an absent or start-less ledger reads as "no
  evidence", and the command three sections below it opened with a bare `jq |
  wc -l`, which prints `0` for a missing file. The decision and its
  implementation contradicted each other inside one document, and the
  implementation was the one that would have been copied. This is C-15's defect
  reproduced one level further down — the reason it was caught is that the
  contract asks the second round to expect defects introduced by the first
  round's own fixes. Owning artifact: this file, Evaluating R11-D10, which now
  guards on readability and on at least one `bind` row before it counts
  anything, and exits 2 for "not evaluated".
- **C-21 — cross-artifact sweep, second pass. `addressed`.** D-6 and D-7
  introduced no new measured figures, so nothing new could drift; the sweep
  reduces to confirming that D-6's three states, the table in D-6, and the
  command in Evaluating R11-D10 now agree, and that D-7's `grep` names the same
  path D-1 chose (`ledger.jsonl`). Both confirmed by reading the three passages
  together rather than in sequence.

Implementation remains **unblocked**. Two remediation rounds have run of the
three the contract permits.

## Planning adversarial review, third round — 2026-09-03

Trigger: implementation amended D-1 and the budget, which the contract counts as
a material update to a reviewed artifact. This is the third and last automatic
round §4 permits. C-11 through C-21 stand.

- **C-22 — the design asserted a fact about the implementation that the
  implementation falsified. Blocking. `addressed`.** *"`bin/` is not spent by
  this design"* was true when written and false when built; so was D-1's
  implied module location. Left alone, the next reader would have budgeted the
  next dashboard item against a `bin/` figure that is 131 lines stale and looked
  for the ledger in a directory that does not contain it. Both passages are
  amended above, with the estimate kept beside the measurement rather than
  overwritten by it. Owning artifacts: this file (D-1, The budget) and
  `implement.md` (step 1, Budget).
- **C-23 — the fallback was never checked before it was named. Blocking.
  `addressed`.** The design named `plugins.py:678-713` as the cut of first
  resort without opening it. It is `alert_rows`, live code whose deletion
  produces exactly the silence requirement 1 exists to end. Nothing was cut, so
  no harm landed; what is recorded is the reasoning error, in The budget above,
  because "it is covered by fixtures" reads like a deletability argument and is
  not one. The standing form: a named fallback is read before it is named, or it
  is not a fallback.
- **C-24 — cross-artifact sweep, third pass. `addressed`.** Enumerated by grep
  rather than by reading in sequence, since C-22 is the exact shape of a
  corrected figure leaving a citation behind. It found two live drifts the
  amendment above had not touched, both now fixed: the PRD asserted `bin/`'s
  **1,783** free lines in the present tense in two places outside its dated
  measured-state row (`prd.md:99,189`, now date-qualified and carrying the 1,584
  the item leaves), and this file's Risks said the ack store makes `dashboard/`
  the owner of a durable fact, which the move to `bin/` falsified in its
  particulars while leaving the risk itself intact. `grep -rn 'ledger\.py'`
  returns three hits, all of them naming `dashboard/ledger.py` as the location
  that was abandoned rather than the one in use; the three
  anchored code citations in this file and `implement.md`
  (`bound_addrs`, `do_POST` and `serve`, at `dashboard/server.py:129,498,621`)
  are the post-edit lines, and are anchored to their symbols so they are
  enforced by
  `tests/test_doc_citations.py`; and D-7's `grep -rn 'ledger\.jsonl'` still
  names the path D-1 chose, which the move did not change.

- **C-25 — the measured numbers were themselves stale. Blocking. `addressed`.**
  Found by the C-24 sweep's own re-run rather than by reading: the figures C-22
  had just installed as "measured" (4,266 total, 2,235 code) were taken after
  step 5, and step 6 had since added the dismiss control. The true final state
  was **4,294 / 4,300** — six lines, not thirty-four, and 4,348 / 4,350 once the
  branch review's remediation landed. This is C-22 committed a
  second time inside the fix for C-22, which is the failure the contract's
  third round exists to catch: a correction is a new claim and inherits none of
  the original's verification. The standing form: re-run the tokeniser after the
  last commit, never after the last one you remember. Owning artifacts: this
  file (The budget), `implement.md` (Budget), `prd.md` (the two `bin/` figures).
- **C-26 — the cap raise. `addressed`, by R11-D29.** Six lines of `dashboard/`
  headroom meant the next paragraph written under that directory was a red
  check — and the branch review's own remediation then needed 42 of them.
  `DASHBOARD_CAP` may be re-derived, unlike the code cap, and this item
  deliberately did not do it: `tests/test_loc_caps.py`'s rule is that a cap
  moves in its own record, by a change that fits under the ceiling it replaces.
  It moved to 4,350 in R11-D29, itemised, in a change touching nothing under
  `dashboard/`, merged immediately before this branch, which is rebased on it.

Implementation **unblocked**; C-26 is a scheduling decision, not a blocker on
this change. Three of three automatic rounds have run; a fourth would need the
contract's escalation, and no concern is open against the code that ships here.

## Planning adversarial review, fourth round — 2026-09-03

Not automatic. §4 permits three, and three ran. This round exists because the
branch review lane (`sd-review --scope branch --challenge`, codex and prism)
returned a finding against a **design decision** rather than against code, which
is the contract's escalation case: a planning artifact cannot be left asserting
something the implementation has disproved.

- **C-27 — D-2's justification was false for a returning count. Blocking.
  `addressed`.** Recorded above, in D-2. What makes it worth a round of its own
  rather than a line in a fix commit is where the error was: not in the code
  implementing D-2, which did exactly what D-2 said, but in D-2's one-sentence
  argument for why permanence was safe. Three planning rounds read that sentence
  and none of them tested it against a count that returns to a previous value.
  The lane that caught it was reading the *code*, which is the only reason the
  case came up concretely. Owning artifact: this file, D-2.
- **C-28 — the named fallback, again, differently. `addressed`.** The branch
  review also found that the mutation record counted refused and failed actions,
  that `[::1]:8767` was classified as tailnet demand by a `split(":")` the file
  already had a correct parser for two hundred lines up, that a total bind
  failure exited before recording anything, and that an empty tailnet probe
  reported a clean start. All four are D-6 and requirement 6 defects — the
  ledger telling the operator something false rather than nothing — and all four
  are fixed. They are recorded here rather than only in the commit because C-23
  said the design's fallback was never checked before it was named, and this is
  the same shape: four claims about behaviour that the design asserted and
  nobody exercised until a reviewer did.
- **C-29 — a fix that made things worse, caught by its own test. `addressed`.**
  The first remediation of the lock replaced a blocking `flock` with three
  non-blocking tries a tenth of a second apart, and its own concurrency test
  dropped eight of forty records. That trades a stall the dashboard has never
  had for a wrong count, which is the single thing the ledger exists to produce.
  Now a two-second budget in fiftieths. Recorded because the review finding was
  legitimate and the first answer to it was worse than the defect.

Implementation **unblocked**. C-26 (the cap) is in flight as its own change, per
`tests/test_loc_caps.py`'s rule that a cap moves in its own record.

## Planning adversarial review, fifth round — 2026-09-03

The branch review, run again after the fourth round's fixes, returned
twenty-eight findings. The contract's rounds are exhausted; this is the record
of what a *code* lane found in artifacts that three planning rounds had passed,
which is the useful part.

- **C-30 — `append` could raise, and D-6 says it cannot. Blocking. `addressed`.**
  Four statements sat above the `try`, `json.dumps` among them. A field JSON
  cannot encode raised `TypeError` into `do_POST` between `actions.run` and
  `send_body`, turning a mutation that had already happened into a 500 — the
  exact failure requirement 2 forbids, produced by the code written to satisfy
  it. Confirmed by calling `append(..., x=object())` before the fix. The whole
  body is inside the guard now, and `tests/test_sd_ledger.py` pins it.
- **C-31 — the ack answered 200 to a write that never landed. Blocking.
  `addressed`.** `record` returned nothing, so `/api/ack` could not tell a
  stored ack from a dropped one, and the page removes the row on the strength
  of that answer. A mutation row is telemetry and may be dropped; an ack is a
  command. `append` now returns whether the record landed, the ack path 503s
  when it did not, and the default sink returns True so a server with no ledger
  does not 503 its own button.
- **C-32 — the day boundary was UTC's, not the operator's. Blocking.
  `addressed`.** D-2's replacement expired an ack at the end of "today"
  measured in UTC. On this machine, in America/Denver, that is 18:00 local: an
  alert dismissed after dinner reappears before bed. Confirmed against the
  clock — at 23:36 local the UTC date was already tomorrow. `at` is stamped in
  local time with its offset, which stays an unambiguous instant while making
  `at[:10]` the operator's day.
- **C-33 — the criterion command did not evaluate the criterion. Blocking.
  `addressed`.** Three defects in one block, all in Evaluating R11-D10. It
  counted every mutation ever rather than the sixty days R11-D10 asks about; it
  accepted any `bind` row as proof the writer worked, including one from ninety
  days ago; and its damage guard did not guard. This is C-20 and C-15 for the
  third time — the command that implements a decision drifting from the
  decision — and the reason it keeps happening is that the command was written
  and never run. It has now been run against fixtures in all three of D-6's
  states, which is how the last two defects were found rather than reasoned
  about: `jq -c .` aborts at a torn line instead of skipping it, returning 1 of
  3 records, and `jq -r 'select(...)'` pretty-prints an object so `wc -l`
  counted seven starts in a ledger holding one.
- **C-34 — two findings refuted, recorded so they are not re-litigated.**
  *"Tests require banded IDs without a production change"* — false;
  `dashboard/now.py:135` carries the band, and the test passes against it.
  *"Non-loopback hosts are incorrectly counted as tailnet demand"* — false;
  `host_ok` has already narrowed `Host` to `allowed_hosts()`, which is
  `LOOPBACK | tailnet_names() | bound addresses`, so a host reaching the record
  is loopback or tailnet and nothing else. The dependency is real and worth
  naming: if `allowed_hosts` ever widens, this classification widens with it.

### Round 6 — the pull request's own review (C-35, C-36)

- **C-35 — `host_name` repairs a malformed `Host` instead of refusing it.
  Real, pre-existing, deferred with a named reason. `parked`.**

  `name.partition("]")[0] + "]"` invents a closing bracket when the header has
  none, so `Host: [::1` is normalised to `[::1]` and admitted, and
  `Host: [::1]evil.com` has its tail discarded and is likewise admitted.
  Confirmed by running it: `host_ok('[::1')` and `host_ok('[::1]evil.com')`
  both return `True`. A boundary that repairs its input is not a boundary.

  Two things bound the severity and one bounds the fix. It is **not introduced
  here**: `git show origin/main:dashboard/server.py` carries the identical
  expression inside `host_ok`, and this item only moved it into a helper so two
  callers could share one parser. It is **not reachable from the documented
  threat model** either: `host_ok`'s docstring names DNS rebinding, and a page
  on the open internet cannot set a `Host` header — reaching this needs a client
  that sets it directly, which is a different and much smaller adversary.

  The fix does not fit. The narrowest correct form is `+1` line of code, but a
  security boundary that now deliberately refuses input it used to repair needs
  the sentence saying so, and `dashboard/` stands at 4,348 against 4,350. Paying
  for it by deleting rationale elsewhere is the exact failure R11-D24 split the
  cap to prevent. So it goes where the doctrine sends it: its own item, opening
  with its own re-derivation, which is what the R11-D29 record says the next
  change under `dashboard/` must do. This is that change, arriving on schedule.

- **C-36 — a test class name read as a bad plural. Non-blocking. `addressed`.**

  `TheCriterionsThreeStates` was a possessive without the apostrophe a class
  name cannot carry. Review proposed `Criteria`, which is wrong in the other
  direction — D-6 has one criterion with three states, not three criteria — so
  it is `TheCriterionHasThreeStates` instead. Recorded because the observation
  was right even though the correction was not.

**On the count.** Thirty findings against work that had passed three
planning rounds and one code round is not a defence of the process — it is the
measurement of it. The pattern across C-22, C-25, C-30 and C-33 is one thing:
every claim this item made that nobody executed turned out to be false, and
every claim that was executed held. The planning rounds read; the code round
ran.
