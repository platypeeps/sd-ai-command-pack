# Design — register the fleet operator policy decision

## Scope boundary

One `InteractionDecision` entry plus one `interaction_decisions` binding on the
`sd-fleet-refresh` command row, and the regenerated surfaces that follow. No
controller changes, no new interaction implementation, no skill-prose rewrite.

The last point is not a convention — it is a measurement. The skill already
carries the whole contract this task is supposed to establish.

## Confirmed measurements

### 1. Both PRD evidence citations point at the wrong lines

`templates/.agents/skills/sd-fleet-refresh/SKILL.md:241-243` is not a question
contract. It is the finding-severity gate's command invocation:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-finding-classify.py \
  --input <temporary-findings.json> --json
```

`references/controller-recovery.md:99-105` is the pack-blocker recovery
transition, not the operator-decision contract.

The real sites:

- `SKILL.md:110-112` — `operator-decision` as a member of the receipt result
  vocabulary, alongside `passed`, `at-target`, `retryable-failure`, and the
  rest.
- `SKILL.md:282-288` — the ask/do-not-ask rule: "Ask only when the controller
  emits a genuine operator decision; `no-merge` remains the explicit way to stop
  before merge" and "Use the portable structured-question contract only for a
  genuinely ambiguous operator policy choice. Normal retries, polling, receipts,
  and optional absence do not prompt."
- `controller-recovery.md:150-156` — the `## Operator Decisions` section:
  "Recommend the lowest-risk option, state the tradeoff, and bind the answer to
  the exact campaign, consumer, head/PR, and action. Noninteractive execution
  records `operator-decision` and parks safely instead of inferring consent."

### 2. The prose contract already exists in full — the gap is registry-side only

Mapping the requirements onto measurement 1:

| requirement | already written at |
|---|---|
| R2 (ask only on genuine ambiguity; routine flow never prompts) | `SKILL.md:282-288` |
| R3 (recommend lowest-risk; bind to campaign/consumer/head/PR/action) | `controller-recovery.md:152-155` |
| R4 (noninteractive records `operator-decision` and parks) | `controller-recovery.md:155-156` |
| R5 (prose never overrides an invalid transition) | `SKILL.md:280-281` |

So R2–R5 are not new behavior. They are the *specification* of a decision that
was never registered, which is exactly what the PRD's second evidence bullet
says: "`installer/registry.py` assigns no `interaction_decisions` entry to
`sd-fleet-refresh`, so generated adapters cannot expose host-native guidance."

That bullet is the accurate one, and it is the whole task. Treating R2–R5 as
prose work would produce a second copy of a contract that already reads
correctly.

### 3. The registry validator forces the option model — it is not a judgement call

`installer/registry.py:1100-1142`. A decision must declare **exactly one** of
static `options` or `option_source`:

```python
has_static_options = bool(decision.options)
has_dynamic_options = decision.option_source is not None
if has_static_options == has_dynamic_options:
    errors.append(f"... must declare exactly one option source")
```

and the dynamic branch is gated hard:

```python
elif (
    not decision.multi_select
    or not isinstance(decision.option_source, str)
    or not decision.option_source.strip()
    or "independent" not in decision.option_source
):
    errors.append(f"... dynamic options require multi-select")
```

R2 describes "mutually exclusive policy choices" — single-select. Dynamic
options are multi-select only. **Therefore this decision uses static options.**

The static branch then imposes:

- 2–3 options (`INTERACTION_MIN_OPTIONS = 2`, `INTERACTION_MAX_OPTIONS = 3`),
  matching R3's "at most three" exactly.
- exactly one recommended option and it must be **first**:
  `if recommended != [0]: errors.append("... must put one recommendation
  first")`. R3's "lowest-risk park option is recommended" therefore also fixes
  its position.
- every option needs a non-empty `consequence`.

R3's other half — "bound to the exact campaign, consumer, release, head/PR, and
proposed action" — is *not* expressible in a static option label and does not
need to be. The binding is runtime prompt context, and it is already required by
`controller-recovery.md:154-155`. Option identity is the policy choice; the
binding is the evidence presented alongside it.

### 4. `noninteractive="park"` is a real value with a sibling precedent

`INTERACTION_NONINTERACTIVE_BEHAVIORS = frozenset({"stop", "park",
"report-only"})` (`registry.py:516`). R4's "records `operator-decision` and parks
without advancing state" maps to `park` exactly, and
`work-backlog.blocked-disposition` (`registry.py:579`) already pairs
`noninteractive="park"` with category `blocked-run-disposition`. Follow that
pair.

### 5. Registration and binding cannot be split across commits

`registry.py:1144-1156` errors both ways:

```python
unknown = sorted(set(command.interaction_decisions) - known_ids)   # bind-first fails
...
unreferenced = sorted(known_ids - referenced_ids)                  # register-first fails
```

`raise RuntimeError("invalid interaction registry: " + …)`. One commit, both
edits.

### 6. `INTERACTION_HEADER_MAX_LENGTH = 12` is tight for this decision

`registry.py:517`. "Fleet policy" is exactly 12 characters — at the limit, not
under it. Anything more descriptive fails validation.

### 7. AC2 is blocked by an undeclared dependency

`sd-fleet-refresh` is the sole member of
`SOURCE_ONLY_COMMAND_NAMES` (`registry.py:1176`), and the generator branches on
it at `.github/scripts/generate-command-surfaces.py:354` (catalog availability
column) and `:881` (excluded from derived manifest entries).

Measured on disk:

```
.claude/commands/sd/audit-repo.md       AskUserQuestion: 1
.claude/commands/sd/fleet-refresh.md    AskUserQuestion: 0   (mtime Jul 18)
templates/.commands/sd-fleet-refresh.md AskUserQuestion: 0   (mtime Jul 23)
```

audit-repo carries the tool name because `audit.followups` is registered and its
adapter is regenerated. fleet-refresh's adapters are **frozen** — which is the
entire subject of `07-28-regenerate-fleet-refresh-adapters`. Registering the
decision will change `templates/.commands/sd-fleet-refresh.md` and the generated
structured-question reference, but AC2's "Claude-capable output names
`AskUserQuestion`" targets `.claude/commands/sd/fleet-refresh.md`, which the
generator is not currently refreshing.

**This dependency is not in the PRD.** Either `07-28-regenerate-fleet-refresh-adapters`
lands first, or AC2 must be restated against the surfaces this task can actually
regenerate.

## The central tension

The task looks like a policy-design problem — what should the operator be asked?
Measurements 2 and 3 say it is not. The question is already specified in prose,
and the validator dictates the data shape. What is left is a registration whose
only real risk is being written to match the *requirements' wording* rather than
the *validator's rules* — R3's "bound to the exact campaign, consumer, release,
head/PR, and proposed action" reads like a request for dynamic options, and
dynamic options would silently force `multi_select=True`, turning mutually
exclusive policy choices into a checklist.

## Contract

```python
InteractionDecision(
    "fleet-refresh.operator-policy",
    "blocked-run-disposition",
    "Fleet policy",                      # exactly 12 chars, the maximum
    "How should this blocked fleet campaign proceed?",
    (
        _option("Park campaign", "<lowest-risk park consequence>", recommended=True),
        _option("<narrowed action>", "<consequence>"),
        _option("<validated action>", "<consequence>"),
    ),
    noninteractive="park",
)
```

bound by `interaction_decisions=("fleet-refresh.operator-policy",)` on the
`sd-fleet-refresh` `CommandInfo` row (`registry.py:837-842`), which currently
declares only `mutates_local=True, mutates_remote=True`.

The ID follows the established `<command-short>.<slug>` convention used by every
existing entry (`help.route`, `create-pr.file-scope`,
`work-backlog.blocked-disposition`, `audit.followups`, `retro.followups`,
`review-learnings.external-target`, `update-spec.ownership-scope`), so R1's
preferred ID is also the conventional one.

The controller stays the state-transition authority. R5's limits — a response
may narrow authority or select an already-validated action, never broaden scope
or invent a transition — are enforced by the controller rejecting invalid
transitions, not by the option text.

## Compatibility

Adding a decision changes generated output for every surface that renders the
structured-question reference, plus the fleet command's own adapters. The
generator already raises `GenerationError` on an unknown decision id
(`generate-command-surfaces.py:369-371`), so a mismatch fails loudly at
generation rather than shipping.

No controller, receipt vocabulary, or state file changes. `operator-decision` is
already a valid receipt result (`SKILL.md:110-112`), so the noninteractive park
path records something the controller already accepts.

The source-checkout-only policy is unchanged: the decision is registered against
a command that is still excluded from derived manifest entries at
`generate-command-surfaces.py:881`.

## Rollout and rollback

One commit for the registry pair (measurement 5), then regeneration in the same
commit because the generated reference and adapters are derived from it.

If `07-28-regenerate-fleet-refresh-adapters` has not landed, the registry work
can still land — but **AC2 stays unchecked and this task stays open.** The
neutral surface and the structured-question reference will carry the decision;
`.claude/commands/sd/fleet-refresh.md` will not, until the adapters unfreeze.
Do not hand-edit the frozen adapter to make AC2 pass, and do not archive the
task with AC2 recorded as "partially met" — a criterion that says
"Claude-capable output names `AskUserQuestion`" is either true of that file or
it is not. Completion is gated on the sibling task; landing early is allowed,
closing early is not.

The distinction that makes this work: `templates/.commands/sd-fleet-refresh.md`
**is** regenerated — `generate-command-surfaces.py:665-691` iterates every
command for template adapters, and `SOURCE_ONLY_COMMAND_NAMES` excludes
fleet-refresh only from *derived manifest entries* at `:881`. What is frozen is
the root dogfood mirror under `.claude/commands/sd/`. So this task moves the
template surface immediately and the mirror later; only the mirror is AC2's
target.

Rollback is removing both edits together; leaving either half raises
`RuntimeError` at import, which is a loud failure rather than a silent one.

## Risk

1. **Using `option_source` because R3 says "bound to the exact campaign".** It
   forces `multi_select=True` and requires the literal substring `"independent"`
   in the source string. Mutually exclusive policy choices rendered as a
   multi-select checklist is a safety regression, not a formatting one.
2. **Landing AC2 as satisfied while the fleet adapters are frozen.** The check
   passes on the neutral surface and fails on the host surface the criterion
   actually names.
3. **Rewriting the skill prose.** R2–R5 already exist verbatim
   (measurement 2); a second copy is a two-copy contract with no test.
4. **Splitting registration from binding.** Both directions raise; the tree does
   not import between the two commits.
5. **A header longer than 12 characters.** Silent-looking requirement, loud
   validator.
6. **Category choice.** `blocked-run-disposition` is chosen for the sibling
   precedent that pairs it with `noninteractive="park"`;
   `higher-risk-mutation` is defensible if the decision is framed at the merge
   boundary rather than at the blocked campaign. Pick one and record why —
   nothing downstream reads it, so the cost of being wrong is documentation
   drift, not behavior.
