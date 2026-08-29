---
title: Document the three undocumented shipped scripts
status: done
created: 2026-07-28
---
# Close the doc gap on shipped scripts, or narrow the public-surface claim

## Goal

`CONTRIBUTING.md:135` declares "shipped script paths and CLIs" to be stable
public surface. Three of the 26 shipped `scripts/` targets appear nowhere in the
installed guide, so the repo promises compatibility on interfaces it never
describes. Either document them or narrow the promise — but the two statements
should stop contradicting each other.

## Origin

Created 2026-07-28 from the repo audit with explicit user consent. Owns finding
A-115 (P2 · S · Plausible · documentation).

**The finding's numbers are wrong and are corrected here.** See Notes.

## Evidence

Measured 2026-07-28 against `manifest.json` and `docs/SD_AI_COMMAND_PACK.md`:

- 26 distinct `scripts/` targets in the manifest.
- 23 are named in the installed guide.
- 3 are not:
  - `scripts/sd-ai-command-pack-pr-eligibility.py`
  - `scripts/sd-ai-command-pack-review-local.py`
  - `scripts/sd_ai_command_pack_lib.py`

The three are not the same case, and a single "write three doc sections" fix
would be wrong for at least two of them:

1. **`pr-eligibility.py`** — has an argparse CLI and is already referenced by
   `.agents/skills/sd-housekeeping/SKILL.md`. It is reachable by an operator and
   documented only inside a skill, not the guide.

2. **`review-local.py`** — 2,232 lines, argparse CLI, invoked in production by
   `scripts/sd-ai-command-pack-review.py:34` (`LOCAL_SCRIPT`). It is an internal
   stage of the routed `sd-review` architecture, not an operator entry point.
   It is also the sharper half of this finding: a **separate, unrelated**
   `scripts/sd-ai-command-pack-review-local.sh` (771 lines) is a shipped target
   too (`manifest.json:264-265`), *is* documented
   (`docs/SD_AI_COMMAND_PACK.md:121`, `:549`, `:550`, `:895`, `:2179`;
   `README.md:621`), and **does not invoke the `.py`**. Two live tools share a
   base name; the docs describe one and never mention the other. A reader who
   finds `review-local.py` in the tree has no way to learn which is which.

3. **`sd_ai_command_pack_lib.py`** — primarily the shared library, imported by 31
   files. It also carries a real CLI at `:704-705` dispatching `_cache_env_main`
   (`:673`). Documenting it as an operator tool would misrepresent it;
   documenting nothing leaves a shipped `__main__` undescribed.

There is no doc-coverage gate. A shipped-script **test**-coverage gate exists at
`.github/scripts/check-shipped-script-coverage.sh` (which lists
`scripts/sd-ai-command-pack-review-local.py 70`), but nothing checks that a
shipped target is mentioned in the guide, which is why the gap opened silently.

## Requirements

- R1: decide, per target, whether it is a **public entry point** (operators
  invoke it; it gets a guide entry) or an **internal helper** (only other pack
  code invokes it; it does not). Record the classification and its rationale.
  This decision drives everything else and must come first.

- R2: if any target is classified internal, `CONTRIBUTING.md:135` must be
  narrowed to match. Today it makes every shipped script path and CLI stable
  public surface with no internal category, so leaving `review-local.py`
  undocumented while that sentence stands keeps the contradiction. Add the
  distinction there, or accept all 26 as public and document all 26.

- R3: whatever is classified public gets a guide entry with the same shape the
  existing 23 use — purpose, invocation, arguments, output, exit codes. Do not
  invent a lighter format for the stragglers.

- R4: resolve the `review-local.sh` / `review-local.py` collision explicitly.
  Both are shipped, both are live, neither calls the other, and the docs describe
  only the `.sh`. Whichever classification R1 produces, the guide must let a
  reader tell them apart — at minimum a sentence in the `.sh` section naming the
  `.py` and its role. Renaming one is the cleaner fix but breaks a manifest
  target path, which `CONTRIBUTING.md:135` makes a compatibility event; treat a
  rename as out of scope here unless R2 concludes otherwise.

- R5: add the missing gate. A test that enumerates manifest `scripts/` targets
  and asserts each is either named in `docs/SD_AI_COMMAND_PACK.md` or on an
  explicit internal allowlist. Without it this finding recurs on the next added
  script. The allowlist is the R1 classification made executable.

- R6: template parity. `templates/docs/SD_AI_COMMAND_PACK.md` mirrors the guide
  (the symlink-root passage is at `:1065` in both); both copies change together
  and generated-parity checks stay green.

## Acceptance Criteria

- [x] R1: every one of the 26 targets carries a public/internal classification.
- [x] R5: the coverage test passes, and fails if a new `scripts/` target is added
      to the manifest without either a guide entry or an allowlist entry.
      Verify the failure mode, not just the passing one.
- [x] R2: `CONTRIBUTING.md` and the guide agree — no target is simultaneously
      "stable public surface" and undocumented.
- [x] R4: `docs/SD_AI_COMMAND_PACK.md` distinguishes `review-local.sh` from
      `review-local.py`; a reader can tell which one `sd-review` runs.
- [x] R6: `docs/` and `templates/docs/` copies are identical; `make sync` passes.
- [x] `make check` passes.
- [x] Changelog + version; fleet rollout via normal refresh.

## Notes

- Audit source: `.trellis/audit/report-2026-07-28.md` — A-115 (P2 · S ·
  Plausible · documentation).
- **A-115's figures are wrong; corrected 2026-07-28.** The ledger says "five
  shipped scripts undocumented" and that the docs cover "21 of the 26" targets.
  Measured: **23 of 26** are documented, **3** are missing. The ledger also says
  `review-local.py` is "mentioned in no README, doc, or skill" — true for the
  `.py` exactly, but it obscures the more useful fact that a same-named `.sh`
  *is* documented in six places. Use the numbers in Evidence, not the ledger's.
- The finding's implied fix — write documentation for five scripts — is wrong for
  at least `sd_ai_command_pack_lib.py`, which is a library that would be
  misrepresented as an operator tool. R1 exists so the classification decision is
  made deliberately rather than absorbed into a docs-writing task.
- R5 is the durable part. The three doc entries are worth a day at most; the
  missing gate is why the gap existed and is what stops it reopening.
- Planning: R1's classification is a judgment call across 26 targets and R2 may
  touch a compatibility contract. Add `design.md` before `task.py start` if R1
  concludes anything other than "all 26 are public."
