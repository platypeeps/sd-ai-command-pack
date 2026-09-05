---
title: design — the bracketed branch parses or refuses, and nothing in between
status: planning
created: 2026-09-04
---

# Design — refuse what cannot be parsed

## The decision

`host_name` stops repairing its input. The bracketed branch accepts exactly
`[addr]` and `[addr]:digits`; every other shape is returned as it arrived,
lowercased and stripped but otherwise unparsed. No allow-list contains an
unparsed header, so `host_ok` refuses it and `tailnet_host` records what
actually came in.

```python
address, bracket, port = name.partition("]")
return address + bracket if bracket and (
    not port or (port[0] == ":" and port[1:].isdigit())) else name
```

Three lines where there was one — **+2 code**, measured, not counted by eye —
plus the paragraph saying why a boundary that used to accept these now refuses
them, which is where the other 16 of the +18 go.

## What the PRD undercounted

The PRD says *"Two headers that are not the IPv6 loopback are accepted as the
IPv6 loopback."* That is not an undercount by six. It is a category error, and
the first draft of this document repeated it one size up by answering "eight" --
which was the number of rows in the corpus below, not the number of headers
admitted.

The admitted set is unbounded. `partition("]")` keeps everything before the
first `]` and discards everything after it, so **every** header of the form
`[::1]<anything>` is admitted as the IPv6 loopback, as is `[::1` followed by
anything containing no `]`. Measured by generating them rather than by listing
them:

```
random '[::1]' + junk tails admitted: 2000/2000
samples: ['[::1]NR5x-/', '[::1]CZJ', '[::1]r.hA', '[::1]c', ...]
```

The table below is a set of representatives chosen to separate the candidate
fixes, not an enumeration of the defect. Counting its rows is the mistake this
paragraph exists to stop happening a third time.

| `Host` header | `host_name()` today | `host_ok()` today | after |
|---|---|---|---|
| `[::1]:8767` | `[::1]` | `True` | `True` — the canonical case |
| `[::1]` | `[::1]` | `True` | `True` — canonical, no port |
| `[::1` | `[::1]` | **`True`** | `False` — bracket invented |
| `[::1]evil.com` | `[::1]` | **`True`** | `False` — tail discarded |
| `[::1]]` | `[::1]` | **`True`** | `False` |
| `[::1]/` | `[::1]` | **`True`** | `False` — a path in the authority |
| `[::1]8767` | `[::1]` | **`True`** | `False` — no colon at all |
| `[::1]:8767:9` | `[::1]` | **`True`** | `False` — two ports |
| `[::1]:0x1f` | `[::1]` | **`True`** | `False` — port is not a number |
| `[::1]:` | `[::1]` | **`True`** | `False` — empty port, see below |
| `[evil.com` | `[evil.com]` | `False` | `False` — refused by accident, now on purpose |
| `[]`, `[` | `[]` | `False` | `False` |

The PRD's severity assessment survives this, which is worth being explicit
about, because "unbounded" reads like an escalation and is not one. A browser
builds the `Host` from the URL authority, and `[::1]anything` is not an
authority a browser will construct — true of the whole family, not just of the
rows the PRD named. Reaching any of it still needs a client that sets the header
directly. The finding is still "a security boundary does not do what its
docstring says", not "the boundary is bypassed today". What changed is the shape
of the defect, not its reachability.

## Open question 1 — digits, not a colon

The PRD asks whether the port should be validated as digits or only as "starts
with a colon", noting the colon check is shorter. Measured, the colon check is
not equivalent:

```
colon-only  admits '[::1]:'+junk : 2000 /2000
digits rule admits '[::1]:'+junk : 57 /2000
digits rule admits '[::1]:'+digits: 2000 /2000
```

The colon check does not shrink the defect. It relocates it: `[::1]<anything>`
becomes `[::1]:<anything>`, still unbounded, still every tail accepted. It fixes
`[::1` and `[::1]evil.com` — the two the PRD named — and nothing structural,
which is exactly what writing a fix against the examples in a report produces.

The digits rule admits 57 of the same 2000 random tails, and all 57 are `:`
followed only by digits — that is, they are ports. It accepts all 2000 numeric
ports tried. So it is not merely stricter by three rows; it is the difference
between an unbounded admitted family and a bounded one. Digits it is.

**The collateral.** `[::1]:` — a bracketed address with an empty port — is legal
under RFC 3986, whose `port` production is `*DIGIT` and so matches the empty
string. The digits rule refuses it. This is a deliberate narrowing: no browser
emits it, `curl` does not produce it, and a guard whose job is to refuse what it
cannot vouch for is the wrong place to honour a degenerate case of the grammar.
Recorded here rather than discovered later, because "we accidentally became
non-compliant with the URI grammar" and "we deliberately did" read identically
in the code.

## Open question 2 — `host_name` is the only parser

Enumerated rather than assumed, per the blast-radius rule. Three call sites,
all in `dashboard/server.py`:

| Site | Caller | What a wrong answer costs |
|---|---|---|
| `server.py:425` | `host_ok` in the read guard | a request served to an origin it should not be |
| `server.py:506` | `host_ok` in the write guard | the same, on a mutation |
| `server.py:568` | `tailnet_host=` on the mutation record | a mutation filed under the wrong origin |

`grep` over `*.py` and `bin/` for `host_name`, `host_ok`, `allowed_hosts`,
`LOOPBACK` and `Host` finds no fourth. `dashboard/actions.py` matches the sweep
but on an unrelated `Host`-free use; the three sites above are the whole set.
This is the property `host_name` was extracted to create, and it holds: fixing
the parser fixes every consumer at once, and no consumer carries its own copy.

## Open question 3 — the sibling item stays separate

The citation-gate item shares a discovery date with this one and nothing else.
It touches `tests/`, not `dashboard/`; it is not under a cap; and it turned out
to be the larger of the two once its premise was measured. Folding it in would
put an unrelated change under this item's cap re-derivation, which is the
specific thing R11-D24 split the cap to prevent. Separate.

## Open question 4 — the unbracketed path widens nothing

The PRD asks for this to be stated either way rather than assumed. Measured:

- `localhost:evil` yields `localhost`. Malformed port, but the host part is the
  host that was asked for, so the origin comparison is answered correctly.
- `localhost:80:80` has two colons, falls past the `count(":") == 1` branch, and
  is returned whole — matching no allow-list entry, so refused.

Either the string has exactly one colon, in which case what precedes it is the
host, or it does not, in which case nothing is stripped. There is no shape where
the unbracketed branch invents a name. It is left alone, and a comment says so,
because "we checked and it is fine" is invisible in a diff that changes nothing.

## The two-change split

`dashboard/` measures **4,348 against a 4,350 cap** — two lines. The patch above
measures **+18 total, +2 code**, landing at 4,366 and 2,271. The code half fits
(`DASHBOARD_CODE_CAP` is 2,300, 31 spare); the total half does not.

`test_loc_caps.py` is explicit that *"a cap is never raised in the PR that busts
it"* and that each re-derivation lands *"in its own decision record by a change
that fit under the ceiling it replaced"*. So:

**Change 1 — R11-D30, the cap.** Touches `tests/test_loc_caps.py` only, so
`dashboard/` stays at 4,348 and the change fits under the 4,350 it replaces.
Itemised:

| | lines |
|---|---|
| `dashboard/` on `main` today | 4,348 |
| this item's fix, measured against the patched tree | +18 |
| required | 4,366 |
| margin for this item's own review rounds | +9 |
| **`DASHBOARD_CAP`** | **4,375** |

Being honest about the order this was derived in: 4,375 was chosen first as a
round number and the 9-line margin is what fell out, not a margin computed from
anything and then added. What justifies keeping it is the predecessor item's
`implement.md`, which records that its cap *"was re-derived from the branch each
time rather than once"* because *"each round of review moved the number"* — four
shipped rows for one item. Nine lines is a bet that this item's review rounds
cost less than that, made explicit so that a fifth round busting it is a visible
event rather than a quiet overrun.

`DASHBOARD_CODE_CAP` is untouched. It is downward-only under R11-D24 and the
fix fits beneath it.

**Change 2 — the fix.** Rebased on change 1. `dashboard/server.py` and the
tests.

## Tests

Per acceptance criterion 2, the bar is mutation-tested, not covered. The
assertion must fail against the current implementation, which is easy to
arrange here — the current implementation is the mutation.

1. Every row of the table above, as a parametrised case over `host_name` and
   `host_ok` together. The pair matters: criterion 3 is precisely that the two
   callers must not disagree, so asserting only `host_ok` would leave
   `tailnet_host` unpinned.
2. `host_name` returns something falsy-but-not-`""` — specifically the header
   itself — for a malformed input. `""` is in `LOOPBACK_NAMES`, so a mutation
   returning `""` on the refusal path would file a malformed header as local
   while still passing every `host_ok` assertion.
3. Mutations to kill, each applied to `dashboard/server.py` and required to fail:
   - `port[1:].isdigit()` → `port[:1] == ":"` (the colon-only variant; must fail
     on `[::1]:8767:9`)
   - `else name` → `else address + bracket` (the repair, restored)
   - `else name` → `else ""` (the `LOOPBACK_NAMES` trap in criterion 3)
   - `not port or ...` → `port is not None or ...` (accepts every port shape)

## Criterion 3, precisely

The PRD asks that `host_name` return "the header unmodified". It returns
`name` — the header stripped and lowercased — not the original bytes. The
deviation is deliberate and is recorded because "unmodified" is what the
criterion says: `strip().lower()` happens before any parsing decision and
applies to the accepted path identically, so keeping it means the refused and
accepted paths normalise the same way. What the criterion is actually
protecting against is the *repair* — the invented bracket and the discarded
tail — and against `""`, which would land in `LOOPBACK_NAMES`. Both hold.

## Rollback

One function and no schema. Reverting change 2 restores the
previous behaviour exactly. Change 1 is a constant in a test file and can stand
alone: a `DASHBOARD_CAP` of 4,375 over a directory measuring 4,348 is loose, not
broken, and the next change under `dashboard/` re-derives it either way.

It is not, however, free of persisted consequence, and the first draft of this
section said "no persisted state", which was wrong. `tailnet_host` is written
into the mutation ledger, so this changes what future rows record for a
malformed header: today `[::1]`, afterwards the header as it arrived. Rows
already written keep the old value and are not migrated — there is no
back-fill, because a row saying `[::1]` for a header that was not `[::1]` is
still an accurate record of what the server believed at the time, and rewriting
history to match a later parser would be the more misleading of the two. Worth
knowing before reading old rows, not worth a migration.

The operational risk of change 2 is the reverse of a bypass — it is refusing a
`Host` that used to work. The refused set is enumerated in the table and
contains no header a browser can produce, so the exposure is a non-browser
client (a reverse proxy rewriting `Host`) that was relying on a shape the guard
should never have accepted. That is the intended change, but it is the thing to
look at first if the dashboard starts 403-ing after this lands.

## Concern ledger

Per `.claude/rules/sd-planning-adversarial-review.md`. One lane — mine — held to
the standard two would have met, because nothing else is going to catch what it
misses. Two rounds ran. Nothing blocks implementation.

- **C-1 — the `+18` was measured against text that no artifact contained.
  `addressed`.** The cap re-derivation's whole justification is a measurement of
  a specific patch, and that patch existed only in a shell heredoc. Any
  paraphrase at implementation time would have silently invalidated R11-D30.
  `implement.md` now pins the exact replacement body and says why; re-measured
  against the pinned text, still +18 / +2.

- **C-2 — "eight" was the size of my corpus, not the size of the defect.
  `addressed`.** The PRD said two; the first draft of this document said eight
  and treated that as the correction. Both are category errors: `partition("]")`
  discards everything after the first `]`, so the admitted family is unbounded.
  Measured by generating rather than listing — 2000 of 2000 random `[::1]` tails
  admitted. This is the session's recurring failure in a new costume: a claim
  built from what I had already written down rather than from the input space.

- **C-3 — the case for digits was argued three rows wide. `addressed`.** The
  first draft said the colon check "leaves three of the eight repaired". Measured,
  the colon check leaves an *unbounded* family repaired too — it relocates
  `[::1]<anything>` to `[::1]:<anything>` and bounds nothing. The real argument
  is a change of kind, not of degree, and it now reads that way. Had C-2 not been
  caught, this one would have stood, because it was downstream of the same
  miscounting.

- **C-4 — the cap margin was presented as derived and was back-derived.
  `addressed`.** 4,375 was picked as a round number and "+9 margin" is what fell
  out of the subtraction. Stated in that order now, with the predecessor item's
  four-rounds-of-cap-movement as the reason to keep it rather than as a
  retrospective justification for it.

- **C-5 — criterion 3 says "unmodified"; the fix returns `strip().lower()`.
  `addressed`.** A real deviation from the PRD's wording, now recorded with the
  argument for it: normalisation happens before any parsing decision and applies
  identically to the accepted path, so the two paths cannot normalise
  differently. What the criterion protects — no repair, and never `""` — holds.

- **C-6 — "no persisted state" in the rollback section was false. `addressed`.**
  `tailnet_host` is written into the mutation ledger, so this changes what future
  rows record for a malformed header. No back-fill, with the reasoning stated.

- **C-7 — the named verification would have verified nothing. `addressed`.**
  `implement.md` originally said to run the test files directly.
  `tests/test_sd_dashboard.py` is the only one of the five in this area without a
  `unittest.main()` guard: run directly it executes nothing and exits 0. Verified
  — zero lines of output, exit 0, on a clean tree. Step 1 is now `make check`.
  A verification step that cannot fail is the same defect as C-18 was, one layer
  further out.

- **C-8 — stale cross-reference introduced by round 1's own fix. `addressed`.**
  Inserting the `make check` step renumbered the mutation step from 2 to 3, and
  the criteria table went on citing "verification step 2". Found by round 2,
  which is the round that exists to find what round 1 broke.

- **C-9 — is `host_name` really the only `Host` parser? `rebutted` — the
  concern was that the sweep was too narrow.** Re-run over `*.py`, `bin/` and
  `sd-*`: three call sites, all in `dashboard/server.py` (425, 506, 568).
  `dashboard/actions.py` matched only a prose mention of "the Host guard" at
  line 22. No fourth parser exists.

- **C-10 — does the fix break the existing suites? `addressed` by execution.**
  Not left as an assertion: the patch was applied to `dashboard/server.py` and
  `tests/test_dashboard_actions.py` and `tests/test_sd_ledger.py` both ran green,
  then the file was restored and `git status` confirmed clean. Every currently
  accepted header is canonical and survives the digits rule.

**Not raised as concerns, recorded so the next round does not re-derive them.**
`port[0]` cannot raise, because `not port or ...` short-circuits. A zone-id
header like `[fe80::1%25eth0]:8767` parses to `[fe80::1%25eth0]` and is then
refused by the allow-list, unchanged from today. `test_one_parser_serves_both_callers`
asserts `.split(":")[0]` appears zero times in `server.py`; the patch does not
reintroduce it.

### Round 2 addendum — a fifth silencer, found by tripping over it

R11-D30's comment added 19 lines to `tests/test_loc_caps.py`, which moved four
symbols the *predecessor* item's `prd.md` cites. CI caught two of them. The
other two were equally wrong and passed, which is worth writing down because the
sibling item (`2026-09-04-the-citation-gate-skips-what-it-cannot-match`) is
about exactly this and its PRD names four silencers, not five.

The gate builds `lines[start-1-WINDOW : end+WINDOW]` and asks whether the anchor
*string appears anywhere in that window*. It does not ask whether the symbol is
**defined** there. So:

- `code_line_count` cited at 117-160, actually at 135-178. The cited span is 44
  lines wide, so the window still contains the real `def`. Passes, wrong.
- `DASHBOARD_CODE_CAP` cited at 91, actually at 109. It passed because the
  R11-D30 comment written in this very change mentions `DASHBOARD_CODE_CAP`
  within two lines of 91 — the citation was validated by the prose that broke
  it.

A wide span or a nearby mention satisfies a citation to a definition. All four
were re-anchored from the AST, not from the two CI named, per the blast-radius
rule; verified by re-deriving every citation into that file and finding zero
disagreements. Recorded here rather than in the sibling item's PRD because
this branch should not edit that item — but it is the sibling's finding, and it
should be moved there when that item starts.
