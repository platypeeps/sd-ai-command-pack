# Implementation — agent kind and subagent capability gate

Three commits: **kind registration → registry field → renderer and wave-1
rows**. The first two are inert by construction; only the third changes
generated output.

Do not start commit 3 before se-ai-command-pack
`07-25-audit-registry-snapshot-contract` is landed or scheduled in the same
window. Its shipped `skill_review.py` AST-parses this repo's `PlatformInfo`.

## Order

### Commit 1 — register the kind

1. Add `"agent"` to `KNOWN_MANIFEST_KINDS` (`installer/manifest.py:31-42`).

2. Add `"agent"` to the hardcoded tuple at
   `scripts/sd-ai-command-pack-surface-check.py:253`.

3. Add it to `templates/scripts/sd-ai-command-pack-surface-check.py:253` as
   well.

   **Gate:** that file is a byte-identical mirror of step 2's file — `diff -q`
   currently reports no difference. Miss it and `make generate` validates
   locally while every installed consumer rejects the new kind. Re-run the
   `diff -q` after editing both.

4. No other code changes. Verified: kind branching exists at exactly two sites
   across `installer/*.py` — the validation gate (`manifest.py:113`) and a
   `MANAGED_BLOCK_KIND` special case (`provenance.py:101`). Install, status,
   remove, audit, and check are kind-agnostic. If this commit grows a
   `kind == "agent"` branch, something is being modeled wrong.

5. Test: a manifest fixture with a `kind: agent` row validates instead of
   raising `unknown kind 'agent'`.

### Commit 2 — the capability field

6. **Do not model this on `structured_question_tool`.** R1 names it, but it is
   `str | None` naming a runtime tool, set on 2 of 18 rows, and it carries no
   target path — a second field would be needed anyway.

   Model on the pair one row up (`installer/registry.py:25-26`):

   ```python
   agent_kind: str | None = None            # "markdown" | "toml" | "json"
   agent_target_pattern: str | None = None  # ".claude/agents/{filename}"
   ```

   Both consumers of the existing pair already show the gate shape:

   ```
   registry.py:448                    if info.command_kind and info.command_target_pattern
   generate-command-surfaces.py:713   if not info.command_kind or not info.command_target_pattern:
   ```

7. Both fields `None` on all 18 registry rows in this commit. Nothing is
   populated yet.

8. Test the gate directly: for every platform in `PLATFORM_REGISTRY`, if
   `agent_kind` is None then the derived manifest contains zero rows with
   `kind == "agent"` for that platform. R2 asks for exactly this assertion and
   it must pass in this commit, when the answer is trivially zero, so that
   commit 3 cannot weaken it.

9. **Do not touch `trellis_local_only`.** `tests/test_install_core.py:2111`
   requires every entry to appear verbatim in
   `scripts/sd-ai-command-pack-review-scope.sh`, and
   `test_install_core.py:2016-2027` requires any platform with local-only or
   gitignore data to hold a slot in `install._LOCAL_ONLY_GROUP_ORDER` /
   `_LOCAL_GITIGNORE_GROUP_ORDER`.

   **Gate:** pack agents are pack-managed and removable. Adding their paths to
   `trellis_local_only` would carve them out of pack management — the opposite
   of R2's "existing provenance/removal/drift semantics". R2's "gitignore-tuple
   invariants extended" is a non-event as long as this holds; if the diff
   touches either order tuple, the model is wrong.

10. **Do not reuse `SKILL_FANOUT_PLATFORMS`** (`registry.py:456`) as the
    capability list. It is antigravity, codebuddy, devin, droid, kilo, kiro, pi,
    qoder, reasonix, trae — "platforms whose command surface is skills-only",
    containing none of claude/codex/gemini. It looks like a capability list and
    is not one.

### Commit 3 — renderer and wave-1 rows

11. **Wave 1 is claude + codex + gemini.** Recorded per R6. The reason is in
    `design.md` measurement 1: three sources claim to say which platforms
    support agents and they disagree on 11 of 17. These three are the only
    platforms present in all three columns, and they are what the checkout
    actually contains:

    ```
    .claude/agents: 3   .codex/agents: 3   .gemini/agents: 3
    .opencode/agents: 3 .github/agents: 3  (every other platform: 0)
    ```

    codex is the TOML dialect, so wave 1 exercises two dialects rather than
    shipping an MD-only path that pretends to be general.

    **Gate:** do not encode R1's platform lists as written. R1 marks trae,
    qoder, zcode, pi as `none` while the registry reserves agent paths for all
    four (`registry.py:405`, `:357`, `:431`, `:331`), and the parent design
    marks github, opencode, droid, antigravity as supporters while none has a
    registry agent glob. Either list encoded verbatim contradicts the file tree
    on day one.

12. github and opencode are wave 2, not wave 1: both have working directories
    but neither is in the registry column, and `.github/agents/*.agent.md`
    carries the 30,000-char cap plus a `.agent.md` double extension no other
    platform uses. Adding them is an additive registry row, which is what R6
    requires the design to preserve.

13. kiro's JSON dialect is deferred. It has a reserved path
    (`registry.py:270`, `:282`) and zero files. Record the JSON shape in the
    field docstring; build the renderer branch when a kiro agent exists.

14. Canonical source lives at `templates/.agents/agents/<name>.md` — neutral
    Markdown + YAML frontmatter, body is the system prompt. Row shape copies
    `_platform_skill_entry` (`generate-command-surfaces.py:727-734`) and its
    neighbours' shared/per-platform split: the `shared` row carries
    `install: "always"` and no `anchor`; per-platform rows carry `anchor` and no
    `install`.

15. **Enforce the `sd-` prefix in the generator, not by convention.** Every
    platform's Trellis agent glob is name-scoped — `.claude/agents/trellis-*.md`,
    `.codex/agents/trellis-*.toml`, `.gemini/agents/trellis-*.md`.

    **Gate:** a pack agent named `trellis-*` lands inside the Trellis-local
    carve-out, stops being pack-managed, and survives removal. This is R4's
    "collision-safe `sd-` prefix" and it is mechanical, not cosmetic. Raise a
    `GenerationError` on any agent name not matching `sd-`.

16. R4 dispositions, each recorded and each with a test where one is possible:

    - **cursor** auto-loads `.claude/agents/` and `.codex/agents/`. Cursor is
      not in wave 1 and gets no rows; it cross-reads claude's. Record that as
      the decision R4 asks for — "cursor gets no rows of its own in wave 1;
      revisit if cursor-specific frontmatter is needed."
    - **copilot 30,000-char cap** — charters stay runtime-read. Testable as a
      body-length assertion once `.github` enters wave 2; nothing to test now,
      so record it as a constraint on the future renderer rather than claiming
      coverage.
    - **gemini no per-tool confirmation** — the gemini emitter writes a tightly
      scoped `tools:` frontmatter list. Assert the emitted list is a subset of
      an allowlist. This is the one R4 wrinkle that is testable in wave 1.
    - **codex project trust** — one line in install/status output. Prose, no
      test.

17. R5 needs re-derivation before implementing. `sd-check`'s `kind` is a
    different vocabulary — `builtin`, `prerequisite`, `check`
    (`scripts/sd-ai-command-pack-check.py:880`, `:1004`, `:1022`) — the
    check-*result* kind, unrelated to `KNOWN_MANIFEST_KINDS`. There is no typed
    artifact-kind contract in sd-check to extend. What R5 actually requires is
    confirming `--audit`/`--status` enumerate manifest rows generically, which
    per step 4 they do. Do not add a kind vocabulary to sd-check.

18. `make generate`, `make sync`, regenerate the catalog.

19. Changelog + version bump + maintainer docs (AC4).

## Validation

Commit 1 — the kind is accepted in all three lists, and the mirror still
matches:

```bash
grep -c '"agent"' installer/manifest.py scripts/sd-ai-command-pack-surface-check.py templates/scripts/sd-ai-command-pack-surface-check.py
```

```bash
diff -q scripts/sd-ai-command-pack-surface-check.py templates/scripts/sd-ai-command-pack-surface-check.py
```

Expect no output from `diff`.

Commit 2 — the gate produces zero rows, asserted while the answer is trivially
zero:

```bash
python3 -m unittest tests.test_install_core -v 2>&1 | grep -i agent
```

The local-only and gitignore order tuples are untouched:

```bash
git diff -- installer/registry.py | grep -c "trellis_local_only\|local_gitignore_patterns"
```

Expect `0`.

Commit 3 — byte-stability across the fan-out (AC2):

```bash
make generate && git diff --stat && make generate && git diff --exit-code
```

Wave-1 rows exist and no others do:

```bash
python3 -c "import json,sys; from installer.manifest import load_manifest; _,f=load_manifest(); print(sorted({x.platform for x in f if x.kind=='agent'}))"
```

Expect `['claude', 'codex', 'gemini', 'shared']`.

Round-trip (AC1):

```bash
make check
```

**Not verified by any of the above:** that claude, codex, or gemini actually
*load* a rendered `sd-*` agent file. Every check here is structural — the row
exists, the bytes are stable, the dialect parses. Whether the host resolves and
dispatches the agent is a live-host observation with no fixture in this repo.
The same gap applies to the copilot 30,000-char cap, which has nothing to
measure until wave 2. Say both plainly in the AC3 disposition record instead of
implying the wrinkles were tested away.

Also unverified here: the SE pack's `skill_review.py` still parses this
registry after commit 2. That check lives in the other checkout.

## Review gates

- No `kind == "agent"` branch anywhere in `installer/` (step 4). Kinds are
  descriptive; a branch means the model drifted.
- No diff to `trellis_local_only` or to either group-order tuple (step 9).
- Commit 2 lands with both fields `None` on all 18 rows and the zero-rows test
  already passing (steps 7, 8).
- The generator rejects a non-`sd-` agent name (step 15).
- Wave-1 platform set is recorded with its reason, not just its membership
  (step 11, R6).
- R1's platform lists are not encoded verbatim (step 11 gate).
- `07-25-worker-agents` does not start until this is reviewed — it consumes the
  kind, the field, and the naming rule.

## Rollback

Commit 1 reverts to a frozenset member and a tuple member in two files.
Commit 2 reverts two dataclass fields with defaults; no call site changes,
because every consumer gates on None.

Commit 3 is the only one with a behavioral revert: removing wave-1 rows removes
the installed agent files on the next `sd-check`/remove pass. That is correct
removal semantics, not a failure — but it means a consumer mid-campaign loses
agent files, so revert commit 3 outside a fleet-refresh window.
