# Design — correct the repo-relative claim the thin repoint contradicts

## The defect, stated precisely

`installer/references.py:468` defines `THIN_PROFILE` with
`script_template=f"{AGENTS_BIN_REFERENCE}/{{name}}"`, so the thin rewrite maps
`scripts/sd-ai-command-pack-housekeeping.sh` to
`~/.agents/bin/sd-ai-command-pack-housekeeping.sh`. It rewrites the path token
and nothing around it. The prose around it says the path is "relative to the
repository root", which was true of the token before the swap and false after.

Reproduced in-process against the current templates, no consumer required:

```python
from installer.references import rewrite_text, THIN_PROFILE
text = open("templates/.github/prompts/sd-housekeeping.prompt.md").read()
out = rewrite_text(text, profile=THIN_PROFILE,
                   key=".github/prompts/sd-housekeeping.prompt.md")
```

which prints, today:

```
3. Verify that `~/.agents/bin/sd-ai-command-pack-housekeeping.sh` is resolvable
and readable, either as a bare command on `PATH` or as a file at that path
relative to the repository root. ...
```

An absolute path under `$HOME`, described in the same sentence as repo-relative.
This harness is also the acceptance check: after the fix it prints nothing.

## The fix

Delete four words from each source. In both
`.github/command-sources/sd-review-learnings.md:12` and
`.github/command-sources/sd-housekeeping.md:13`:

```
- ... or as a file at that path relative to the repository root.
+ ... or as a file at that path.
```

"at that path" is true in both shapes. Fat: the path reads `scripts/…` and the
file is there. Thin: the path reads `~/.agents/bin/…` and the file is there.
The sentence stops asserting anything about *where* that path is anchored,
which is precisely the fact the rewrite changes and the prose has no way to
track.

Nothing is lost. The clause never told a reader anything the path did not
already say — a reader looking at `scripts/sd-ai-command-pack-housekeeping.sh`
does not need to be told it is repo-relative.

## The alternative, and why not

`THIN_PROFILE` already carries a `literal_rewrites` map for exactly this class
of problem: prose the path swap invalidates. Adding
`"at that path relative to the repository root"` → `"at that path"` would keep
the fat text maximally explicit and fix thin.

Rejected, for two reasons.

The first is coupling. A `literal_rewrite` is a second copy of the sentence,
matched byte-exactly. Any later edit to the source wording — a comma, a
rewrap across the line break — silently stops matching, and the failure is a
consumer quietly regaining the contradiction with nothing red anywhere. The
existing `literal_rewrites` entries earn that cost because they have no
shape-independent phrasing available: `.agents/skills/sd-*/SKILL.md` genuinely
must become `~/.agents/skills`, since the population it globs does not survive.
This clause has a shape-independent phrasing available, so it does not.

The second is blast radius. `.github/command-sources/sd-audit-repo.md` ends
with the same six words for a path the rewrite does *not* touch, and its
sentence is correct. A literal rewrite keyed on the closing words alone would
match it too and would have to be keyed on more surrounding text to avoid that
— more bytes to drift, for a case that needs no rewrite at all.

The precedent is 0.71.41: the `sd-review` adapter named a machine-scope script
that thin consumers do not carry, and the fix was to stop the prose making the
claim rather than to teach the rewrite a new substitution.

## Blast radius

Two authored sources, 11 generated mirrors each: 24 files carry the clause in
this repository, 22 of them generated. An earlier count said 18/16 by grepping
only `*.md`, which silently dropped the Gemini TOML family — the `.gemini`
adapters carry the same prose inside a TOML string. Measured from the changed
set after regeneration, not from the grep that missed them.

Propagation is two commands, not one. `make generate` runs
`generate-command-surfaces.py`, which writes the `templates/…` copies, plus
`generate-plugin.py`, which writes `plugins/sd/…`. The repository's own adapter
directories — `.claude/commands/sd/`, `.github/prompts/`, `.opencode/commands/`
— are an *install* of those templates into this checkout, written by
`make sync` (`install.py . --force`). Editing a source and running only
`make generate` leaves this repo's own adapters stale — 8 of the 22, across
`.claude`, `.gemini`, `.github/prompts`, and `.opencode`. `make generate`
itself fails loudly in that state rather than passing quietly: `surface-check`
reports `mirror.stale` per file and names `make sync` as the preparation.

`prepare-release.py` runs both in that order (generate, partition, plugin,
provider-config, then the self-sync install), so `make release-prep` closes any
gap. Running them explicitly first is for seeing the propagation diff before it
is buried in a release-prep run.

Only one of those surfaces reaches a thin consumer. Measured on hoa-manager,
the only affected file per command is `.github/prompts/sd-<name>.prompt.md`;
the Claude and opencode adapters are not vendored, because a thin consumer
carries no `.agents/skills/sd-*` at all and resolves those through the machine
plugin. Six consumers × two commands = the 12 sites.

`.trellis/workspace/sdelmas/journal-9.md` also contains the string, as session
history. The journal is append-only and records what was true when written; it
is not edited.

## Verification

| claim | check |
|---|---|
| sources fixed | `grep` the two sources for the clause — 0 hits |
| `sd-audit-repo.md` untouched | `git diff --name-only` does not list it |
| mirrors propagated | repo-wide `grep`, only the journal remains |
| thin text no longer contradicts | the `rewrite_text` harness above prints nothing for both prompt surfaces |
| nothing else broke | `make check` |
| citations still resolve | whole-tree review preflight, 0 failures |

The `rewrite_text` harness is the one that matters. The others confirm the edit
landed; only that one confirms the edit fixes the shape it was written for,
and it does so without needing a consumer to convert.

## Rollback

`git revert` of the single PR. The change is four words in two files plus their
generated mirrors and a version bump; no state migrates, no consumer has acted
on it yet, and a consumer already refreshed onto the new version reverts on its
next refresh. Release-prep artifacts revert with the same commit.
