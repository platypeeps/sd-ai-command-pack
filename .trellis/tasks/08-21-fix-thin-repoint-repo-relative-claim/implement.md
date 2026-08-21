# Implement — correct the repo-relative claim the thin repoint contradicts

Branch off `main` in the pack repository. One PR.

## Step 0 — capture the pre-fix reproduction

Run the harness from `design.md` against both prompt templates and keep the
output. It must show the contradiction on both. If it does not, the defect is
not what this task says it is and the plan stops here rather than proceeding to
fix something else.

```bash
.venv/bin/python - <<'PY'
import sys; sys.path.insert(0, '.')
from installer.references import rewrite_text, THIN_PROFILE
for name in ("sd-housekeeping", "sd-review-learnings"):
    key = f".github/prompts/{name}.prompt.md"
    text = open(f"templates/{key}").read()
    for line in rewrite_text(text, profile=THIN_PROFILE, key=key).splitlines():
        if "relative to the repository root" in line:
            print(name, "::", line[:120])
PY
```

Expected now: two lines. Expected after Step 1: none.

## Step 1 — edit the two authored sources

Delete ` relative to the repository root` from:

- `.github/command-sources/sd-review-learnings.md`, line 12
- `.github/command-sources/sd-housekeeping.md`, line 13

Leave the trailing period. Do not open `.github/command-sources/sd-audit-repo.md`.

Sanity: `git diff --name-only` lists exactly those two files.

## Step 2 — propagate

```bash
make generate    # rewrites templates/ and plugins/
make sync        # installs those into this repo's own .claude/ .github/ .opencode/
```

Both, in that order. `make generate` does not touch this repository's own
adapter directories — they are an install of the templates, and `make sync`
is what performs it. Running only the first leaves 6 of the 16 mirrors stale.
If `make generate` fails reporting stale mirrors, run `make sync` first and
retry; that is what the 0.71.41 release needed.

Then confirm the repo-wide state, matching the **defect phrase** specifically:

```bash
grep -rln "at that path relative to the repository root" . --include=*.md \
  | grep -v '^./.git/'
```

Expected, and only these three: `.trellis/workspace/sdelmas/journal-9.md`
(append-only history), this task's own `design.md`, which quotes the defective
line as evidence, and this `implement.md`, which contains the phrase inside the
grep command two lines above. A verification command that matches its own text
is a trap worth naming rather than being surprised by. Nothing else — in
particular nothing named `housekeeping` or `review-learnings`.

Match that phrase, not the shorter `relative to the repository root` — the
short form also selects the `sd-audit-repo` family, 9 files that are correct
and must not change, and reading their presence as a failure is a way to
"fix" something that was never broken.

## Step 3 — re-run the harness

Step 0's script, again. Zero lines. This is the acceptance check the task
exists for; a pass on Steps 1 and 2 with a fail here means the edit landed
somewhere the rewrite does not read.

## Step 4 — version and changelog

Bump `manifest.json` past 0.71.41 — patch, since this is a prose correction
with no behavior change — and add the matching `CHANGELOG.md` entry under a
`### Fixed` heading, naming the contradiction rather than the edit.

```bash
make release-prep      # prepare-release.py, then make check
```

`make check` must exit 0. If a test breaks, understand it before touching it;
no test asserts this clause today, so a failure here means something else.

## Step 5 — preflight and PR

```bash
node scripts/sd-ai-command-pack-review-preflight.mjs   # 0 failures
git diff --check                                       # trailing whitespace
```

`git diff --check` is not optional: the CI scope lane runs it and the local
review preflight does not, so a trailing space passes locally and reds CI.
That cost a round trip on #529.

Open the PR, request Copilot review, converge, merge.

## Step 6 — record

Note in the PR body that this is the second defect of the adapter-survives-
conversion family, after #529, and that both were invisible because they only
surface when a fat consumer converts.

## Rollback

Revert the merge commit. Nothing else to undo.

## What could go wrong

- **`make generate` rewrites more than expected.** The mirrors are generated
  from the sources, so a large diff means the mirrors were already stale before
  this change. Inspect before committing; a stale-mirror diff belongs to its own
  commit, not smuggled into this one.
- **The harness passes but a real consumer still contradicts itself.** It would
  mean the shipped rewrite path differs from `rewrite_text` as called here.
  Check against a consumer's actual `.github/prompts/` after the next refresh;
  out of scope to force one.
