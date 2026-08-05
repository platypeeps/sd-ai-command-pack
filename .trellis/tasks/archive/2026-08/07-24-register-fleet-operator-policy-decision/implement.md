# Implementation — register the fleet operator policy decision

**One commit.** The registry validator rejects both halves in isolation, so
registration and binding land together, with regeneration in the same commit
because the generated surfaces are derived from them.

No controller changes. No skill-prose rewrite — see step 2.

## Order

1. **Re-read the actual evidence before writing anything.** Both PRD citations
   are wrong. `SKILL.md:241-243` is the finding-severity gate's
   `fleet-finding-classify.py` invocation; `controller-recovery.md:99-105` is the
   pack-blocker recovery transition. The real sites:

   ```
   SKILL.md:110-112              operator-decision in the receipt result vocabulary
   SKILL.md:282-288              the ask / do-not-ask rule
   controller-recovery.md:150-156  ## Operator Decisions
   ```

2. **Do not touch the skill prose.** R2, R3, R4's park behavior, and R5's
   authority limits are already written:

   | requirement | already at |
   |---|---|
   | R2 | `SKILL.md:282-288` |
   | R3 | `controller-recovery.md:152-155` |
   | R4 | `controller-recovery.md:155-156` |
   | R5 | `SKILL.md:280-281` |

   **Gate:** the PRD's own second evidence bullet is the accurate one — the gap
   is that `installer/registry.py` assigns no `interaction_decisions` entry, "so
   generated adapters cannot expose host-native guidance." If the diff touches
   `SKILL.md` or `controller-recovery.md`, it is creating a second copy of a
   contract that already reads correctly.

3. **Use static options. Not `option_source`.** R3's "bound to the exact
   campaign, consumer, release, head/PR, and proposed action" reads like a
   request for dynamic options. The validator (`installer/registry.py:1136-1142`)
   forces dynamic options to be multi-select and to contain the literal
   substring `"independent"`:

   ```python
   elif (
       not decision.multi_select
       or not isinstance(decision.option_source, str)
       or not decision.option_source.strip()
       or "independent" not in decision.option_source
   ):
       errors.append(f"... dynamic options require multi-select")
   ```

   **Gate:** R2 specifies "mutually exclusive policy choices". Rendering those
   as a multi-select checklist is a safety regression. The runtime binding to
   campaign/consumer/head/PR lives in the prompt evidence
   (`controller-recovery.md:154-155`), not in option identity.

4. Write the entry into `INTERACTION_DECISIONS` (`registry.py:532`):

   The three options are decided in planning (2026-07-28), not left to
   implementation. They are the exhaustive disposition set for a campaign that
   the controller has left blocked: stop, retry the same scope, or narrow it.
   Anything else — changing the release, editing consumer state, dispatching a
   merge — is authority this decision may not grant (PRD R6).

   ```python
   InteractionDecision(
       "fleet-refresh.operator-policy",
       "blocked-run-disposition",
       "Fleet policy",
       "How should this blocked fleet campaign proceed?",
       (
           _option(
               "Park the campaign",
               "Stops here and records the blocker against this campaign. "
               "Nothing is dispatched; the release and every consumer keep "
               "their current state. Resume needs a fresh run.",
               recommended=True,
           ),
           _option(
               "Retry the blocked consumer",
               "Re-runs the same already-authorized action against the same "
               "consumer, release, and head. Correct when the blocker was "
               "transient — a timeout or an unreadable API response. Repeats "
               "the failure if the cause is persistent.",
           ),
           _option(
               "Continue without the blocked consumer",
               "Proceeds with the remaining consumers and leaves the blocked "
               "one out of this campaign. The fleet ends partially rolled out "
               "and the excluded consumer needs its own later campaign.",
           ),
       ),
       noninteractive="park",
   )
   ```

   **Gate:** the consequence text is what an operator reads before answering, so
   each one states what happens to the release, the consumers, and the
   resumability — not a restatement of the option label. None of the three
   consequences may describe an action the campaign has not already authorized;
   that is the R6 capability-ledger line, and it is checkable by reading the
   three strings alone.

   Validator constraints this must satisfy, all in `registry.py:1096-1135`:

   - 2–3 options (`INTERACTION_MIN_OPTIONS = 2`, `INTERACTION_MAX_OPTIONS = 3`)
     — matches R3's "at most three".
   - **exactly one recommended option, and it must be first**:
     `if recommended != [0]`. R3's "lowest-risk park option is recommended"
     therefore also fixes its position.
   - unique labels, non-empty `consequence` on every option.
   - `noninteractive` in `{"stop", "park", "report-only"}` (`registry.py:516`);
     `park` matches R4 exactly, and `work-backlog.blocked-disposition`
     (`registry.py:579`) is the sibling that already pairs `park` with
     `blocked-run-disposition`.
   - **header ≤ 12 characters** (`INTERACTION_HEADER_MAX_LENGTH = 12`,
     `registry.py:517`). "Fleet policy" is exactly 12 — at the limit.

5. Bind it on the `sd-fleet-refresh` `CommandInfo` row (`registry.py:837-842`),
   which today declares only `mutates_local=True, mutates_remote=True`:

   ```python
   interaction_decisions=("fleet-refresh.operator-policy",),
   ```

6. **Steps 4 and 5 are one commit.** `registry.py:1144-1156` errors in both
   directions — `unknown interaction decisions` if bound before registered,
   `unreferenced interaction decision(s)` if registered before bound, both
   raising `RuntimeError("invalid interaction registry: …")` at import.

   **Gate:** a split commit does not import. There is no intermediate green
   state.

7. R6 is satisfied by construction: the skill body stays host-agnostic and the
   host tool names come from the generator's per-platform emission
   (`generate-command-surfaces.py:420-440` renders the decision block;
   `registry.py:1062` supplies `structured_question_tool`). Do not write
   `AskUserQuestion` into any authored source.

8. `make generate`, `make sync`, regenerate the catalog and the structured
   question reference.

9. **Check AC2 honestly — it is blocked by an undeclared dependency.**
   `sd-fleet-refresh` is the only member of `SOURCE_ONLY_COMMAND_NAMES`
   (`registry.py:1176`) and its adapters are frozen. Measured:

   ```
   .claude/commands/sd/audit-repo.md       AskUserQuestion: 1
   .claude/commands/sd/fleet-refresh.md    AskUserQuestion: 0   (mtime Jul 18)
   templates/.commands/sd-fleet-refresh.md AskUserQuestion: 0   (mtime Jul 23)
   ```

   audit-repo carries the tool name because `audit.followups` is registered
   *and* its adapter regenerates. fleet-refresh's does not — which is exactly
   what `07-28-regenerate-fleet-refresh-adapters` exists to fix.

   **Gate:** do not hand-edit `.claude/commands/sd/fleet-refresh.md` to make
   AC2 pass. Either land `07-28-regenerate-fleet-refresh-adapters` first, or
   land this work with AC2 left **unchecked** and the task left open until that
   sibling lands. "Partially met" is not a state this criterion has.

   Note which surface is which: `templates/.commands/sd-fleet-refresh.md`
   regenerates normally (`generate-command-surfaces.py:665-691` iterates every
   command; `SOURCE_ONLY_COMMAND_NAMES` at `:881` excludes fleet-refresh only
   from derived *manifest entries*). The frozen file is the root dogfood mirror,
   and that is the one AC2 names.

10. Changelog + version bump.

## Validation

The registry validates — this is the decisive check, because every constraint in
step 4 raises at import:

```bash
python3 -c "import installer.registry as r; print(len(r.INTERACTION_DECISIONS))"
```

Expect one more than before. A failure prints
`invalid interaction registry: <reason>` naming the exact violated rule.

The decision is registered exactly once and bound to exactly one command (AC1):

```bash
grep -c "fleet-refresh.operator-policy" installer/registry.py
```

Expect `2` — one entry, one binding.

Generated reference carries it, and the authored sources do not name a host tool
(R6):

```bash
grep -rn "fleet-refresh.operator-policy" templates/ .claude/ .gemini/ | head
```

```bash
grep -rn "AskUserQuestion" templates/.agents/skills/sd-fleet-refresh/
```

Expect no hits from the second command.

Byte-stability:

```bash
make generate && git diff --stat && make generate && git diff --exit-code
```

```bash
make check
```

**Not verified by any of the above:** AC2 on the Claude surface, if
`07-28-regenerate-fleet-refresh-adapters` has not landed — see step 9. Also
unverified here: AC4's noninteractive/stale-head/wrong-release/mismatched-action
park fixtures. Those exercise the **controller's** rejection paths, which this
commit does not touch; if no such fixtures exist yet, say so rather than
reporting AC4 as met because the registry validated. And AC5 ("routine fleet
transitions complete without approval fatigue") is a property of the skill prose
at `SKILL.md:282-288`, which step 2 forbids changing — it is unchanged, not
newly verified.

## Review gates

- No diff to `SKILL.md` or `controller-recovery.md` (step 2).
- No diff under `scripts/sd-ai-command-pack-fleet-controller.py` — the
  controller remains the state-transition authority (PRD "Out of scope: making
  the controller interactive").
- Static options, `multi_select` left at its `False` default (step 3).
- Park option first, `recommended=True` (step 4).
- Header is 12 characters or fewer (step 4).
- Registration and binding in the same commit (step 6).
- No host tool name in any authored source (step 7).
- `.claude/commands/sd/fleet-refresh.md` is not hand-edited (step 9).

## Rollback

Revert both registry edits together. Reverting one half raises
`RuntimeError: invalid interaction registry` at import — a loud failure, not a
silent one, which is the right shape but means a partial revert breaks the tree
immediately.

No runtime state is created by this change, so there is nothing to migrate back:
`operator-decision` was already a valid receipt result before this task
(`SKILL.md:110-112`).
