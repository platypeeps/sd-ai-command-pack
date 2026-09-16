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

1. **Pre-flight, before the first render.** A new function `link_plan` (no
   `source:` locator: the citation gate resolves one against today's tree)
   lists `bin/` the way `command_report` does and classifies `bin_dir/<name>`
   as absent, ours (a symlink whose target resolves to `checkout/bin/<name>`)
   or foreign (a regular file, a dangling link, a link anywhere else). One
   foreign entry refuses: `error: <path> exists and is not a link to
   <checkout>/bin/<name>; move it or pass --bin-dir`, return 1, nothing
   rendered, linked or written. This is the PR template's "no
   mutate-before-success".
2. **Link, after the renders and before the receipt write.** A new function
   `link_commands` makes `bin_dir` (`mkdir -p`), creates the absent links,
   leaves the ours links untouched, and returns one receipt row per name (the
   shape below, not a `Written`, which carries a digest). A checkout with no
   `bin/`, such as the `committed_checkout()` fixture, links nothing and
   creates no directory. Output: `linked N commands into <bin_dir>`, with
   `(not on PATH in this shell)` appended when no PATH entry resolves to it;
   under `--dry-run`, `would link N commands into <bin_dir>` and no write.

`bin_dir` is a `Context` field, so `--pull` carries it into the `cmd_user` it
calls. Default `home / ".local" / "bin"`; `--bin-dir DIR` overrides. Under a
sandbox (`Context.sandboxed`) a `--bin-dir` outside the home exits 2: the
containment rule `xdg_root` applies to an XDG override, refusing rather than
falling back because a typed flag is an intent and not inherited environment.
A scratch install never writes the real `~/.local/bin`, and
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
`hook`. A new function `prune_links` takes the link rows not in the current
set (all of them under `--uninstall`, the retired names under `--user`) and
removes a row only when `path` is still a symlink and `os.readlink(path)`
equals the recorded `target`; anything else is left and reported
`left in place (not our link): <path>`. A link the receipt does not name,
`~/bin/common/sd` say, is never touched, and `bin_dir` itself stays.
`source:bin/sd_install.py::cmd_uninstall` counts removed links in its
`removed N file(s)` line.

### `--status` counts per command

`source:bin/sd_install.py::command_report` replaces its directory test with
the per-name test its shadow line already makes: `shutil.which(name,
path=PATH)`, then `_resolves_to` against `checkout/bin/<name>` for ours, a
hit elsewhere for a shadow, no hit for missing.

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

- A machine whose `~/.local/bin` is not on PATH gets links that resolve
  nowhere; `--user` says so and `--status` says `not on PATH`. Accepted: the
  installer does not edit shells.
- `AGENTS.md` and three skills state the calling convention; code without
  the `AGENTS.md` edit leaves the repository contradicting itself. The PR
  carries the edit (`implement.md`, step 5).
- The 100% coverage gate makes every new branch a test obligation: the four
  rule tests plus the sandboxed `--bin-dir` refusal and `--dry-run`.

## Review

Planning adversarial review, 2026-09-16, the lane's own.

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

The three pages stand as written after round 3. The owner takes the three
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
| C-11 | 2 | low | no | parked |
| C-12 | 3 | medium | yes | addressed |

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
plan proper is 265 (`prd.md` 88, `design.md` 105 above this Review,
`implement.md` 72), and this Review adds the ledger the contract requires.
Parked, owner's call: the brief enumerates the content each page carries,
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

### Cross-artifact sweep

Each value was grepped across the three pages after rounds 2 and 3: `17`,
`Fourteen`/three commands without `Path(__file__)`, `2 of 3`, `12 of 17`,
the seven and the two existing `command_report` tests, `step 5`,
`link_plan`, `link_commands`, `prune_links`, `LinkTests` and the four test
names, `~/.local/bin`, `~/bin/common`, `kind: link`, exit codes 1 and 2,
`schema` 1, `c6879551`, `skills/sd-handoff/SKILL.md:18`. Every occurrence
agrees; every cross-artifact citation (`prd.md` Decisions, `implement.md`
step 5, `design.md` "Where the link step sits", this `## Review`) names a
heading that exists.

### Consequences

The code PR is the owner's to review and merge (`sensitive`), and the plan
leaves three choices open until the owner takes them. A plan without a
default on the link directory cannot start; the recommendation is there so a
one-word answer suffices.

### Reversal

Round 3 opens if Copilot's review of the planning PR raises a supported
concern, or if the owner's choices differ from the recommendation on any of
the three lines; either rewrites `design.md` and this ledger. Three of the
cap's 5 rounds are spent.
