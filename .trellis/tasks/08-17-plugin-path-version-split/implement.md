# Implementation: one way for a skill to reach a pack helper

Ordered. Each step names its own validation. Steps 1-3 are the fix; 4-6 are the
gate, the report, and the proof.

## Step 0 — re-enumerate before editing

**Edit `templates/**`, never the repository's own `.agents/skills/` or
`.claude/skills/`.** `AGENTS.md:36` makes `templates/**` the source of truth for
shipped payloads, and `make sync` overwrites the repo-level copies from it. A
diff applied to the installed trees is reverted by the next sync without a
word.

Re-derive the counts from the filesystem before touching anything; do not trust
the tables in `design.md`.

```bash
python3 - <<'EOF'
import re, pathlib
pat = re.compile(r'sd-ai-command-pack-[A-Za-z0-9_-]+\.(?:mjs|py|sh)')
AUTHORED = [
    ('templates/.agents/skills', '*.md'),
    ('templates/docs', 'SD_AI_COMMAND_PACK.md'),
    ('.github/command-sources', '*.md'),
]
ta = tb = 0
for root, glob in AUTHORED:
    a = b = 0
    for p in sorted(pathlib.Path(root).rglob(glob)):
        for i, line in enumerate(p.read_text().splitlines(), 1):
            if not pat.search(line):
                continue
            if 'toolchain.sh' in line:
                a += 1
            elif re.match(r'\s*(bash|node|python3) ', line):
                b += 1
                print(f'class B  {p}:{i}')
    print(f'{root}: class A {a} | class B {b}')
    ta += a; tb += b
print(f'TOTAL authored: class A {ta} | class B {tb}')
EOF
```

Expect `class A 67 | class B 17`, split 50/9 across the skills, 15/8 in
`templates/docs/SD_AI_COMMAND_PACK.md`, and 2/0 in `.github/command-sources`. A
materially different count means the payloads moved since the design was
written — reconcile before continuing, do not adjust the plan silently.

**Glob `*.md`, not `SKILL.md`.** Eight of the 22 skill files are `references/`
and `charters/` documents — `sd-help/references/recovery-artifacts.md`,
`sd-ship/references/watch-coordinator.md`, and six more — and they carry 13 of
the skills' 50 class-A occurrences. They are executed exactly like `SKILL.md`
text and must be converted with them. A `SKILL.md`-only sweep reports 37 and
silently leaves those thirteen behind.

**Do not edit the generated adapter copies.** `templates/.commands/`,
`templates/.claude/`, `templates/.gemini/`, and `templates/.github/` each carry
two occurrences derived from the two in `.github/command-sources/`
(`sd-review.md`, `sd-status.md`). Fix the sources and run `make generate`;
hand-editing the adapters puts them out of sync with their generator.

## Step 1 — write the bootstrap reference

New file `templates/.agents/skills/sd-help/references/pack-helper-resolution.md`.
It holds
the bootstrap snippet from `design.md` and the one rule, and it is the single
place either is stated. Every skill cites it; no skill restates the resolution
order in its own words, because two copies of an ordering is one copy going
stale.

Content, minimally:

- the bootstrap snippet, verbatim and copy-pasteable;
- the resolution order and *why* each entry is where it is, especially why
  `PATH` is absent;
- the `run --` first-operand trap: never name the interpreter;
- what to do when the bootstrap fails (reinstall; the message names all three
  candidates it checked).

`sd-help` is the right home because it already owns the shared references the
other skills cite (`structured-questions.md`,
`completion-lifecycle.md`, `recovery-artifacts.md`).

Validation: the file exists and the snippet in it is byte-identical to the one
the skills use. Step 4's gate enforces the second half.

## Step 2 — convert class B to class A

The seventeen class-B invocations, from Step 0's own output rather than from
this list. These are **not** the bare-name occurrences `prd.md` counts; the two
sets are disjoint. As of 2026-08-17, nine are under
`templates/.agents/skills/` — `sd-fleet-refresh:181`, `sd-review-pr:234`,
`sd-review-pr:776`, `sd-finish-work:85`, `sd-finish-work:150`,
`sd-housekeeping:22`, `sd-housekeeping:30`, `sd-update-deps:84`,
`sd-create-pr:218` — and eight are command examples in
`templates/docs/SD_AI_COMMAND_PACK.md`.

Each becomes:

```bash
bash "$SD_PACK_TOOLCHAIN" run -- <bare-helper-name> [args...]
```

**Do not name the interpreter.** `run` resolves only its first operand, so
`run -- node sd-ai-command-pack-review-preflight.mjs` resolves `node`, leaves
the `.mjs` unresolved, and fails. The helpers carry shebangs
(`#!/usr/bin/env node`, `#!/usr/bin/env bash`) and are executable in the machine
install; that is what makes the interpreter unnecessary. Re-verify rather than
assume:

```bash
shopt -s nullglob
found=0
for h in "$HOME"/.agents/bin/sd-ai-command-pack-*; do
  found=1
  [ -x "$h" ] || printf 'NOT EXECUTABLE: %s\n' "$h"
done
[ "$found" = 1 ] || printf 'no pack helpers found in %s/.agents/bin\n' "$HOME" >&2
```

Iterate the glob directly rather than `$(ls …)`: word-splitting `ls` output
breaks on any path containing whitespace, and an unmatched glob would otherwise
be passed through literally and reported as a missing file. `nullglob` plus the
`found` flag turns "no helpers at all" into its own diagnosis instead of a
silent pass.

Any non-executable helper that a skill invokes directly blocks this step for
that helper — report it, do not work around it by naming the interpreter.

`sd-create-pr:213-218` is the special case. Delete the `command -v` guard
outright rather than repairing it: the bootstrap's failure branch is now the
diagnosis, and the guard existed only because the invocation could disagree with
it. That disagreement is the defect recorded in `design.md`.

## Step 3 — convert class A bootstraps

In `templates/.agents/skills/**`, `templates/docs/SD_AI_COMMAND_PACK.md`, and
`.github/command-sources/**`, replace every
`bash scripts/sd-ai-command-pack-toolchain.sh` with the bootstrap plus
`bash "$SD_PACK_TOOLCHAIN"`, **and drop the `scripts/` prefix from the operand
too**:

```bash
bash "$SD_PACK_TOOLCHAIN" run-python -- sd-ai-command-pack-status.py --json
```

The operand change is not strictly required for correctness —
`resolve_pack_script_operand` strips a `scripts/` prefix
(`scripts/sd-ai-command-pack-toolchain.sh:48`), so the old operand resolves
fine. It is required for the gate. Step 4 rule 1 forbids `scripts/` in any
executable block with no exception, because a gate that carved out operands
would have to tell the harmless prefix apart from the CWD-relative bootstrap
that is the defect. Leaving operands prefixed would make the converted tree fail
its own gate.

A skill with several blocks resolves the bootstrap once per block, not once per
file — each fenced block is executed independently and cannot rely on a variable
set in an earlier one.

Validation after this step — authored trees clean, then regenerate and confirm
the generated layers followed:

```bash
grep -rn "scripts/sd-ai-command-pack-toolchain.sh" \
  templates/.agents/skills templates/docs .github/command-sources \
  || echo "authored trees clean"
make generate && make sync
grep -rn "scripts/sd-ai-command-pack-toolchain.sh" templates .agents .claude \
  || echo "generated layers followed"
```

## Step 4 — the gate

Add a check to `make check` that enumerates the **authored** trees from the
filesystem — every `*.md` under `templates/.agents/skills/` (not just
`SKILL.md`, for the reason Step 0 gives), plus
`templates/docs/SD_AI_COMMAND_PACK.md` and `.github/command-sources/**` — and
fails on:

1. `scripts/sd-ai-command-pack-` inside a fenced executable block — with no
   exception for toolchain operands, which Step 3 therefore strips;
2. `bash|node|python3` directly invoking a `sd-ai-command-pack-*` helper;
3. a pack helper name appearing as the **second** operand of `run --`.

Rule 3 is the one that catches the interpreter trap, and it is the rule most
likely to be omitted because the failure it prevents looks like working code.

Enumerating from `rglob('*.md')` rather than from a fixed list is deliberate: a
skill or reference file added later is covered without anyone remembering to
edit the gate. The gate scans authored trees only — running it over the
generated copies would report every defect twice and fail a tree whose only
repair is `make generate`.

Prose references must **not** fail the gate — restrict rules 1 and 2 to fenced
`bash` blocks. Nine prose occurrences exist today and two of them
(`sd-review-pr:262-263`) instruct the reader not to use the scripts they name;
a gate that flagged those would be telling the author to break the sentence.

Validation: the gate fails on a deliberately reintroduced scripts-prefixed
toolchain line and passes on the converted tree. Both
directions — a gate only ever observed passing has not been tested.

## Step 5 — `sd-status` reporting

Extend the machine-scope section of `scripts/sd-ai-command-pack-status.py` with
one row: the toolchain the bootstrap resolves, its install root, every `PATH`
entry naming a pack `bin/` in `PATH` order, and a verdict of `bound` or
`shadowed`.

Do not overload the existing install-versus-target line. It answers a different
question — which release is installed — and requirement 3 says explicitly it
must not be made to imply this one.

`shadowed` is the reporting machine's state today and renders as an advisory,
not a blocker: after Steps 1-3 the skills no longer consult `PATH`, so a stale
cache entry is inert. Rendering it as a failure would train operators to ignore
it.

Tests: one for `bound`, one for `shadowed`, and one for the thin-consumer path
where no `scripts/` directory exists.

**Amended 2026-08-17, during implementation.** "Advisory" is implemented as a
report row only, not as an `[advisory]` anomaly, following the rule the
machine-scope section already applies to its `skew` comparison: machine scope
describes the machine, not the reported repository. Promoting it would have put
`--expect-clean` in every repository under the operator's `PATH` — a value that
repository cannot change — and made the status test suite host-dependent, which
is how the choice surfaced: five scratch-repo tests changed their follow-up
ordinals on a machine whose `PATH` happens to carry a stale plugin cache.

A fourth verdict, `unresolved`, is also reported: no candidate answered. It is
distinct from `bound` with nothing on `PATH`, and the row has to say which.

## Step 6 — prove it against a real split

The acceptance criterion says "demonstrated against a deliberately constructed
split, not only against a clean machine." Construct it with the override rather
than by editing `PATH`, which requirement 5 forbids:

```bash
SD_AI_COMMAND_PACK_TOOLCHAIN=/path/to/older/cache/bin/sd-ai-command-pack-toolchain.sh \
  <run a converted skill's block>
```

Expect: every helper in that run comes from the older install — coherent, not
mixed — and `sd-status` reports `shadowed` naming both roots. A run that mixes
two installs fails the criterion even if it exits zero.

Then the thin-consumer half, read-only, from a checkout that is **clean at that
moment** — re-check immediately before, per `08-08-fleet-one-path`'s per-lane
rule; do not reuse an earlier cleanliness reading:

```bash
cd <clean thin consumer>
node scripts/sd-ai-command-pack-review-preflight.mjs   # before: throws
# after conversion, via the bootstrap: resolves from ~/.agents/bin
```

Never write into the consumer. This step reads and runs read-only helpers only.

### Run on 2026-08-17

**The constructed split.** The override pointed at the stale plugin cache this
task was filed for, `~/.claude/plugins/cache/sd-ai-command-pack/sd/0.71.22/bin`,
against a `0.71.29` install. Coherence is observable rather than argued: naming
a helper that does not exist makes the toolchain print the directory it resolves
every helper against, and that directory was the `0.71.22` `bin/` —

```text
pack helper is missing next to the toolchain:
/Users/sven/.claude/plugins/cache/sd-ai-command-pack/sd/0.71.22/bin/sd-ai-command-pack-does-not-exist.py
```

— and the helper that did run was the old one, not the working checkout's:
`sd-ai-command-pack-status.py --json` reported `machineScope.schemaVersion 1`
with no `resolution` row, which is exactly the copy that predates Step 5. One
install answered the whole run.

**`sd-status` on the split machine.** `- helper resolution: shadowed;
.../sd-ai-command-pack/scripts/sd-ai-command-pack-toolchain.sh (via checkout,
root .../sd-ai-command-pack); PATH pack bins (1, in order):
~/.claude/plugins/cache/sd-ai-command-pack/sd/0.71.22/bin` — both roots named,
exit status unchanged.

**The thin consumer.** `~/repos/rwbp/rwbp-coordinator`, re-read clean
(`git status --porcelain` = 0 lines) immediately before and again after. It has
its own `scripts/` directory but no vendored pack copy, which is the shape the
old form assumed and this one does not:

```text
$ bash scripts/sd-ai-command-pack-toolchain.sh run -- ...
bash: scripts/sd-ai-command-pack-toolchain.sh: No such file or directory

$ <bootstrap>; echo "$SD_PACK_TOOLCHAIN"
/Users/sven/.agents/bin/sd-ai-command-pack-toolchain.sh
```

Through it, both a Node helper (`sd-ai-command-pack-review-preflight.mjs`) and a
Python helper (`sd-ai-command-pack-status.py --json --no-network`) resolved and
ran from `~/.agents/bin`. Nothing was written to the consumer.

## Validation summary

```bash
make check                                    # includes the new gate
python3 -m pytest tests/test_status.py -q     # Step 5's three cases
grep -rn "scripts/sd-ai-command-pack" \
  templates/.agents/skills templates/docs .github/command-sources
```

## Rollback

Steps 1-4 are text and one gate; revert the commit. Step 5 is additive
reporting and reverts independently. Nothing here writes to a consumer, changes
`PATH`, or touches the plugin cache, so there is no external state to unwind.

## What this task does not close

`sd-status` cannot report which `SKILL.md` text the agent loaded — no process
can observe it. `design.md` records this as a limit rather than a gap: coherence
along the executed path is structural, and the unobservable half is not claimed.
