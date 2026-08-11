# Design — split the planning contract so the Codex lane ships only where Codex is asked for

## D0 — What the detector actually reports

Measured 2026-08-11 by running the shipped classifier over the shipped
template, rather than reading the rule:

```
FIRES line 42: `command -v codex` and `codex exec --help`. When both succeed, launch one
  (quiet 43): review-only `codex exec` command in a separate background Bash task before
  (quiet 54): TTY, so `codex exec` treats it as piped input, prints `Reading additional input
  (quiet 64): A foreground `codex exec` succeeds under the same configuration, so a working
  (quiet 74): This lane uses the installed `codex` CLI directly. Do not inspect, install,
```

**One line of 129 fires.** It fires because it begins with an inline code
span, which `codex_in_command_position` counts as command position — the
rule R15-C2 added so that "`codex exec` is prohibited here." at the start
of a line would not be missed. Four other mentions of the same
instruction, mid-sentence, are silent.

Two things follow, and they pull in opposite directions:

- The verdict is **wrap-dependent**. Reflowing line 42 would clear the
  scan while changing nothing about what the document instructs. That is
  the option this task must not take by accident, and the PRD already
  names it as "the option most likely to be chosen for the wrong reason".
- The verdict is nonetheless **correct about the file**. A surviving
  pack-shipped document really does tell an agent to run `codex exec` in
  a repository that never declared `codex`. The detector under-reports;
  it does not over-report.

So the fix has to remove the usage from repositories that did not declare
the tool, not remove the detector's ability to see it.

## D1 — Decision: split the document, ship the lane conditionally

This is the PRD's **option 5**, added during design. The original four
were enumerated before the measurement D1's fact 3 rests on, so all four
of them are rejections (D2), and the PRD's acceptance criterion was
corrected from "three rejected" to four.

`templates/.claude/sd-ai-command-pack/planning-adversarial-review.md`
becomes two files:

| File | Platform row | Reaches |
|---|---|---|
| `.claude/sd-ai-command-pack/planning-adversarial-review.md` | `claude` | every consumer, as today |
| `.codex/sd-ai-command-pack/planning-adversarial-review-codex.md` | `codex` | repositories that declare `codex` — plus any install passing `--all` or `--platform codex`, per the `--all` case below |

**The appendix lands under `.codex/`, not beside the host contract, and
that is load-bearing rather than tidy.** The first draft put it in
`.claude/sd-ai-command-pack/`, which the adversarial review refuted:
that path matches the unconditional `consumer-config` override
(`partition-surfaces.py:115`), and `expected_residual_targets` adds a
`consumer-config` row to the expected residual **without checking the
consumer's platforms** — `row.platform in consumer_platforms or
row.category == "consumer-config"` (`installer/conversion.py:307`). An
appendix that is never installed never enters the receipt, so expected
and residual would disagree and `stale_receipt_reason` would refuse the
conversion (`install.py:959-961`). That trades the codex `packDefect` for a
receipt-drift blocker — the same conversion, still refused.

Under `.codex/` there is no override, so `platform_category("codex")`
returns `repo-native` (`partition-surfaces.py:143`), which *is* platform
checked. The two sides then agree in both directions: an undeclared
consumer has the row in neither expected nor residual; a declaring
consumer has it in both.

Worth recording that the refuted comment's premise is already false —
it says consumer-config rows "carry platform `shared`", but two of the
six carry `claude`. That never mattered because all eight consumers
declare `claude`. A `codex` row is the first one for which it would.

Measured, not estimated: the document is 129 lines, the Codex lane
occupies lines **41–89** (49 lines) inside section 2 "Parallel review
lanes", and the remaining **80 lines** are the host-side contract every
consumer actually executes.

**The lane is not a clean excision, and the plan must not pretend it
is.** Six references to it sit outside 41–89, and none of them would be
caught by the D0 probe, because they name Codex without invoking it:

| Line | What it says | Why it matters |
|---|---|---|
| 20 | `## 2. Parallel review lanes` | the **section heading**, promising several lanes above a section that would describe one |
| 26 | "accepting **either** review lane at face value" | presupposes two |
| 93 | "Merge and deduplicate **both lanes** into one concern ledger" | describes two lanes where a non-codex consumer has one |
| 112 | "one fresh Codex review against ... only if it was available in the initial round" | a procedural step for a lane that may not exist |
| 118 | "the two lanes remain in material conflict" | a stop condition that can never trigger |
| 127 | "Codex status as completed, skipped, or failed" | a **final-report requirement** for a lane the consumer cannot run |

Six, not four. The first draft of this table listed 93, 112, 118, and 127
— everything a `grep` for `codex` returns, plus the two lines that happen
to say "lanes" near them. Lines 20 and 26 were missed because they name
the concept without naming the tool, and the round-2 host review caught
them by widening the pattern to `codex|lane`. `implement.md` step 2b
therefore carries the enumerating command rather than this table, on the
principle that a recited list drifts and a `grep` does not.

Line 127 is still the sharpest: without reconciliation, a consumer with
no appendix is told to report the status of a lane it has no way to
attempt. All six become conditional on the appendix being present, which
is section 2's own existing vocabulary — the contract already handles a
skipped lane; it just does not yet handle an absent one.

This needs **no new machinery**. Three measured facts make the platform
row sufficient on its own:

1. `codex` is already a registered platform
   (`installer/registry.py:123`, a full `PlatformInfo` with `.codex`),
   though the pack ships **zero** `codex` rows today. This would be the
   first.
2. `selected_files` skips an `if-anchor-exists` row whose platform is not
   selected (`installer/fileops.py:184`), and with no `--platform` filter
   it additionally requires `has_active_trellis_platform`
   (`fileops.py:193`).
3. `ACTIVE_TRELLIS_PLATFORM_MARKERS` has **no `codex` entry**, so
   `has_active_trellis_platform(target, "codex")` iterates an empty tuple
   and returns `False` (`fileops.py:158-160`).

Fact 3 is the load-bearing one, and it is what makes this safe rather
than merely plausible. Every one of the three canaries has a **populated**
`.codex/` directory while declaring only
`["claude", "gemini", "github", "opencode"]` (child 3's requirement 3).
An anchor-only gate would therefore install the appendix into all of
them and put the marker straight back. It does not, because the anchor is
not the last word: absent an explicit `--platform`, the row also needs an
active-Trellis marker that does not exist for `codex`.

### Why the marker then reaches zero

The scan's codex loop is guarded by `if "codex" not in declared`
(`sd-ai-command-pack-thin-resweep.py:894`), and it skips any path in
`removed`. After the split:

- **A consumer that does not declare `codex`** does not receive the
  appendix through any normal install, so no surviving file invokes the
  CLI. The host contract that does survive contains no invocation — it
  is the appendix that carries every line quoted in D0.
- **A consumer that declares `codex`** receives the appendix, but the
  guard short-circuits before the walk. Declared usage is not undeclared
  usage.

**`--all` is a third case, and the first draft's "never receives it" was
wrong.** `selected_files` selects a row under `install_all` *before*
consulting either the platform filter or the active-Trellis marker
(`installer/fileops.py:187`), and `--all` is a documented override
(`docs/SD_AI_COMMAND_PACK.md:163`). A consumer installed with `--all`
gets the appendix, keeps it through conversion, and reports the
`packDefect` again.

This is not patched around. `--all` means "install everything regardless
of what this repository looks like", and a resweep that then reports
undeclared usage is the gate working. What changes is the claim: the
split removes the marker from every consumer that installs normally, not
from every consumer under every invocation. The eight are measured on
their actual receipts, and if any was installed with `--all` it shows up
in acceptance run 6 -- the fleet `packDefects` sweep -- rather
than being assumed away.

## D2 — Why the other options lose

Recorded because the PRD requires it, and because two of them are
reasonable enough that "we picked the other one" is not an answer.

**Option 1, declare `codex` for the eight.** Rejected on measured
grounds, not preference. `PLATFORM_RETAIN_VENDORED_FOR` carries
`"shared": ("codex", "pi")` (`partition-surfaces.py:170-172`) and is
keyed on the shared platform, so declaring `codex` retains the whole
shared machine slice. Quoting child 3's measured figures in full rather
than summarizing them: the plan moves from **166 delete / 13 retire / 27
keep** to **91 delete / 13 retire / 102 keep** — 75 additional retained
targets, being 49 `.agents/**`, 25 `scripts/**`, and one document. It
unblocks the conversion by largely undoing it.

Those figures are child 3's, measured **before** this task adds a row, and
they stay as quoted because they are what makes option 1 lose. Once the
appendix exists, a *declaring* consumer also keeps it — `repo-native`
classifies as `keep` (`installer/conversion.py:190`) — so the post-change
tuple on the same canary basis is **91 / 13 / 103**, and the gap from 27
becomes 76. The extra keep is the appendix itself, not more of the shared
slice. 75 remains the number that matters for the rejection: it is the
size of the unwanted `.agents/**` and `scripts/**` retention, which is
option 1's actual cost and is unchanged.

**Option 2, narrow the detector to ignore pack-shipped documentation.**
Rejected because it re-opens a decision three review rounds already
settled, in the direction they rejected. The scanner's own comment
records it: R14 keyed an exemption on receipt membership, R15 on
whole-file ownership, R16 showed neither is the granularity the proof
has, and both *dropped* the hit rather than bucketing it — "so a marker
in the pack's own text left every bucket and the four-bucket claim with
it. Pack-owned markers are now recorded as what they are: the pack
shipping text that names an undeclared tool." Reinstating the exemption
would restore precisely the blind spot those rounds removed.

D0's wrap-dependence is a real defect in that gate, and it is *not* an
argument for this option: making detection consistent would flag more
lines, not fewer. It is filed as a follow-up rather than fixed here,
because this task's job is to stop shipping undeclared usage, and a
sharper detector would only make the same file fire harder.

**Option 3, machine-scope the whole document.** Rejected on a blocker
found by measurement. Reclassifying the row to `machine-claude` would
make it the first such row outside the three shapes that have delivery
routes — every one of today's 79 is `.claude/skills/**`,
`.claude/commands/**`, or `scripts/**`. `family_for_target` matches on
those prefixes and returns `None` otherwise, failing closed by design
(`installer/machinepayload.py:81`). Machine-scoping would therefore need
a new payload family or plugin mapping, changing the delete set and the
payload contract for one document — which requirement 4 says carries its
own review, and which is a large blast radius for a file the split
handles without touching either contract.

**Option 4, reword so no line reads as a command.** Rejected as the
wrong reason dressed as a fix. D0 shows the change needed is a line
break: the same instruction survives on lines 43, 54, 64, and 74 without
firing. Taking it would leave every consumer still carrying an
instruction to run an undeclared tool, with the only difference being
that the gate can no longer see it.

## D3 — The reference between the two files

`.claude/rules/sd-planning-adversarial-review.md` links the host contract
as a repo-relative sibling, which is why `.claude/sd-ai-command-pack/**`
is `consumer-config` in the partition
(`partition-surfaces.py:115`). That link is unchanged: the host contract
keeps its name and its path.

The host contract gains an explicit **"read and follow"** instruction
for the appendix, conditional on its presence — not a mention of it.
The adversarial review caught the difference: the only mandatory
lazy-load edge in this whole surface is the rules file's "read and
follow" link (`templates/.claude/rules/sd-planning-adversarial-review.md:6-7`),
and a sentence that merely *names* a document creates no obligation to
open it. An appendix that is installed but never read is the same
outcome as one that was never shipped, reached more expensively.

Since the appendix now lives under `.codex/`, the reference crosses
directories rather than naming a sibling. That reference must be written
so it does not become a defect in its own right:

- It cannot cite a path the conversion removes. It does not: neither file
  is in the removal set for a consumer that keeps them, and a file that
  was never installed is not in `removed` either — the resweep's
  `blockers`/`packDefects` are citations to *removed* paths, not to
  absent ones.
- It must not itself read as a command. It names a document, not a CLI.
- **It is a dangling link wherever `codex` is undeclared, and no gate
  catches that.** Searched rather than assumed: there is no
  markdown-link checker anywhere in `make check` — no `lychee`,
  `markdownlint`, `remark`, or equivalent in `Makefile`,
  `scripts/sd-ai-command-pack-full-check.sh`, or the workflows, and
  the only link logic in `scripts/sd-ai-command-pack-check.py` is
  `_is_external_symlink` (`:715`),
  which is about symlinks, not references. So nothing will fail, and
  nothing will warn either.

  That makes the surrounding prose the *only* thing distinguishing an
  intentionally-absent appendix from a broken reference. The sentence
  must say the file is not always present, in the same breath as naming
  it. **Not** "present only where `codex` is declared" — that is the
  narrowed claim C-2 already refuted, and shipping it into consumer-facing
  text would be knowingly false guidance for any repository installed
  with `--all` or `--platform codex`. The honest form states the
  condition without enumerating the ways it is met: the file accompanies
  the Codex platform, and is absent where that platform was not
  installed. A bare link plus a later caveat fails
  this: the reader who clicks first sees a defect, and the most likely
  response to an apparent defect in a pack-shipped contract is a bug
  report against the pack.

## D4 — The cost, stated rather than discovered

**This repository loses the appendix from its own `.claude/`.** `make
sync` runs `install.py . --force` with no `--platform` and no `--all`
(`Makefile:38`), so the appendix is skipped here by exactly the rule D1
relies on: the pack's `.codex/` is populated, but `codex` has no
active-Trellis marker.

That is a real loss and requirement 3 says it gets named rather than
absorbed. It is accepted because the source of truth remains readable in
this repository at
`templates/.codex/sd-ai-command-pack/planning-adversarial-review-codex.md`,
which is where every other pack surface is authored and read during pack
work. What is lost is the *installed copy*, in the one repository that
also holds the original.

The alternatives were considered and are worse: an entry in
`ACTIVE_TRELLIS_PLATFORM_MARKERS` for `codex` would have to name files
the eight consumers already have (`.codex/config.toml`,
`.codex/agents/trellis-*.toml`), which would select the platform in all
of them and put the marker back; `ALWAYS_INSTALL` bypasses the platform
filter entirely (`fileops.py:177`) and would do the same.

**Consumers whose developers have the Codex CLI installed *do* lose the
lane.** The first draft claimed none of the eight can run it today
because none declares `codex`. The adversarial review refuted that, and
it is right: the lane is gated by **runtime probes**, not by the
registry — "capability-check the optional native Codex lane with both
`command -v codex` and `codex exec --help`"
(`planning-adversarial-review.md:41`). Nothing consults
`docs/fleet/consumers.json`. Any consumer where the CLI is on PATH runs
the lane today, declaration or not, and this repository is the existence
proof: it declares nothing and the lane ran during this task's planning.

So the loss is real and requirement 3 applies to it. Its size is
unmeasured and unmeasurable from here — whether a given consumer's
developers have the CLI is not a repository-visible fact, which is the
same blind spot child 3's requirement 3 already documents for globally
configured Codex. What can be said precisely:

- the **host** contract is unchanged, so the adversarial review itself
  continues everywhere;
- what is lost is the **second lane** — the operational detail for
  running it, including the `< /dev/null` trap that costs half an hour
  to rediscover;
- recovering it is one recorded decision, not a code change: declare
  `codex` for that consumer, which is child 3's requirement 3 asking the
  question anyway — with option 1's 75-target retention as its price.

The host contract therefore keeps a short conditional pointer saying the
lane exists and that a repository obtains it by declaring the platform,
so the capability is discoverable rather than silently gone. In prose,
never as a command line — see the C-3 disposition below for why the
literal flag cannot appear in this file.

**Operator decision, 2026-08-11: the loss is accepted.** The split
ships. Requirement 3 is satisfied by that recorded acceptance plus the
CHANGELOG naming, not by the loss being small.

**Every consumer gains one new advisory line, and it points the wrong
way.** `install.py:775-779` prints, for each platform whose row was
skipped with an `install not detected` reason while its directory exists:

```
hint: .codex/ exists but no active Trellis codex install was detected;
pass --platform codex or update Trellis if that platform should be
active here
```

All eight have a populated `.codex/`, so all eight will see this on their
next refresh — the pack ships no `codex` row today, which is the only
reason they do not see it already. It is a printed hint, not an error, and
nothing fails.

It still has to be named, and an earlier draft named it wrongly: it said
taking the hint's advice "is exactly option 1", buying the 75-target
retention. Round 2 refuted that. `--platform codex` installs the appendix
for that one run and records no declaration
(`installer/fileops.py:184`), while retention is computed from the fleet
entry (`install.py:919`). Following the hint is *not* option 1.

The hint is misleading in a subtler way than "expensive". It is the
generic message for a detected-but-unselected platform, and it is
accurate about what the flag does — but it invites a one-shot install
that looks like it settled a question it did not settle. The next
ordinary refresh does not reselect the row, so a consumer can follow the
hint, see the appendix appear, and still be undeclared. The recorded
per-consumer decision child 3's requirement 3 asks for is the fleet
declaration, which is the thing that actually costs 75 targets. The
CHANGELOG entry draws that distinction rather than collapsing it.

### D4.1 — The restore path, corrected twice

Round 2 refuted the sentence this design shipped to the operator with the
C-3 decision, and round 3 refuted round 2's replacement. Both corrections
are recorded, because the shape of the mistake is more instructive than
either version: each draft assumed a flag or a config field did the whole
job, and in this installer neither does.

**What the original said.** "The lane comes back with
`install.py <repo> --platform codex`." Wrong three ways:

1. **`--platform` declares nothing.** It filters file selection for one
   invocation (`installer/fileops.py:184`). Nothing about it reaches
   `docs/fleet/consumers.json`.
2. **It does not buy the 75-target retention.** Conversion reads
   retention platforms from the fleet entry —
   `platforms = frozenset(entry.get("platforms") or ())`
   (`install.py:919`). That price belongs to *declaring*, not to the flag.
3. **A converted consumer refuses it.** `if args.platform or args.all:`
   returns "a thin consumer's platform set is owned by its pin;
   --platform and --all do not apply. Revert first if the platform set
   must change" (`install.py:1268-1273`). Children 3-5 convert all eight.

**What round 2's replacement got wrong.** It called the flag a
"non-sticky one-shot" and said the durable restore is "add `codex` to
`consumers.json`". Both halves are false:

- **The one-shot is sticky.** A later unflagged refresh does not drop the
  entry: `preserved_receipt_targets` keeps receipt entries for platforms
  skipped in *this checkout* (`installer/provenance.py:313`), because
  markers and anchors can live on gitignored paths. There is a direct
  regression test —
  `test_install_preserves_receipt_entries_for_undetected_platform`
  (`tests/test_install_audit.py:428`). The appendix and its receipt row
  persist.
- **Declaring alone installs nothing.** Selection still reads only
  command-line platforms, `--all`, or active markers
  (`installer/fileops.py:184`). What closes the gap is the fleet
  workflow: `install_command` appends `--platform <p>` for each declared
  platform, and only for a non-thin consumer
  (`scripts/sd-ai-command-pack-fleet-preflight.py:296-299`). So the
  restore is **declare, then run the flagged refresh preflight emits** —
  two steps, not one.

The accurate table, and the one the CHANGELOG must carry:

| Repository state | How the lane comes back | What it actually costs |
|---|---|---|
| Not yet converted, one repo | `install.py <repo> --platform codex` | nothing at install time — but see the warning below; this is not a free trial |
| Not yet converted, durably | add `codex` to `platforms` in `docs/fleet/consumers.json`, **then** run the refresh preflight emits (it carries `--platform codex`) | D2 option 1's 75 retained targets at conversion |
| Already thin | revert the conversion, then declare and refresh | the conversion, redone |

**The one-shot re-arms the blocker this task removes, and that is the
warning the CHANGELOG owes its reader.** Round 2 checked the wrong gate
here. It verified that `stale_receipt_reason` computes
`source_residual - receipt_residual` (`installer/thin.py:569`) and so
ignores an *extra* receipt entry — true, and tested
(`tests/test_thin_plan.py:513`) — and concluded there was no drift risk.
But receipt drift was never the gate that fires. The **resweep** is: a
surviving appendix in a repository that has not declared `codex` is
exactly the `undeclared codex usage` `packDefect` this whole task exists
to eliminate (`install.py:898`,
`scripts/sd-ai-command-pack-thin-resweep.py:894`). Because the entry
persists, a developer who reaches for the flag once has permanently
blocked that consumer's conversion until they either declare the platform
or remove the file.

So the flag is not a lightweight alternative to declaring. It is a way to
end up in option 1 without having decided on option 1 — which is precisely
the per-consumer decision child 3's requirement 3 requires be written
down.

The restore instruction goes in the CHANGELOG and this design, **not** in
the shipped host contract. Measured against the shipped detector rather
than assumed: a fenced line reading `install.py <repo> --platform codex`
fires it —

```
FIRES 4 'install.py <repo> --platform codex'
```

— so writing the flag into the contract would put the marker back into
the very file the split removes it from. D3's conditional pointer names
the appendix in prose; it does not print a command.

The CHANGELOG is safe for it because consumers never receive that file:
`grep -c CHANGELOG manifest.json` returns `0`, and it matches no machine
payload family.

## D5 — What this task does not change

The seven stale-path surfaces are `08-10-thin-prompt-surface-repoint`,
merged 2026-08-11 as PR #423. This task neither fixes nor breaks them,
and the acceptance measurement below checks that explicitly: the two
counts are disjoint and only both reaching zero unblocks children 3–5.

## Concern ledger — planning adversarial review, 2026-08-11

Two lanes: host review, and the native Codex lane (`codex exec`,
read-only, ~6 min). Merged and deduplicated. Every concern was verified
against the repository before disposition; none was accepted on the
reviewing lane's word.

| ID | Lane | Severity | Disposition |
|---|---|---|---|
| C-1 | Codex | blocking | **Confirmed, design changed.** `consumer-config` is added to the expected residual without a platform check (`conversion.py:307`), so an uninstalled appendix would refuse the conversion on receipt drift. Appendix relocated to `.codex/`, which is platform-checked. |
| C-2 | Codex | blocking | **Confirmed, claim narrowed.** `--all` selects before the platform filter (`fileops.py:187`). The design no longer claims "never receives"; the `--all` case is named and left to the gate. |
| C-3 | Codex | blocking | **Confirmed, D4 rewritten.** The lane is runtime-probe gated (`planning-adversarial-review.md:41`), not registry gated, so consumers with the CLI can run it today and do lose it. Escalated rather than absorbed — see below. |
| C-4 | Codex | blocking | **Partly accepted.** The fleet half genuinely cannot be measured here; that boundary stands. But the criticism that a file-selection fixture cannot catch C-1 is correct, and the verification now runs a real `--check` and conversion refusal probe. |
| C-5 | Codex | high | **Confirmed, D3 changed.** A sentence naming the appendix creates no read obligation; the host contract now carries a conditional "read and follow" edge. |
| H-1 | host | blocking | **Round 1:** four references to the lane outside lines 41–89 (93, 112, 118, 127), none of which fires the detector. Step 2b added. **Round 2:** the enumeration was two short — line 20's section heading and line 26's "either review lane" name the concept without the tool, so a `codex` grep misses them. Step 2b now carries the enumerating `codex|lane` command instead of a list, and acceptance run 5 reads the result. |
| H-2 | host | medium | All eight consumers gain an `install.py` hint offering `--platform codex`, whose cost it does not state. Named in D4 and the CHANGELOG. |
| H-3 | host | low | Line counts were estimated; measured and corrected (49 lane, 80 host). |
| H-4 | host | low | Canary figures dropped the "13 retire" term; quoted in full. |
| H-5 | host | low | The chosen approach is a fifth option; PRD updated, and its "three rejected" criterion corrected to four. |

### Round 2, 2026-08-11 — remediation round under contract §4

Both lanes rerun against the revised artifacts. Every round-2 concern was
verified against the code before disposition; all six were **confirmed**,
which is worth stating plainly rather than softening — the round-1
remediation introduced two of them.

| ID | Lane | Severity | Disposition |
|---|---|---|---|
| C-6 | Codex | blocking | **Confirmed, addressed.** The restore path this design shipped with the C-3 decision — `install.py <repo> --platform codex` — is wrong three ways: `--platform` only filters selection (`fileops.py:184`), retention comes from the fleet entry (`install.py:919`), and a thin consumer refuses the flag outright (`install.py:1268-1273`). D4 now carries a corrected table, and the correction goes back to the operator because it changes the price of an accepted decision. |
| C-7 | Codex | high | **Confirmed, addressed.** The first numbering fix renumbered `implement.md` alone, leaving this design at `5=packDefects` while `implement.md` had `5=host-reads-whole`. Both lists are now 1-8 in identical order. A cross-artifact citation defect introduced *by* the fix for a cross-artifact citation defect. |
| C-8 | Codex | high | **Confirmed, addressed.** D3 requires the availability condition in the same sentence as the link; `implement.md` step 2 asked only for a conditional edge, and run 5 checked only absent-lane obligations. Both now state the same-sentence requirement, so an implementation cannot satisfy `implement.md` while producing the dangling link D3 rejects. |
| C-9 | Codex | medium | **Confirmed, addressed.** C-2's narrowing was applied to D1 but not propagated: `prd.md`'s option 5, `implement.md` step 2b, and the Rollback section each still said the appendix reaches only declaring repositories. All three now name the `--all` case. |
| C-10 | Codex | medium | **Confirmed, addressed.** `prd.md` still called the appendix a "sibling file" after the `.codex/` relocation, its Options heading still read "none yet chosen", and `task.json`'s description still presented four options as an open decision. All three updated. |
| C-11 | Codex | low | **Confirmed, addressed.** Three citations were off: the rules file's "read and follow" is at `:6-7` not `:5`, the receipt-drift refusal is at `install.py:959-961` not `:958`, and `_is_external_symlink` lives in `scripts/sd-ai-command-pack-check.py`, not a bare `check.py`. |

**What round 2 says about round 1.** Four of the six (C-7 through C-10)
are defects the round-1 *remediation* introduced or failed to propagate,
not defects in the original plan. Every one is the same shape: a value or
a claim corrected in one artifact and left standing in another. Contract
§2 warns about exactly this — "the stale copy is the one you did not
think to open" — and the round-1 pass did not run that sweep, which is
why round 2 found six things instead of zero.

Only C-6 is a defect of substance rather than propagation, and it is the
blocking one.

### Round 3, 2026-08-11 — final permitted remediation round (contract §4)

Contract §4 allows two remediation rounds. This is the second, so there
is no automatic round 4. Six concerns, all confirmed against the code;
three of them are defects the round-2 remediation introduced.

| ID | Lane | Severity | Disposition |
|---|---|---|---|
| C-12 | Codex | blocking | **Confirmed, addressed in D4.1.** Round 2's replacement restore path was wrong in both halves. The flag is *not* a non-sticky one-shot — `preserved_receipt_targets` keeps the entry across later unflagged refreshes (`installer/provenance.py:313`), with a regression test at `tests/test_install_audit.py:428`. And declaring alone installs nothing; the fleet workflow is what appends `--platform <p>` for a non-thin consumer (`fleet-preflight.py:296-299`). Worse, round 2 checked the wrong gate: receipt drift was never the risk, the **resweep** is — a persisted appendix in an undeclared repository re-arms the exact `packDefect` this task removes. |
| C-13 | Codex | blocking | **Confirmed, addressed.** The C-8 fix required the shipped sentence to say the appendix is present "only where the platform is declared" — the narrowed claim C-2 already refuted, now headed for *consumer-facing text*. Implementing `implement.md` literally would have shipped false availability guidance. The design's own title carried it too. All five sites rephrased to "absent where the Codex platform was not installed". |
| C-14 | Codex | medium | **Confirmed, addressed.** The C-10 fix used `task.py set-meta description`, which writes `meta.description`; Trellis reads the top-level `description` as canonical (`task_store.py:362`). The old text was still the live one. Moved to the top-level field; `task.py validate` passes. |
| C-15 | Codex | medium | **Confirmed, annotated.** The `166/13/27 → 91/13/102` figures predate this task's own row. A declaring consumer also keeps the appendix (`conversion.py:190`), so the post-change tuple is `91/13/103`. D2 now says so, and says why 75 is still the right number for option 1's rejection. |
| C-16 | Codex | medium | **Confirmed, corrected.** "No markdown-link checker exists" was false — `review-preflight.mjs:233` runs one. The conclusion holds for a different reason: `documentationRoots` (`:253-264`) covers neither `templates/` nor `.claude/`. D3 now states the real reason, because the false version would misdirect anyone trying to add coverage. |
| C-17 | Codex | low | **Confirmed, addressed.** The restore table was cited as D3 in two places and D4 in two others, while physically sitting inside the round-2 ledger. Moved into D4 as **D4.1**; all four citations now point there. |

**The pattern held for three rounds.** Round 2 found four propagation
defects from round 1's remediation; round 3 found three more from round
2's. Each round's fix was correct in the artifact it edited and stale or
contradictory somewhere else, and in C-13's case the fix for one concern
directly restated a claim an earlier concern had refuted.

Rounds are spent. §4 permits no automatic round 4, so convergence is the
operator's call rather than another lane's.

**C-3 was escalated and is now closed by operator decision, 2026-08-11.**
It is a genuine capability loss whose acceptance was not the
implementer's to grant, and it was not visible when the approach was
chosen, so it went back to the operator before implementation started.
The two alternatives were put alongside it with their prices — declare
`codex` fleet-wide (option 1's 75-target retention, which partly defeats
the conversion this task exists to unblock) and narrow the detector
instead (option 2, which weakens the gate and belongs to the resweep's
owner). The decision is **accept the loss**: ship the split and name the loss in
the CHANGELOG. The restore path offered alongside that decision was
stated wrongly and is corrected below; the correction makes the durable
restore a fleet declaration rather than a flag, which is a materially
worse restore story than the operator was shown.


## Verification strategy

Per consumer and per claim, measured with the shipped classifier rather
than reasoned about:

1. The appendix is **not** selected for a repository with a populated
   `.codex/` that does not declare `codex` — the canaries' exact shape.
   This is the claim the whole design rests on, so it is measured on a
   fixture with `.codex/` present, not inferred from `fileops.py:193`.
2. The appendix **is** selected under `--platform codex`.
3. The host contract, alone, produces zero codex hits from the shipped
   classifier — the D0 probe rerun against the split file.
4. The appendix, scanned as a surviving file in an undeclared repository,
   would produce a hit — the negative case proving the split moved the
   marker rather than diluting it.
5. The **host contract reads as a whole** after step 2b — no step, list
   item, or report field requires a lane the reader may not have, and
   the sentence naming the appendix says in that same sentence that the
   file is not always present — phrased as "absent where the Codex
   platform was not installed" rather than "only where `codex` is
   declared", since `--all` and `--platform codex` also install it
   (C-13). Added in round 2
   alongside the six-reference correction above. No probe can close it:
   none of the six firing-free references fires the detector, a `grep`
   for `codex` misses lines 20 and 26 outright, and no gate anywhere
   checks markdown links. It is a read, and the plan says so rather than
   implying a tool covers it.
6. `packDefects` for the codex row reaches zero for all eight consumers.
7. The seven-surface count is unchanged.
8. The conversion is **not refused on receipt drift** for a normally
   installed fixture — `--check` and a gated `--thin` both succeed. This
   is C-1's regression check. It is listed separately from 1 and 2
   because a file-selection probe cannot see it: the appendix's absence
   is correct *selection* and, under the rejected `.claude/` placement,
   incorrect *residual accounting* at the same time. Only
   `expected_residual_targets` against the receipt tells them apart.

Eight, not six. Checks 5 and 8 came out of the round-1 and round-2
reviews, and both cover failures the original six would have passed —
worth recording rather than renumbering silently.

`implement.md` step 7 runs these same eight under these same numbers.
Getting that alignment right took two attempts: an earlier draft numbered
the new ones `4b` and `7`, and the first correction renumbered
`implement.md` alone, leaving this list with `packDefects` at 5 while
`implement.md` had it at 6. Round 2 caught the second version. Both lists
are now literally 1-8 in the same order, which is the only arrangement
that makes a cross-reference like "run 8" unambiguous.
