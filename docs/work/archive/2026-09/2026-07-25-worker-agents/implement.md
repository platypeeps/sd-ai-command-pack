# Implementation — wave-1 SD named agents

Four commits: **sd-audit-refuter → sd-audit-reviewer → sd-ci-triager → R6
reference sentences.** Not the PRD's listing order; the refuter has the
smallest contract and the tightest invocation constraint, so it sets the house
shape.

Blocked by `07-25-agent-artifact-kind` — kind, capability field, renderer, and
the `sd-` naming rule all come from there. Commit 3 additionally waits on
`07-25-fix-ci-dispatch` being reviewed.

Wave-1 platform set is claude + codex + gemini, inherited from
`07-25-agent-artifact-kind`. Do not re-decide it here.

## Order

### Before any commit — settle the enforcement claim

1. **Measure what each wave-1 dialect can actually express, and write the
   answer into install/status output.** Measured from the shipped Trellis
   agents:

   ```
   claude    tools: Read, Write, Edit, Bash, Glob, Grep     comma string
   codex     sandbox_mode = "workspace-write" + [features]  TOML mode + flags
   gemini    (no tools field in any shipped agent)          not expressible
   ```

   Read-only renders differently on each: drop `Write, Edit` on claude; set
   `sandbox_mode = "read-only"` on codex; on gemini there is **no mechanism**.

   **Gate:** the Goal says "ENFORCED tool restriction is the point". That is
   true on claude and codex and false on gemini — which is also the platform
   parent `design.md` §1.5 singles out as running subagents *without per-tool
   confirmation*. AC2's "documented limitation where it cannot" is not a
   footnote here; it is the headline for one of three wave-1 platforms. If the
   changelog or docs imply uniform enforcement, back it out.

2. **Turn off sub-agent spawning in every dialect that can express it.** Codex
   shows the structural fix already in this checkout:

   ```toml
   [features]
   multi_agent = false
   ```

   with the shipped comment that `spawn_agent` / `wait_agent` / `list_agents` /
   `close_agent` "are not registered in the sub-agent's tool list at all — the
   model literally cannot call them."

   **Gate:** a reviewer that can spawn reviewers breaks one-agent-per-charter
   accounting, and a refuter that can spawn refuters corrupts the 2-of-3 vote.
   Where the dialect cannot express it, say so in the body.

### Commit 1 — sd-audit-refuter

3. Canonical source at `templates/.agents/agents/sd-audit-refuter.md`, neutral
   MD + frontmatter, body is the system prompt.

4. Contract: input one finding; output refute/uphold with evidence; **prompted
   to refute by default**, defaulting to refuted when uncertain
   (`sd-audit-repo/SKILL.md:169-170` — refuters "receive one finding each with
   the instruction to disprove it").

5. **Write it stateless and non-singleton.** R3 says "input = one finding",
   which is true but incomplete. The orchestrator's depth rules
   (`SKILL.md:70-74`) invoke it three ways:

   - `standard`: one refuter, P0/P1 only
   - `exhaustive`: P0–P2, with **P0 using 2-of-3 refuter votes**
   - `exhaustive`: correctness and security **loop until a pass** finds nothing

   **Gate:** the body must carry no run-scoped state and must not address
   itself as "the" refuter. Three concurrent instances that share an assumption
   produce correlated votes, which is the same as not voting.

6. Read-only, and it never writes the ledger — `SKILL.md:171` is "Reviewers and
   refuters never modify files. Only the orchestrator writes."

### Commit 2 — sd-audit-reviewer

7. Input is **one charter path** plus the fingerprint scope brief verbatim, and
   nothing else. `SKILL.md:166-168`: reviewers do not read other charters and do
   not re-derive the repository inventory.

8. **Keep charters runtime-read (R5) — but not for the reason R5 gives.**
   Measured: 15 charters, 60,787 bytes total, largest 4,781 bytes. A single
   charter is ~4.8k, six times under Copilot's 30,000-char cap, so the cap
   argument does not hold for one charter.

   The real reason is structural: this agent is **charter-agnostic**. One
   definition serves all 15 charters, chosen per dispatch by the router
   (`scripts/sd-ai-command-pack-audit-route.py`). Inlining means 15 agent
   definitions and a router that names agents instead of charters. Record the
   corrected rationale; keep the requirement.

9. Reproduce the finding schema **verbatim** from `SKILL.md:142-149`:

   ```
   [<dimension>] <title>
   severity: P0-P3 · effort: S/M/L
   evidence: <file:line> (+ short excerpt or command output)
   why it matters: <1-2 sentences>
   fix sketch: <1-3 sentences>
   ```

10. No IDs. `SKILL.md:154`: "Finding IDs (`A-NNN`) are assigned by the
    orchestrator at ledger-write time, never by reviewers; this prevents ID
    collisions across parallel agents." R2's ID rule is a restatement of this
    existing invariant, not a new constraint.

11. Add a drift test comparing the schema block in the agent body against
    `SKILL.md`.

    **Gate:** this is now a two-copy contract — the agent body *is* the system
    prompt, so duplication is unavoidable. Without the test, the copies split
    silently and the ledger is downstream of both.

### Commit 3 — sd-ci-triager

12. Do not start until `07-25-fix-ci-dispatch` is reviewed. That task owns the
    contract; this commit copies it and must not re-derive it.

13. Input: run id + job id + job name; that job's `--log-failed` output; the
    run-level change context the parent resolved once (behind-default-branch
    status, PR-head/local-HEAD note).

14. Output: exactly one of `real-code | flake | infra | stale-baseline`,
    evidence **quotes** not summaries, and a proposed fix or rerun disposition.

15. **No `gh run rerun`, no writes, no pushes.**

    **Gate:** `max-reruns` (default 1) is a shared counter owned by the parent.
    An agent that can rerun makes the bound unenforceable — this is the same
    gate as `07-25-fix-ci-dispatch` step 4, and it is why the triager's toolset
    matters more than its prompt.

### Commit 4 — R6 reference sentences

16. One sentence in `sd-audit-repo/SKILL.md`'s dispatch protocol and one in
    `sd-fix-ci`'s, naming the agents as an optional enhancement.

17. Do not restructure either dispatch section. The behavior-without-them
    clause is already satisfied — `SKILL.md:158-161` already says "On inline
    platforms, work through the selected charters sequentially in one context."

18. R7's context prefix is already the house convention
    (`SKILL.md:163-165`): every dispatch prompt opens with
    `Active task: <task path from task.py current>`. Trust is the single
    carried-forward `checkout-trust: <state> (<reason-code>)` line inherited
    from `07-25-fix-ci-dispatch` — workers never reclassify.

19. `make generate`, `make sync`, catalog, changelog, version bump.

## Validation

Agents render and install on wave-1 platforms only (AC1):

```bash
python3 -c "from installer.manifest import load_manifest; _,f=load_manifest(); print(sorted((x.platform,x.target) for x in f if x.kind=='agent'))"
```

Expect rows for `shared`, `claude`, `codex`, `gemini` and no others.

Restriction is expressed where the dialect allows (AC2):

```bash
grep -n "tools:" templates/.agents/agents/sd-audit-reviewer.md .claude/agents/sd-audit-reviewer.md
```

```bash
grep -n "sandbox_mode\|multi_agent" .codex/agents/sd-audit-reviewer.toml
```

Expect `sandbox_mode = "read-only"` and `multi_agent = false`.

No agent can rerun CI or write:

```bash
grep -rn "gh run rerun\|git push\|git commit" templates/.agents/agents/
```

Expect no hits.

Byte-stability across the fan-out:

```bash
make generate && git diff --stat && make generate && git diff --exit-code
```

```bash
make check
```

**Not verified by any of the above:** that a host actually *enforces* the
restriction it was handed. Every check here reads the emitted file; none
observes a refused tool call. On gemini it cannot be verified even in principle
— the dialect has no field to check, so `sd-audit-reviewer` is read-only there
by prose alone. Also unverified: that three concurrent refuters produce
independent verdicts (step 5). That is a property of the prompt, observable only
in a live exhaustive audit run, and there is no fixture for it. State both in
the AC2 record instead of implying enforcement was tested.

## Review gates

- No commit claims uniform enforcement (step 1). The gemini limitation is in
  install/status output, not only in a design doc.
- No agent body can spawn sub-agents where the dialect can prevent it (step 2).
- The refuter body reads as one of many, not as the singleton (step 5).
- Charters are referenced by path, never inlined (step 8).
- The finding schema in the reviewer body matches `SKILL.md:142-149` and the
  drift test exists (steps 9, 11).
- The triager cannot rerun or write (step 15).
- Commit 3 does not land before `07-25-fix-ci-dispatch` is reviewed.
- Both skills still work with no agents installed (R6, step 17).

## Rollback

Each agent commit reverts independently; its rows disappear on the next removal
pass and both skills fall back to built-in sub-agents or the inline path, which
is today's behavior.

Commit 4 is the coupling: revert an agent without reverting its reference
sentence and a skill body names an agent that no longer installs. Revert them
together, or revert commit 4 first.
