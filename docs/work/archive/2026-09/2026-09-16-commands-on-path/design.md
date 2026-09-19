# Design — commands on PATH

## Approach

Symlinks, one per executable, into one directory. Rejected: a wrapper script
per command (a second copy that drifts from `bin/`) and a `PATH` edit (a
write to `~/.zshrc`, a file the installer does not own; the module docstring
of `bin/sd_install.py` forbids editing files it did not render). A symlink is
what the hand loop already makes, and `sys.path[0]` follows it.

### Where the link step sits in `--user`

`source:bin/sd_install.py::cmd_user` today: discover, render, `prune_stale`,
`install_hook`, excludes, `seed_registry`, build `owned`, `write_receipt`.
The link work splits in two so a refusal writes nothing:

1. **Pre-flight, first thing in `cmd_user`, before `open_library`.** A new
   function `link_plan` (no `source:` locator: the citation gate resolves
   one against today's tree) lists `bin/` the way `command_report` does and
   classifies `bin_dir/<name>` as absent, ours (a symlink, absolute or
   relative, that `_resolves_to` `checkout/bin/<name>`) or foreign (a
   regular file, a dangling link, a link anywhere else). One foreign entry
   refuses: `error: <path> exists and is not a link to <checkout>/bin/<name>;
   move it or pass --bin-dir`, return 1, nothing rendered, linked or written.
   Before the library on purpose: `open_library` then
   `source:bin/sd_install.py::expire_trials` ends expired trials in the
   shared database, a write, so a pre-flight placed merely before the first
   render would still mutate before refusing. This is the PR template's "no
   mutate-before-success".
2. **Link, after the renders and before the receipt write.** A new function
   `link_commands` makes `bin_dir` (`mkdir -p`), creates the absent links,
   leaves the ours links untouched, and returns one receipt row per name (the
   shape below, not a `Written`, which carries a digest). A checkout with no
   `bin/`, such as the `committed_checkout()` fixture, links nothing and
   creates no directory. An `OSError` on any link unlinks every link this
   call made, prints `error: could not link <path> (<strerror>)`, and
   returns 1 without a receipt write: the renders stand, and the next
   `--user` converges them, but no link exists that no receipt names.
   Output: `linked N commands into <bin_dir>`, with `warning: <bin_dir> is
   not on PATH in this shell` on the next line when no PATH entry resolves
   to it; under `--dry-run`, `would link N commands into <bin_dir>` and no
   write.

`bin_dir` is a `Context` field, so `--pull` carries it into the `cmd_user` it
calls. Default `home / ".local" / "bin"`; `--bin-dir DIR` overrides. Under a
sandbox (`Context.sandboxed`) a `--bin-dir` outside the home exits 2, and
`main` checks it while building the `Context`, before any mode runs:
`source:bin/sd_install.py::cmd_pull` fast-forwards the serving checkout
before it calls `cmd_user`, so a check inside the link step would pull first
and refuse second. Containment is on the resolved path,
`Path(bin_dir).resolve()` against `home.resolve()`, not on
`_is_within`'s lexical `relative_to`: `<home>/alias/bin` with
`alias -> /outside` passes the lexical test and writes outside (measured:
`relative_to` inside, `resolve()` outside). The rule is the one `xdg_root`
applies to an XDG override, refusing rather than falling back because a
typed flag is an intent and not inherited environment. A scratch install
never writes the real `~/.local/bin`, and
`test_every_written_path_is_under_the_given_home` holds. Outside a sandbox
any directory is honoured, `/usr/local/bin` included.

### Receipt row for a link

`schema` stays 1: a reader that ignores an unknown `kind` is unaffected.

```json
{"path": "/Users/x/.local/bin/sd-handoff", "kind": "link",
 "target": "/Users/x/repos/sd-ai-command-pack/bin/sd-handoff"}
```

`path` is the link, `target` what it points to; the checkout is the receipt's
top-level `checkout`, which `target` lies under. No `sha256`: a link has no
bytes of its own, and `prune_stale` digesting through it would read the
script and never match. Rows sort with the others by `(path, kind)`.

### What `--uninstall` and a re-render remove

`source:bin/sd_install.py::prune_stale` skips `kind == "link"` as it skips
`hook`. A new function `prune_links` takes the previous link rows and the
set of link paths this run produced, `{row["path"] for the link rows}`, a
set of its own and not `cmd_user`'s `current`, which holds rendered platform
paths and would retire every link on every run. Under `--uninstall` the set
is empty, so every row is a candidate; under `--user` only a retired name
is. A row is removed only when `path` is still a symlink and
`_resolves_to(path, target)`, the same test `link_plan` uses to call a link
ours, so a relative link kept at install is recognised at uninstall;
anything else, a retargeted link or a regular file at the path, is left and
reported `left in place (not our link): <path>`. A link the receipt does
not name, `~/bin/common/sd` say, is never touched, and `bin_dir` itself
stays.
`source:bin/sd_install.py::cmd_uninstall` counts removed links in its
`removed N file(s)` line.

### `--status` counts per command

`source:bin/sd_install.py::command_report` replaces its directory test with
the per-name test its shadow line already makes: `shutil.which(name,
path=PATH)`, then `_resolves_to` against `checkout/bin/<name>` for ours, a
hit elsewhere for a shadow, no hit for missing. `PATH` here is the
normalised list the function already builds for its directory test, the
non-empty components, joined back with `os.pathsep`; today the shadow line
passes the raw string, and `which` reads an empty component as the working
directory (measured: `path=":/usr/bin"` finds `./sd-probe`; `path=""` finds
nothing, on 3.9, 3.12, 3.13 and 3.14). A command in the working directory
is nobody's install and never counts.

- all ours: `commands: 17 in bin/, 17 resolve on PATH from this checkout`;
- some: `commands: 17 in bin/, 12 of 17 resolve on PATH from this checkout
  (missing: sd-check, sd-note, sd-review, sd-ship, sd-status)`, every
  missing name, since the list is bounded by the count in `bin/`;
- none: `commands: 17 in bin/, not on PATH -- invoke by path (bin/sd)`;
- the `[N shadowed by another install: <name>]` suffix stays on every line.

A `bin/` on PATH is the all-ours case, so the two existing tests asserting
`on PATH from this checkout` pass unchanged. The docstring drops "links no
executable anywhere" and says what `--user` links and where.

## Decisions

- 2026-09-16, lane: the refusal runs before the first render, not between
  render and receipt as the brief placed the step. Reverses if the owner
  prefers converge-then-refuse; nothing else depends on it.
- 2026-09-16, lane, pending owner: `~/.local/bin` default, links on by
  default, `--pull` unchanged (`prd.md`, Decisions for the owner).

## Risks

- A machine whose link directory is not on PATH gets links that resolve
  nowhere; `--user` warns and `--status` says `not on PATH`. Accepted: the
  installer does not edit shells, and `--bin-dir` names one that is.
- A link failure after some links are made is rolled back (above), but a
  failure inside the rollback itself leaves a link no receipt names; the
  error line names the path, and the next `--user` keeps it as ours.
- `AGENTS.md`, `docs/lane-brief.md` and three skills state the calling
  convention; code without the `AGENTS.md` edit leaves the repository
  contradicting itself. The PR carries the edit (`implement.md`, step 5);
  the lane brief keeps by-path on purpose, since a lane reads the store
  from a named checkout and a bare name resolves against whatever PATH holds.
- The 100% coverage gate makes every new branch a test obligation: the four
  rule tests plus the sandboxed `--bin-dir` refusal and `--dry-run`.

## Review

Planning adversarial review, 2026-09-16. Rounds 1-3 are the lane's own;
round 4 folds Copilot's review of the planning PR (#1000, at `756f5abd`,
3 inline and 12 suppressed findings, effort Lite) through the same ledger,
and round 5 folds its pass on the round-4 push (at `d97efc2c`, 1 inline and
7 suppressed, "eight unresolved moderate findings"). Five rounds is the cap;
no further round starts on its own. Round 5 changes this ledger only: the
pages above it are the ones the code lane builds from, and an edit to them
would call for a sixth round the cap does not allow.

### Context

`bin/sd_install.py` is a `sensitive` path in `.github/sd-review.json`, so
the planning adversarial review contract
(`.claude/sd-ai-command-pack/planning-adversarial-review.md`) applies in
full to `prd.md`, `design.md` and `implement.md`: a
`C-*` ledger, a cross-artifact sweep per round, and the Development /
prd-and-design cap of 5 rounds. Baseline at `c6879551`: none of the three
pages existed. The pack defines no second lane; the host review is the whole
review. Copilot's review of the pull request folds through this ledger.

### Decision

The three pages stand as written after round 4; round 5 parks eight
findings on the code lane, none blocking. The owner takes the three
choices `prd.md` lists under "Decisions for the owner"; the lane's
recommendation is `~/.local/bin`, links on by default, `--pull` unchanged.

### Concern ledger

| ID | Round | Severity | Blocking | Disposition |
|---|---|---|---|---|
| C-1 | 1 | high | yes | addressed |
| C-2 | 1 | medium | yes | addressed |
| C-3 | 1 | medium | yes | addressed |
| C-4 | 1 | high | yes | addressed |
| C-5 | 1 | medium | no | addressed |
| C-6 | 1 | medium | no | addressed |
| C-7 | 1 | low | no | addressed |
| C-8 | 2 | medium | no | addressed |
| C-9 | 2 | low | no | addressed |
| C-10 | 2 | low | no | rebutted |
| C-11 | 2 | low | no | resolved |
| C-12 | 3 | medium | yes | addressed |
| C-13 | 4 | high | yes | addressed |
| C-14 | 4 | medium | yes | addressed |
| C-15 | 4 | medium | no | addressed |
| C-16 | 4 | high | yes | addressed |
| C-17 | 4 | high | yes | addressed |
| C-18 | 4 | medium | yes | addressed |
| C-19 | 4 | medium | no | addressed |
| C-20 | 4 | high | yes | addressed |
| C-21 | 4 | medium | no | addressed |
| C-22 | 4 | medium | no | addressed |
| C-23 | 4 | medium | no | addressed |
| C-24 | 4 | low | no | addressed |
| C-25 | 4 | medium | no | addressed |
| C-26 | 4 | medium | yes | addressed |
| C-27 | 4 | low | no | addressed |
| C-28 | 5 | medium | no | addressed |
| C-29 | 5 | medium | no | rebutted |
| C-30 | 5 | medium | no | addressed |
| C-31 | 5 | medium | no | addressed |
| C-32 | 5 | medium | no | addressed |
| C-33 | 5 | medium | no | addressed |
| C-34 | 5 | low | no | addressed |
| C-35 | 5 | low | no | addressed |

**C-1, a third copy of the rule the item names two of.** The item's rule 3
names the README table and the `command_report` docstring. `AGENTS.md`
"Calling Convention" also says the installer "links no executable anywhere"
and that by-path is "the only convention the repository supports". Code that
lands with only two of three edited leaves the repository contradicting
itself. Evidence: `grep -rn "links no executable"` at `c6879551` finds
`bin/sd_install.py`, `AGENTS.md` and one historical `implement.md`.
Addressed: `prd.md` requirement 3, `design.md` Risks, `implement.md` step 5.

**C-2, a `source:` locator for a symbol that does not exist.** The first
draft cited `link_plan`, `link_commands` and `prune_links` as
`source:bin/sd_install.py::<symbol>`; `stable_source_citations` in
`tests/test_doc_citations.py` resolves each against today's tree and fails a
missing declaration. Addressed: the new functions are named in prose, the
existing ones keep their locators, and the gate ran green.

**C-3, "after the render, before the receipt write" against "nothing else
written".** The brief places the link step after the render; the refusal
must write nothing. Placed as one step, a foreign file at one target would
refuse after every render was written. Addressed: `design.md` splits the
check (pre-flight, before the first render) from the write (after the
renders); recorded under Decisions there.

**C-4, `prune_stale` would strand every link on uninstall.** Evidence:
`source:bin/sd_install.py::prune_stale` reads `entry.get("sha256")`, digests
`target.read_bytes()`, and skips on mismatch; a link row has no digest and
`read_bytes` follows the link into the script, so every link would be
reported "modified since it was installed" and left. Addressed: `design.md`
skips `kind == "link"` in `prune_stale` and adds `prune_links` keyed on
`os.readlink`.

**C-5, a link row is not a `Written`.** `Written` carries `sha256: str`;
the first draft returned "`Written`-shaped rows". Addressed: `design.md`
gives the row shape and says it is not a `Written`.

**C-6, the fixture checkout has no `bin/`.** `committed_checkout()` in
`tests/test_sd_install.py` writes one skill and no `bin/`; a link step that
created `bin_dir` unconditionally would change every receipt-equality test.
Addressed: `design.md`, "links nothing and creates no directory".

**C-7, requirement numbering drifted from the item.** The first `prd.md`
split the item's rule 1 into two and shifted the rest, and `implement.md`
cited "rule 2" for uninstall while the item's rule 2 is `--status`.
Addressed: four requirements in the item's numbering; every "rule N" in
`implement.md` is the item's.

**C-8, `xdg_root` falls back, the flag refuses.** `design.md` said the
sandboxed `--bin-dir` refusal works "the way `xdg_root` contains" an
override; `xdg_root` silently falls back to the home. Addressed: the
paragraph now states the difference and the reason.

**C-9, the missing-name list was shown truncated.** The example line ended
`...`, which reads as truncation. Addressed: every missing name is listed;
the bound is the count in `bin/`.

**C-10, `shutil.which(name, path="")`.** Concern that an empty `PATH` falls
back to the process environment and finds a real install. Rebutted: the
existing `command_report` already passes `environ.get("PATH", "")` and its
`PATH=""` tests pass at `c6879551` (`make check` below); CPython's `which`
returns `None` for an empty `path`.

**C-11, size.** The brief asks for ~120-180 lines across three pages; the
plan proper is 320 after round 4 (`prd.md` 94, `design.md` 140 above this
Review, `implement.md` 86 above its completion report), and this Review
adds the ledger the contract requires.
Resolved 2026-09-19 by owner ruling, the item having shipped at that size: the brief enumerates the content each page carries,
and a shorter set drops one of those items. Trigger: the owner asks; owner:
plan-969's successor lane.

**C-12, the ledger cannot live in `decision.md` beside the pages.** The
brief asked for it there, from the `decision.md` template. Rule 1 of
`bin/sd-docs-lint` (`check_shape`) fails any file in a work item other than
`prd.md`, `design.md`, `implement.md` and `.citations.tsv`, and the
2026-09-04 item `the-plan-interview-is-one-sentence` carries its ledger under
`## Review` in `design.md` for that reason. Addressed: the ledger is this
section; the template's Context, Decision, Consequences and Reversal headings
stay as sub-headings so the record keeps its shape.

**C-13, lexical containment lets a symlinked parent escape.** Copilot,
inline at the `--bin-dir` paragraph: `<home>/alias/bin` with `alias ->
/outside` passes `relative_to` and writes outside. Measured with a scratch
home: `relative_to` inside, `resolve()` outside. Addressed: containment on
the resolved path; a symlink-parent test in step 6.

**C-14, a relative link is kept at install and refused at uninstall.**
Copilot, inline: `link_plan` resolves, `prune_links` compared raw
`os.readlink` to an absolute target. Addressed: `prune_links` uses
`_resolves_to`, the same test; test 1 installs over a relative link, test 3
uninstalls it.

**C-15, test 2 covered one of three foreign shapes.** Copilot, inline.
Addressed: test 2 runs over a regular file, a dangling link and a link into
a second checkout.

**C-16, `--pull --bin-dir <outside>` pulls before it refuses.** Copilot,
suppressed. Evidence: `source:bin/sd_install.py::cmd_pull` runs
`git pull --ff-only` and then `cmd_user`. Addressed: `main` checks
`bin_dir` while building the `Context`; step 6 tests both modes and asserts
the fixture's commit is unchanged.

**C-17, `expire_trials` writes before a pre-flight placed before the first
render.** Copilot, suppressed. Evidence: `cmd_user` opens the library and
calls `source:bin/sd_install.py::expire_trials`, which calls
`sd_db.end_trial`, before `discover_surfaces`. Addressed: `link_plan` is the
first thing `cmd_user` does; test 2 asserts an expired trial row survives a
refusal.

**C-18, a partial link failure leaves unrecorded links.** Copilot,
suppressed. Addressed: `link_commands` unlinks what it made on the first
`OSError`, returns 1, writes no receipt; step 6 tests it with a patched
`os.symlink`; Risks names the residual (a failure inside the rollback).

**C-19, the C-10 rebuttal.** Copilot, suppressed: "`shutil.which` treats an
empty PATH component as the current directory, so `which(name, path="")`
can find `./name`". Measured with `sd-probe` in the working directory:
`path=""` returns `None` on CPython 3.9.6, 3.12.14, 3.13.15 and 3.14.7, so
the literal claim does not hold and C-10 stays rebutted. The neighbouring
claim holds: `path=":/usr/bin"` and `path="/usr/bin:"` both find
`./sd-probe`, and today's shadow line passes the raw string while the
directory test drops empty components. Addressed: one normalised list for
both tests; a working-directory test with `PATH=":"` in step 6.

**C-20, `prune_links` cannot reuse `current`.** Copilot, suppressed.
Evidence: `current` is `{str(item.path) for item in written}`, rendered
paths, so every link would retire on every run and the kept-inode rule
would break. Addressed: the link-path set is defined as its own set.

**C-21, the README ownership paragraph says every row has a digest.**
Copilot, suppressed. Evidence: "records every path the installer wrote
together with the digest of what it wrote". Addressed: step 5 edits it.

**C-22, rule 3 had no test.** Copilot, suppressed. Addressed: test 5, a
contract test on the three documents, in step 5; the mutation list gains it.

**C-23, test 3 skipped the safety branch.** Copilot, suppressed.
Addressed: a retargeted link and a regular file at a recorded path are
fixtures of test 3, both `left in place`.

**C-24, `docs/lane-brief.md` also says by-path only.** Copilot, suppressed.
Evidence: its template reads "never as a bare `sd`. That is the only calling
convention this repository supports". Addressed as a deliberate exception:
a lane reads the store from a named checkout, and a bare name resolves
against whatever PATH holds; step 5 adds the clause and Risks names it.

**C-25, the README machine-write inventory omits the links.** Copilot,
suppressed. Evidence: "What it writes on a machine" lists four paths and the
hook entries. Addressed: step 5 adds the link directory line.

**C-26, "on PATH" is not guaranteed by the default.** Copilot, suppressed.
Addressed: requirement 1 is restated as a configured link directory with a
warning when it is not on PATH, no refusal, the shell being the owner's;
`prd.md` Decisions names `--bin-dir ~/bin/common` for a machine whose
`~/.zshrc` appends that directory and not `~/.local/bin`.

**C-27, `sd-plan` has no `bin/` half.** Copilot, suppressed, on the
Problem bullet naming `sd-plan` and `sd-research-repo`. Evidence:
`skills/sd-plan/SKILL.md:191` says so. The bullet meant the `bin/` commands
those skills invoke bare, `sd-trackers` and `sd-research-kit`, both
executables in `bin/`; addressed by naming the commands and their lines.

**Round 5, how the eight are dispositioned.** Copilot rated all eight
moderate. None is blocking: each is a case inside a rule the pages already
state (foreign entries refuse, a failed link run leaves no unrecorded link,
`prune_links` removes only our links, a working-directory hit never counts),
not a scope, requirement or assumption error. The seven that hold are
parked, not addressed: trigger, the code PR for this item; owner, the code
lane, which carries each into the implementation and its tests under the
rule named. The pages are unchanged by direction of the coordinating
session, so the code lane reads the cases from this ledger.

**C-28, a directory at the target was not foreign.** Copilot, suppressed.
"Where the link step sits" lists the foreign shapes as a regular file, a
dangling link, a link anywhere else; a directory fell through the list, and
`os.symlink` on it raises `FileExistsError` after the renders. Parked for
the code lane: `link_plan` treats everything that exists (`lexists`) and is
not ours as foreign, a directory included, and test 2 runs a fourth
`subTest` over a directory.

**C-29, the rollback boundary against the writes before the link stage.**
Copilot, suppressed: the unlink-on-failure leaves the renders, the pruned
files, the hook and the excludes edit in place, so the rollback is partial.
Rebutted: that boundary is the one `cmd_user` has today. Evidence:
`source:bin/sd_install.py::cmd_user` renders, prunes, installs the hook,
edits excludes and seeds the registry before `write_receipt`, and any
failure between them already leaves the writes recorded by the previous
receipt or by nobody; the next `--user` rewrites the same paths and records
them. The link step neither widens nor narrows that. What it adds is that
no link outlives a failed run, because a link, unlike a render, is kept on
the next run rather than rewritten, and a kept link no receipt names would
be invisible to `--uninstall` for good. The code lane tests the two-run
recovery (a failed run, then a clean `--user` that records every render and
link) under step 6.

**C-30, `--bin-dir X` then a plain `--user`.** Copilot, suppressed. The
design says the flag overrides the default; a later run without it produces
the default directory's rows, `prune_links` retires X's links, and the new
receipt does not name them. Parked for the code lane: the receipt carries a
top-level `binDir`; a run without the flag reuses it; a different flag
relocates in one run (X's links removed, Y's created, one receipt). Two-run
test under step 6.

**C-31, `mkdir -p` outside the handled path.** Copilot, suppressed: the
design names `os.symlink` as the `OSError` source and the directory
creation could raise first. Parked for the code lane: the `mkdir -p` sits
inside the same `OSError` handling, the same `error: could not link` line,
rc 1, no traceback; step 6 tests an unwritable directory (`Path.mkdir`
patched to raise).

**C-32, `PATH="."` resolves the working directory.** Copilot, suppressed.
Measured: `shutil.which("sd-probe", path=".")` returns `./sd-probe` on the
same four CPython versions as C-19. The design's normalised list drops the
empty components only. Parked for the code lane: the list keeps absolute
components only, so a relative component counts neither as ours nor as a
shadow; step 6 tests `PATH="."` next to `PATH=":"`.

**C-33, a malformed `kind: link` row aborts `--uninstall`.** Copilot,
suppressed. Evidence: `source:bin/sd_install.py::owned_entries` admits any
dict with a `path`, so a `link` row without a `target` reaches
`prune_links`, and `PruneTests` already covers malformed rows for
`prune_stale`. Parked for the code lane: a row whose `path` or `target` is
missing or not a string is skipped and reported `left in place (malformed
link row): <path>`; test 3 appends one such row to the receipt.

**C-34, test 3 replaced the relative link before exercising it.** Copilot,
suppressed. Test 3 replaces the second recorded link, the relative one from
test 1, with a regular file, so no test removes a relative link. Parked for
the code lane: the relative link stays and is the one `--uninstall`
removes; the regular file takes the third slot.

**C-35, no test asserts the not-on-PATH warning.** Copilot, inline. Test 1
asserts the links and the receipt, not the `warning:` line. Parked for the
code lane: test 1 runs once with a `PATH` that lacks the directory and
asserts the line, and once with it on `PATH` and asserts its absence.

### Cross-artifact sweep

Each value was grepped across the three pages after rounds 2, 3, 4 and 5: `17`,
`Fourteen`/three commands without `Path(__file__)`, `2 of 3`, `12 of 17`,
the seven and the two existing `command_report` tests, `step 5`,
`link_plan`, `link_commands`, `prune_links`, `LinkTests` and the four test
names, `~/.local/bin`, `~/bin/common`, `kind: link`, exit codes 1 and 2,
`schema` 1, `c6879551`, `skills/sd-handoff/SKILL.md:18`, and after round 4
`three executables`/`three` rows in tests 1 and 3, `sd-trackers`,
`sd-research-kit`, `_resolves_to`, `expire_trials`, `cmd_pull`, `test 5`,
`PATH=":"`, `~/bin/common`. Every occurrence
agrees; every cross-artifact citation (`prd.md` Decisions, `implement.md`
step 5, `design.md` "Where the link step sits", this `## Review`) names a
heading that exists.

### Consequences

The code PR is the owner's to review and merge (`sensitive`), and the plan
leaves three choices open until the owner takes them. A plan without a
default on the link directory cannot start; the recommendation is there so a
one-word answer suffices.

### Reversal

The cap of 5 is spent. Whatever Copilot posts on the round-5 push is
residue for the owner, read and listed in the lane report, not a sixth
round. The owner's choices differing from the recommendation on any of the
three lines rewrites `design.md` and this ledger under a new item or an
owner-opened round.
